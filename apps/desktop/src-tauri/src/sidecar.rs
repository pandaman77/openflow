//! Python engine sidecar: spawn, JSON-RPC over stdio, auto-restart.
//!
//! In dev the engine runs from the repo venv (`OPENFLOW_ENGINE_CMD` env
//! override); in production it's the bundled PyInstaller binary next to
//! the app exe (tauri externalBin).
//!
//! A background reader thread pumps every stdout line into a channel, so a
//! call can wait with a timeout: a silently hung engine never freezes the GUI
//! forever — the call times out and the engine is force-restarted.

use std::fs::File;
use std::io::{BufRead, BufReader, Write};
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::mpsc::{self, Receiver, RecvTimeoutError};
use std::sync::Mutex;
use std::time::Duration;

use serde_json::{json, Value};

/// Upper bound on any single call. Generous because loading a large model on a
/// slow CPU can take tens of seconds; this only guards against a *permanent*
/// hang, not against a slow-but-progressing engine.
const CALL_TIMEOUT: Duration = Duration::from_secs(120);

/// A hard-killed shell leaves its engine child orphaned; on next launch we
/// reap any stray engine processes so we don't stack up (and hog the mic).
#[cfg(windows)]
fn kill_orphan_engines() {
    use std::os::windows::process::CommandExt;
    let _ = Command::new("taskkill")
        .args(["/F", "/IM", "openflow-engine.exe"])
        .creation_flags(0x0800_0000) // CREATE_NO_WINDOW
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status();
}

#[cfg(not(windows))]
fn kill_orphan_engines() {}

/// %APPDATA%\OpenFlow\engine.log — the engine's stderr (its logging output).
fn engine_log_file() -> Option<File> {
    let dir = std::path::PathBuf::from(std::env::var_os("APPDATA")?).join("OpenFlow");
    std::fs::create_dir_all(&dir).ok()?;
    File::create(dir.join("engine.log")).ok()
}

pub struct Engine {
    child: Mutex<Option<Child>>,
    stdin: Mutex<Option<ChildStdin>>,
    // Every stdout line arrives here, parsed, from the reader thread.
    responses: Mutex<Option<Receiver<Value>>>,
    // Serializes whole request->response transactions. Without it two
    // concurrent calls can each consume (and discard) the other's reply.
    call_lock: Mutex<()>,
    next_id: AtomicU64,
}

impl Engine {
    pub fn new() -> Self {
        Self {
            child: Mutex::new(None),
            stdin: Mutex::new(None),
            responses: Mutex::new(None),
            call_lock: Mutex::new(()),
            next_id: AtomicU64::new(1),
        }
    }

    fn engine_command() -> Command {
        if let Ok(cmd) = std::env::var("OPENFLOW_ENGINE_CMD") {
            // dev override, e.g. "C:\...\.venv\Scripts\python.exe -m openflow_engine"
            let parts: Vec<&str> = cmd.split_whitespace().collect();
            let mut c = Command::new(parts[0]);
            c.args(&parts[1..]);
            return c;
        }
        // production: bundled sidecar binary next to the exe
        let exe_dir = std::env::current_exe()
            .ok()
            .and_then(|p| p.parent().map(|d| d.to_path_buf()))
            .unwrap_or_default();
        Command::new(exe_dir.join("openflow-engine.exe"))
    }

    pub fn start(&self) -> Result<(), String> {
        let mut guard = self.child.lock().unwrap();
        if guard.is_some() {
            return Ok(());
        }
        kill_orphan_engines();
        let mut cmd = Self::engine_command();
        // Engine logs go to a file: a GUI parent has no console, so
        // inheriting stderr would hand the child an invalid handle.
        let stderr = engine_log_file()
            .map(Stdio::from)
            .unwrap_or_else(Stdio::null);
        cmd.stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(stderr);
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
        }
        let mut child = cmd.spawn().map_err(|e| format!("engine spawn failed: {e}"))?;
        *self.stdin.lock().unwrap() = child.stdin.take();

