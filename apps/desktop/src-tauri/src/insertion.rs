//! Text insertion into the focused control of any application.
//!
//! Strategy (same as Wispr Flow and friends):
//! 1. Save clipboard, put text on it, send Ctrl+V, restore clipboard.
//!    Fast, works everywhere including terminals and Electron apps.
//! 2. `SendInput` with `KEYEVENTF_UNICODE` as a fallback for apps that
//!    block synthetic paste (some elevated windows, secure fields).

use std::thread::sleep;
use std::time::Duration;

#[cfg(windows)]
use windows::Win32::UI::Input::KeyboardAndMouse::{
    SendInput, INPUT, INPUT_0, INPUT_KEYBOARD, KEYBDINPUT, KEYBD_EVENT_FLAGS,
    KEYEVENTF_KEYUP, KEYEVENTF_UNICODE, VIRTUAL_KEY, VK_CONTROL, VK_V,
};

#[cfg(windows)]
fn key_event(vk: VIRTUAL_KEY, scan: u16, flags: KEYBD_EVENT_FLAGS) -> INPUT {
    INPUT {
        r#type: INPUT_KEYBOARD,
        Anonymous: INPUT_0 {
            ki: KEYBDINPUT {
                wVk: vk,
                wScan: scan,
                dwFlags: flags,
                time: 0,
                dwExtraInfo: 0,
            },
        },
    }
}

/// Send Ctrl+V to the foreground window.
#[cfg(windows)]
pub fn send_paste() {
    let inputs = [
        key_event(VK_CONTROL, 0, KEYBD_EVENT_FLAGS(0)),
        key_event(VK_V, 0, KEYBD_EVENT_FLAGS(0)),
        key_event(VK_V, 0, KEYEVENTF_KEYUP),
        key_event(VK_CONTROL, 0, KEYEVENTF_KEYUP),
    ];
    unsafe {
        SendInput(&inputs, std::mem::size_of::<INPUT>() as i32);
    }
}

/// Type text character-by-character via KEYEVENTF_UNICODE.
/// Slower than paste but immune to clipboard interference.
#[cfg(windows)]
pub fn type_unicode(text: &str) {
    for unit in text.encode_utf16() {
        let inputs = [
            key_event(VIRTUAL_KEY(0), unit, KEYEVENTF_UNICODE),
            key_event(VIRTUAL_KEY(0), unit, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP),
        ];
        unsafe {
            SendInput(&inputs, std::mem::size_of::<INPUT>() as i32);
        }
        // tiny pacing so slow apps (RDP, Java UIs) don't drop events
        sleep(Duration::from_micros(500));
    }
}

/// Insert text into the currently focused field.
/// `via_clipboard`: paste (default) or unicode typing.
pub fn insert_text(
    app: &tauri::AppHandle,
    text: &str,
    via_clipboard: bool,
) -> Result<(), String> {
    #[cfg(windows)]
    {
        use tauri_plugin_clipboard_manager::ClipboardExt;

        if via_clipboard {
            let clipboard = app.clipboard();
            let saved = clipboard.read_text().ok(); // may be empty/non-text
            clipboard
                .write_text(text.to_string())
                .map_err(|e| e.to_string())?;
            // give the clipboard a beat to settle before the paste keystroke
            sleep(Duration::from_millis(30));
            send_paste();
            // restore after the target app has consumed the paste
            if let Some(prev) = saved {
                let app = app.clone();
                std::thread::spawn(move || {
                    sleep(Duration::from_millis(300));
                    let _ = app.clipboard().write_text(prev);
                });
            }
        } else {
            type_unicode(text);
        }
        Ok(())
    }
    #[cfg(not(windows))]
    {
        let _ = (app, text, via_clipboard);
        Err("text insertion is Windows-only for now".into())
    }
}

/// Simulate app-level undo (Ctrl+Z) — used by the "undo" voice command.
#[cfg(windows)]
pub fn send_undo() {
    use windows::Win32::UI::Input::KeyboardAndMouse::VK_Z;
    let inputs = [
        key_event(VK_CONTROL, 0, KEYBD_EVENT_FLAGS(0)),
        key_event(VK_Z, 0, KEYBD_EVENT_FLAGS(0)),
        key_event(VK_Z, 0, KEYEVENTF_KEYUP),
        key_event(VK_CONTROL, 0, KEYEVENTF_KEYUP),
    ];
    unsafe {
        SendInput(&inputs, std::mem::size_of::<INPUT>() as i32);
    }
}
