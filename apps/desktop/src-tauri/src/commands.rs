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
    let result = engine.call(
        "stop_recording",
        json!({ "active_app": target_app }),
    )?;

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

#[tauri::command]
pub fn get_audio_level(engine: State<'_, Engine>) -> Result<Value, String> {
    engine.call("get_level", json!({}))
}