        // Reader thread: parse each stdout line and forward it. It ends when the
        // engine closes stdout (exit/kill), which drops the sender and lets a
        // waiting call see Disconnected.
        let (tx, rx) = mpsc::channel::<Value>();
        if let Some(stdout) = child.stdout.take() {
            std::thread::spawn(move || {
                let mut reader = BufReader::new(stdout);
                loop {
                    let mut raw = Vec::new();
                    // read_until + lossy: device names may arrive in the OEM
                    // code page from older engines — never abort on that.
                    match reader.read_until(b'\n', &mut raw) {
                        Ok(0) | Err(_) => break, // EOF or pipe error
                        Ok(_) => {}
                    }
                    let line = String::from_utf8_lossy(&raw);
                    if let Ok(value) = serde_json::from_str::<Value>(line.trim()) {
                        if tx.send(value).is_err() {
                            break; // receiver gone
                        }
                    }
                }
            });
        }
        *self.responses.lock().unwrap() = Some(rx);
        *guard = Some(child);
        log::info!("engine started");
        Ok(())
    }

    pub fn stop(&self) {
        let _ = self.call("shutdown", json!({}));
        // Kill outright rather than wait(): a call() during shutdown may have
        // silently restarted the child, and a stuck engine would never exit.
        if let Some(mut child) = self.child.lock().unwrap().take() {
            let _ = child.kill();
            let _ = child.wait();
        }
        *self.stdin.lock().unwrap() = None;
        *self.responses.lock().unwrap() = None;
    }

    fn restart(&self) -> Result<(), String> {
        log::warn!("engine unresponsive, restarting");
        if let Some(mut child) = self.child.lock().unwrap().take() {
            let _ = child.kill();
            let _ = child.wait();
        }
        *self.stdin.lock().unwrap() = None;
        *self.responses.lock().unwrap() = None;
        self.start()
    }

    /// Blocking JSON-RPC call with a hard timeout. The whole transaction is
    /// serialized by call_lock so a concurrent caller can never swallow
    /// someone else's response line.
    pub fn call(&self, method: &str, params: Value) -> Result<Value, String> {
        let _transaction = self.call_lock.lock().unwrap();
        let id = self.next_id.fetch_add(1, Ordering::SeqCst);
        let request = json!({"jsonrpc": "2.0", "id": id, "method": method, "params": params});
        let line = serde_json::to_string(&request).map_err(|e| e.to_string())?;

        {
            let mut stdin = self.stdin.lock().unwrap();
            let pipe = stdin.as_mut().ok_or("engine not running")?;
            pipe.write_all(line.as_bytes()).map_err(|e| e.to_string())?;
            pipe.write_all(b"\n").map_err(|e| e.to_string())?;
            pipe.flush().map_err(|e| e.to_string())?;
        }

        let deadline = std::time::Instant::now() + CALL_TIMEOUT;
        let responses = self.responses.lock().unwrap();
        let rx = responses.as_ref().ok_or("engine not running")?;
        loop {
            let remaining = deadline.saturating_duration_since(std::time::Instant::now());
            match rx.recv_timeout(remaining) {
                Ok(value) => {
                    if value.get("id").and_then(Value::as_u64) != Some(id) {
                        continue; // a notification or a stale reply — skip
                    }
                    if let Some(err) = value.get("error") {
                        return Err(err["message"].as_str().unwrap_or("engine error").to_string());
                    }
                    return Ok(value.get("result").cloned().unwrap_or(Value::Null));
                }
                Err(RecvTimeoutError::Timeout) => {
                    drop(responses);
                    self.restart()?;
                    return Err("engine timed out (restarted)".into());
                }
                Err(RecvTimeoutError::Disconnected) => {
                    drop(responses);
                    self.restart()?;
                    return Err("engine died mid-call (restarted)".into());
                }
            }
        }
    }
}
