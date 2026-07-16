//! System tray: status at a glance, quick access to settings, quit.

use tauri::menu::{Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::{TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Manager};

pub fn setup(app: &AppHandle) -> tauri::Result<()> {
    let show = MenuItem::with_id(app, "show", "Открыть OpenFlow", true, None::<&str>)?;
    let mode_fast = MenuItem::with_id(app, "mode_fast", "Режим: Быстрый (правила)", true, None::<&str>)?;
    let mode_smart = MenuItem::with_id(app, "mode_smart", "Режим: Умный (ИИ)", true, None::<&str>)?;
    let separator = PredefinedMenuItem::separator(app)?;
    let quit = MenuItem::with_id(app, "quit", "Выход", true, None::<&str>)?;

    let menu = Menu::with_items(app, &[&show, &separator, &mode_fast, &mode_smart, &separator, &quit])?;

    TrayIconBuilder::with_id("main-tray")
        .icon(app.default_window_icon().unwrap().clone())
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id.as_ref() {
            "show" => show_main(app),
            "quit" => {
                let engine = app.state::<crate::sidecar::Engine>();
                engine.stop();
                app.exit(0);
            }
            "mode_fast" | "mode_smart" => {
                let mode = if event.id.as_ref() == "mode_fast" { "fast" } else { "smart" };
                let engine = app.state::<crate::sidecar::Engine>();
                let _ = engine.call("set_config", serde_json::json!({"cleanup.mode": mode}));
            }
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::DoubleClick { .. } = event {
                show_main(tray.app_handle());
            }
        })
        .build(app)?;

    Ok(())
}

fn show_main(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
}
