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

#[tauri::command]
pub fn get_audio_level(engine: State<'_, Engine>) -> Result<Value, String> {
    engine.call("get_level", json!({}))
}

/// True for a portable install (a `portable.txt` next to the exe).
///
/// The updater installs through the NSIS bundle, which would drop a second
/// copy into %LOCALAPPDATA% instead of updating the folder the user actually
/// runs. Those installs get a download link rather than an update button.
#[tauri::command]
pub fn is_portable() -> bool {
    crate::paths::is_portable()
}

/// Is the pointer actually over the overlay right now?
///
/// The overlay resizes under the cursor (sliver -> pill -> recording pill), and
/// Windows does not reliably deliver a mouseleave when the window shrinks away
/// from a pointer that never moved. The React side would stay "hovered" forever
/// and keep the idle pill on screen after a dictation ended. Asking the OS is
/// the only answer that can't get stuck.
#[tauri::command]
pub fn cursor_over_overlay(app: AppHandle) -> bool {
    let Some(overlay) = app.get_webview_window("overlay") else {
        return false;
    };
    #[cfg(windows)]
    {
        use windows::Win32::Foundation::{HWND, POINT, RECT};
        use windows::Win32::UI::WindowsAndMessaging::{GetCursorPos, GetWindowRect};
        let Ok(handle) = overlay.hwnd() else {
            return false;
        };
        let raw = handle.0 as isize;
        unsafe {
            let mut point = POINT::default();
            let mut rect = RECT::default();
            if GetCursorPos(&mut point).is_err() || GetWindowRect(HWND(raw as _), &mut rect).is_err()
            {
                return false;
            }
            point.x >= rect.left && point.x < rect.right && point.y >= rect.top && point.y < rect.bottom
        }
    }
    #[cfg(not(windows))]
    {
        let _ = overlay;
        false
    }
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
        use windows::Win32::UI::WindowsAndMessaging::{SetWindowPos, HWND_TOPMOST, SWP_NOACTIVATE};
        let raw = overlay.hwnd().map_err(|e| e.to_string())?.0 as isize;
        unsafe {
            // HWND_TOPMOST, not NOZORDER: the pill must stay above everything.
            // The always-on-top flag alone only puts it in the topmost band —
            // another topmost window can still cover it, and it never climbs
            // back. Re-asserting the position on every fit keeps it on top.
            SetWindowPos(HWND(raw as _), HWND_TOPMOST, x, y, pw, ph, SWP_NOACTIVATE)
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
