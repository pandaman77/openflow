// OpenFlow — local-first voice dictation for Windows.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod active_window;
mod commands;
mod hook;
mod hotkeys;
mod insertion;
mod sidecar;
mod tray;

use serde_json::json;
use tauri::Manager;

use sidecar::Engine;

fn main() {
    init_logging();

    tauri::Builder::default()
        // Only one OpenFlow at a time — a second launch just reveals the window.
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(main) = app.get_webview_window("main") {
                let _ = main.show();
                let _ = main.set_focus();
            }
        }))
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .plugin(tauri_plugin_clipboard_manager::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_autostart::init(
            tauri_plugin_autostart::MacosLauncher::LaunchAgent,
            None,
        ))
        .manage(Engine::new())
        .manage(commands::EngineStatus::default())
        .setup(|app| {
            let handle = app.handle().clone();

            tray::setup(&handle)?;

            // Engine start + model warm-up off the main thread: the tray must
            // appear instantly even while whisper loads.
            let engine_handle = handle.clone();
            std::thread::spawn(move || {
                let engine = engine_handle.state::<Engine>();
                if let Err(e) = engine.start() {
                    log::error!("engine start failed: {e}");
                    return;
                }
                use tauri::Emitter;
                match engine.call("initialize", json!({})) {
                    Ok(info) => {
                        log::info!("engine ready: {info}");
                        // store first (the UI polls this), then notify live windows
                        engine_handle.state::<commands::EngineStatus>().set(info.clone());
                        let _ = engine_handle.emit("engine:ready", info);
                    }
                    Err(e) => {
                        log::error!("engine initialize failed: {e}");
                        let _ = engine_handle.emit("engine:error", e);
                    }
                }
            });

            // PTT rides a low-level keyboard hook (supports modifier-only
            // combos like Ctrl+Win); the toggle uses the shortcut plugin.
            if let Err(e) = hook::install(handle.clone(), hotkeys::DEFAULT_PTT) {
                log::error!("ptt hook failed: {e}");
            }
            if let Err(e) = hotkeys::register_defaults(&handle) {
                log::error!("hotkey registration failed: {e}");
            }

            // Overlay pill: bottom-center above the taskbar, always visible,
            // click-through so it never steals input from the app below.
            if let Some(overlay) = app.get_webview_window("overlay") {
                if let Ok(Some(monitor)) = overlay.primary_monitor() {
                    let screen = monitor.size();
                    let win = overlay
                        .outer_size()
                        .unwrap_or(tauri::PhysicalSize::new(460, 72));
                    let x = (screen.width.saturating_sub(win.width)) as i32 / 2;
                    let y = screen.height.saturating_sub(win.height + 52) as i32;
                    let _ = overlay.set_position(tauri::PhysicalPosition::new(x, y));
                }
                let _ = overlay.set_ignore_cursor_events(true);
                let _ = overlay.show();
            }

            // First run: show the main window (onboarding); otherwise stay in tray.
            let first_run = !crate::first_run_marker().exists();
            if first_run {
                if let Some(main) = app.get_webview_window("main") {
                    let _ = main.show();
                }
                let _ = std::fs::create_dir_all(crate::first_run_marker().parent().unwrap());
                let _ = std::fs::write(crate::first_run_marker(), b"1");
            }

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::engine_call,
            commands::start_dictation,
            commands::stop_dictation,
            commands::cancel_dictation,
            commands::get_active_app,
            commands::get_audio_level,
            commands::get_engine_status,
            hotkeys::set_hotkeys,
        ])
        .on_window_event(|window, event| {
            // Closing the main window hides it to tray instead of quitting.
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                if window.label() == "main" {
                    let _ = window.hide();
                    api.prevent_close();
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running OpenFlow");
}

fn first_run_marker() -> std::path::PathBuf {
    let appdata = std::env::var("APPDATA").unwrap_or_default();
    std::path::PathBuf::from(appdata).join("OpenFlow").join(".initialized")
}

/// Shell logs go to %APPDATA%\OpenFlow\app.log — a GUI process has no
/// visible stderr, so without this the logs vanish.
fn init_logging() {
    let mut builder = env_logger::Builder::from_default_env();
    builder.filter_level(log::LevelFilter::Info);
    if let Ok(appdata) = std::env::var("APPDATA") {
        let dir = std::path::PathBuf::from(appdata).join("OpenFlow");
        let _ = std::fs::create_dir_all(&dir);
        if let Ok(file) = std::fs::File::create(dir.join("app.log")) {
            builder.target(env_logger::Target::Pipe(Box::new(file)));
        }
    }
    builder.init();
}
