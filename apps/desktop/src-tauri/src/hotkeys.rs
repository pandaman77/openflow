//! Hotkey wiring.
//!
//! Push-to-talk (hold Ctrl+Win by default) lives in hook.rs — the OS-level
//! RegisterHotKey API can't express modifier-only combos. The toggle
//! shortcut (press once / press again) goes through the shortcut plugin
//! and therefore needs a real key in the combo.

use tauri::{AppHandle, Manager};
use tauri_plugin_global_shortcut::{GlobalShortcutExt, Shortcut, ShortcutState};

use crate::sidecar::Engine;

pub const DEFAULT_PTT: &str = "ctrl+super";
// Not Ctrl+Win+Space: Windows reserves it (input-language switch), so
// RegisterHotKey always fails with "already registered".
pub const DEFAULT_TOGGLE: &str = "ctrl+alt+d";

pub fn register_defaults(app: &AppHandle) -> Result<(), String> {
    register_toggle(app, DEFAULT_TOGGLE)
}

pub fn register_toggle(app: &AppHandle, toggle: &str) -> Result<(), String> {
    let shortcuts = app.global_shortcut();
    shortcuts.unregister_all().map_err(|e| e.to_string())?;

    let toggle_shortcut: Shortcut = toggle
        .parse()
        .map_err(|e| format!("bad toggle hotkey: {e:?}"))?;

    shortcuts
        .on_shortcut(toggle_shortcut, move |app, _sc, event| {
            if event.state() == ShortcutState::Pressed {
                let app = app.clone();
                std::thread::spawn(move || {
                    let engine = app.state::<Engine>();
                    let started = engine
                        .call("start_recording", serde_json::json!({}))
                        .map(|v| v["already"].as_bool() != Some(true))
                        .unwrap_or(false);
                    if !started {
                        let engine = app.state::<Engine>();
                        let _ = crate::commands::stop_dictation(app.clone(), engine);
                    } else {
                        use tauri::Emitter;
                        let _ = app.emit("dictation:started", ());
                    }
                });
            }
        })
        .map_err(|e| e.to_string())?;

    Ok(())
}

#[tauri::command]
pub fn set_hotkeys(app: AppHandle, ptt: String, toggle: String) -> Result<(), String> {
    crate::hook::set_combo(&ptt)?;
    register_toggle(&app, &toggle)
}
