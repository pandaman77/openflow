//! Tauri commands: the bridge between the React UI / hotkey handlers
//! and the Python engine + native layer.

use serde_json::{json, Value};
use tauri::{AppHandle, Emitter, Manager, State};

use crate::active_window::active_process_name;
use crate::insertion;
use crate::sidecar::Engine;

/// Last known engine readiness, filled once initialize succeeds. The UI polls
/// this instead of relying on the one-shot `engine:ready` event, which a
/// window opened after startup would miss.
#[derive(Default)]
pub struct EngineStatus(pub std::sync::Mutex<Option<Value>>);

impl EngineStatus {
    pub fn set(&self, info: Value) {
        *self.0.lock().unwrap() = Some(info);
    }
}

/// Returns the engine info once ready, or null while it's still warming up.
#[tauri::command]
pub fn get_engine_status(status: State<'_, EngineStatus>) -> Option<Value> {
    status.0.lock().unwrap().clone()
}

#[tauri::command]
pub fn engine_call(engine: State<'_, Engine>, method: String, params: Value) -> Result<Value, String> {
    engine.call(&method, params)
}

#[tauri::command]
pub fn start_dictation(app: AppHandle, engine: State<'_, Engine>) -> Result<(), String> {
    engine.call("start_recording", json!({}))?;
    // the overlay pill is always visible; just make sure it wasn't closed
    if let Some(overlay) = app.get_webview_window("overlay") {
        let _ = overlay.show();
    }
    let _ = app.emit("dictation:started", ());
    Ok(())
}

#[tauri::command]
pub fn stop_dictation(app: AppHandle, engine: State<'_, Engine>) -> Result<Value, String> {
    let target_app = active_process_name();
    let _ = app.emit("dictation:processing", ());
    let result = match engine.call("stop_recording", json!({ "active_app": target_app })) {
        Ok(v) => v,
        Err(e) => {
            // never leave the UI stuck in "processing" — always close the cycle
            log::error!("stop_recording failed: {e}");
            let _ = app.emit("dictation:finished", json!({"type": "empty", "error": e}));
            return Err(e);
        }
    };

    match result["type"].as_str() {
        Some("text") => {
            let text = result["text"].as_str().unwrap_or_default();
            if !text.is_empty() {
                insertion::insert_text(&app, text, true)?;
            }
        }
        Some("command") => {
            handle_voice_command(&app, result["action"].as_str().unwrap_or_default())?;
        }
        _ => {} // empty — nothing to insert
    }
    let _ = app.emit("dictation:finished", result.clone());
    Ok(result)
}

#[tauri::command]
pub fn cancel_dictation(app: AppHandle, engine: State<'_, Engine>) -> Result<(), String> {
    engine.call("cancel_recording", json!({}))?;
    let _ = app.emit("dictation:cancelled", ());
    Ok(())
}

fn handle_voice_command(app: &AppHandle, action: &str) -> Result<(), String> {
    match action {
        "undo" => {
            #[cfg(windows)]
            insertion::send_undo();
        }
        "new_paragraph" => insertion::insert_text(app, "\n\n", false)?,
        "new_line" => insertion::insert_text(app, "\n", false)?,
        "bullet_list" => insertion::insert_text(app, "\n- ", false)?,
        // redo/delete_last_sentence/select_all/LLM transforms:
        // emitted to the UI layer which may show a hint or run engine transforms
        other => {
            let _ = app.emit("voice-command", other.to_string());
        }
    }
    Ok(())
}

#[tauri::command]
pub fn get_active_app() -> Option<String> {
    active_process_name()
}

/// Bring up the main window — used when the overlay pill is clicked.
#[tauri::command]
pub fn open_main(app: AppHandle) {
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.show();
        let _ = w.unminimize();
        let _ = w.set_focus();
    }
}

