// OpenFlow — local-first voice dictation for Windows.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod active_window;
mod commands;
mod hook;
mod hotkeys;
mod insertion;
mod paths;
mod sidecar;
mod tray;

use serde_json::json;
use tauri::Manager;

use sidecar::Engine;

fn main() {
    init_logging();

    // Chromium stops painting a window it believes is covered, and it gets that
    // wrong for a 72x16 transparent sliver: after sleep or a lock screen the
    // overlay's webview goes dark for good. No frames means no rAF, which
    // strands the React resize chain and leaves the pill invisible while the
    // app itself keeps working. Turning the check off keeps the overlay alive.
    std::env::set_var(
        "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS",
        "--disable-features=CalculateNativeWinOcclusion",
    );

    // Portable mode: keep the WebView2 profile (localStorage etc.) inside
    // the app folder too. Must be set before the first webview is created.
    if paths::is_portable() {
        let webview_dir = paths::data_dir().join("webview");
        let _ = std::fs::create_dir_all(&webview_dir);
        std::env::set_var("WEBVIEW2_USER_DATA_FOLDER", &webview_dir);
    }

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

            // Overlay: a small always-on sliver at the bottom-center that the
            // React side resizes/repositions per state. It stays a real (not
            // click-through) window so it can react to hover, but it's only as
            // big as its visible pixels — clicks elsewhere hit the app behind.
            // It starts hidden (visible:false) and the React side shows it only
            // AFTER sizing+positioning, so it never flashes at the default spot.

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
            commands::check_update,
            commands::open_url,
            commands::open_main,
            commands::fit_overlay,
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
    paths::data_dir().join(".initialized")
}

/// Shell logs go to <data dir>\app.log — a GUI process has no
/// visible stderr, so without this the logs vanish.
fn init_logging() {
    let mut builder = env_logger::Builder::from_default_env();
    builder.filter_level(log::LevelFilter::Info);
    let dir = paths::data_dir();
    let _ = std::fs::create_dir_all(&dir);
    if let Ok(file) = std::fs::File::create(dir.join("app.log")) {
        builder.target(env_logger::Target::Pipe(Box::new(file)));
    }
    builder.init();
}
