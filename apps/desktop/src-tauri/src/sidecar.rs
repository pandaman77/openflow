//! Python engine sidecar: spawn, JSON-RPC over stdio, auto-restart.
//!
//! In dev the engine runs from the repo venv (`OPENFLOW_ENGINE_CMD` env
//! override); in production it's the bundled PyInstaller binary next to
//! the app exe (tauri externalBin).

use std::fs::File;
use std::io::{BufRead, BufReader, Write};
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Mutex;

use serde_json::{json, Value};

/// %APPDATA%\OpenFlow\engine.log — the engine's stderr (its logging output).
fn engine_log_file() -> Option<File> {
    let dir = std::path::PathBuf::from(std::env::var_os("APPDATA")?).join("OpenFlow");
    std::fs::create_dir_all(&dir).ok()?;
    File::create(dir.join("engine.log")).ok()
}

pub struct Engine {
    child: Mutex<Option<Child>>,
    stdin: Mutex<Option<ChildStdin>>,
    stdout: Mutex<Option<BufReader<ChildStdout>>>,
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
            stdout: Mutex::new(None),
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
        *self.stdout.lock().unwrap() = child.stdout.take().map(BufReader::new);
        *guard = Some(child);
        log::info!("engine started");
        Ok(())
    }

    pub fn stop(&self) {
        let _ = self.call("shutdown", json!({}));
        if let Some(mut child) = self.child.lock().unwrap().take() {
            let _ = child.wait();
        }
        *self.stdin.lock().unwrap() = None;
        *self.stdout.lock().unwrap() = None;
    }

    fn restart(&self) -> Result<(), String> {
        log::warn!("engine unresponsive, restarting");
        if let Some(mut child) = self.child.lock().unwrap().take() {
            let _ = child.kill();
            let _ = child.wait();
        }
        *self.stdin.lock().unwrap() = None;
        *self.stdout.lock().unwrap() = None;
        self.start()
    }

    /// Blocking JSON-RPC call. The engine is single-threaded (one mic, one
    /// model), and the whole transaction is serialized by call_lock so a
    /// concurrent caller can never swallow someone else's response line.
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

        let mut stdout = self.stdout.lock().unwrap();
        let reader = stdout.as_mut().ok_or("engine not running")?;
        loop {
            // read_until + lossy conversion: device names may arrive in the
            // OEM code page from older engines — never abort the call on that.
            let mut raw = Vec::new();
            let n = reader.read_until(b'\n', &mut raw).map_err(|e| e.to_string())?;
            if n == 0 {
                drop(stdout);
                self.restart()?;
                return Err("engine died mid-call (restarted)".into());
            }
            let buf = String::from_utf8_lossy(&raw);
            let value: Value = match serde_json::from_str(buf.trim()) {
                Ok(v) => v,
                Err(_) => continue, // stray line on stdout — ignore
            };
            // skip notifications; match our request id
            if value.get("id").and_then(Value::as_u64) == Some(id) {
                if let Some(err) = value.get("error") {
                    return Err(err["message"].as_str().unwrap_or("engine error").to_string());
                }
                return Ok(value.get("result").cloned().unwrap_or(Value::Null));
            }
        }
    }
}