/// Ask GitHub for the latest release and compare it to the running version.
/// Notification-only: we never auto-download, just point the user at the page.
#[tauri::command]
pub fn check_update() -> Result<Value, String> {
    const REPO: &str = "pandaman77/openflow";
    let current = env!("CARGO_PKG_VERSION");
    let url = format!("https://api.github.com/repos/{REPO}/releases/latest");

    let resp = ureq::get(&url)
        .set("User-Agent", "OpenFlow-updater")
        .timeout(std::time::Duration::from_secs(8))
        .call()
        .map_err(|e| format!("не удалось проверить обновления: {e}"))?;
    let body: Value = resp.into_json().map_err(|e| e.to_string())?;

    let latest = body["tag_name"].as_str().unwrap_or("").trim_start_matches('v');
    let html_url = body["html_url"].as_str().unwrap_or("");
    let available = !latest.is_empty() && version_gt(latest, current);

    Ok(json!({
        "current": current,
        "latest": latest,
        "update_available": available,
        "url": html_url,
    }))
}

/// Open a URL in the user's default browser (used for the release page).
#[tauri::command]
pub fn open_url(url: String) -> Result<(), String> {
    // only allow our own https release links, never arbitrary schemes
    if !url.starts_with("https://github.com/") {
        return Err("refused to open non-release URL".into());
    }
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        std::process::Command::new("cmd")
            .args(["/C", "start", "", &url])
            .creation_flags(0x0800_0000)
            .spawn()
            .map_err(|e| e.to_string())?;
    }
    Ok(())
}

/// True if `a` is a higher semver-ish version than `b` (numeric dotted compare).
fn version_gt(a: &str, b: &str) -> bool {
    let parse = |s: &str| -> Vec<u32> {
        s.split('.').map(|p| p.parse().unwrap_or(0)).collect()
    };
    let (va, vb) = (parse(a), parse(b));
    for i in 0..va.len().max(vb.len()) {
        let (x, y) = (va.get(i).copied().unwrap_or(0), vb.get(i).copied().unwrap_or(0));
        if x != y {
            return x > y;
        }
    }
    false
}

#[tauri::command]
pub fn get_audio_level(engine: State<'_, Engine>) -> Result<Value, String> {
    engine.call("get_level", json!({}))
}

/// Move + resize the overlay to its bottom-center spot in ONE native call.
/// Two separate setSize/setPosition IPC calls let Windows paint the window at
/// an intermediate rect (old position, new size) — a visible stretched flash
/// on every hover expand/collapse.
#[tauri::command]
pub fn fit_overlay(app: AppHandle, w: f64, h: f64) -> Result<(), String> {
    let overlay = app
        .get_webview_window("overlay")
        .ok_or("overlay window missing")?;
    let monitor = overlay
        .current_monitor()
        .map_err(|e| e.to_string())?
        .ok_or("no monitor")?;
    let scale = monitor.scale_factor();
    let msize = monitor.size();
    let mpos = monitor.position();
    let pw = (w * scale).round() as i32;
    let ph = (h * scale).round() as i32;
    let x = mpos.x + (msize.width as i32 - pw) / 2;
    // sit above the taskbar (same 56px gap the JS math used)
    let y = mpos.y + msize.height as i32 - ph - (56.0 * scale).round() as i32;

    #[cfg(windows)]
    {
        use windows::Win32::Foundation::HWND;
        use windows::Win32::UI::WindowsAndMessaging::{
            SetWindowPos, SWP_NOACTIVATE, SWP_NOZORDER,
        };
        let raw = overlay.hwnd().map_err(|e| e.to_string())?.0 as isize;
        unsafe {
            SetWindowPos(HWND(raw as _), HWND::default(), x, y, pw, ph, SWP_NOZORDER | SWP_NOACTIVATE)
                .map_err(|e| e.to_string())?;
        }
    }
    #[cfg(not(windows))]
    {
        let _ = overlay.set_size(tauri::PhysicalSize::new(pw.max(1) as u32, ph.max(1) as u32));
        let _ = overlay.set_position(tauri::PhysicalPosition::new(x, y));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::version_gt;

    #[test]
    fn newer_versions_win() {
        assert!(version_gt("0.2.0", "0.1.0"));
        assert!(version_gt("1.0.0", "0.9.9"));
        assert!(version_gt("0.1.1", "0.1.0"));
    }

    #[test]
    fn equal_or_older_do_not() {
        assert!(!version_gt("0.1.0", "0.1.0"));
        assert!(!version_gt("0.1.0", "0.1")); // trailing zero == missing
        assert!(!version_gt("0.1.0", "0.2.0"));
        assert!(!version_gt("0.9.9", "1.0.0"));
    }
}
