//! Low-level keyboard hook (WH_KEYBOARD_LL) for push-to-talk.
//!
//! RegisterHotKey cannot express modifier-only combos like Ctrl+Win, so PTT
//! is driven by a global hook instead: when every key of the combo is down,
//! recording starts; as soon as any of them is released, it stops. The hook
//! callback only updates key state and posts to a worker thread — it must
//! return fast or Windows silently removes the hook.

use std::collections::HashSet;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{mpsc, Mutex, OnceLock};

use tauri::{AppHandle, Manager};

use crate::sidecar::Engine;

#[cfg(windows)]
use windows::Win32::{
    Foundation::{LPARAM, LRESULT, WPARAM},
    UI::WindowsAndMessaging::{
        CallNextHookEx, GetMessageW, SetWindowsHookExW, KBDLLHOOKSTRUCT, MSG,
        WH_KEYBOARD_LL, WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP,
    },
};

/// One combo member matches any of its virtual-key alternatives (L/R variants).
type Combo = Vec<Vec<u32>>;

static COMBO: Mutex<Option<Combo>> = Mutex::new(None);
static PRESSED: Mutex<Option<HashSet<u32>>> = Mutex::new(None);
static ACTIVE: AtomicBool = AtomicBool::new(false);
static EVENTS: OnceLock<mpsc::Sender<bool>> = OnceLock::new();

/// "ctrl+super" -> [[VK_LCONTROL, VK_RCONTROL], [VK_LWIN, VK_RWIN]]
pub fn parse_combo(spec: &str) -> Result<Combo, String> {
    let mut combo = Vec::new();
    for part in spec.split('+').map(|p| p.trim().to_lowercase()) {
        let alternatives: Vec<u32> = match part.as_str() {
            "ctrl" | "control" => vec![0xA2, 0xA3],
            "super" | "win" | "meta" | "cmd" => vec![0x5B, 0x5C],
            "alt" => vec![0xA4, 0xA5],
            "shift" => vec![0xA0, 0xA1],
            "space" => vec![0x20],
            "tab" => vec![0x09],
            "capslock" => vec![0x14],
            k if k.len() == 1 && k.chars().next().unwrap().is_ascii_alphanumeric() => {
                vec![k.to_uppercase().chars().next().unwrap() as u32]
            }
            k if k.starts_with('f') && k[1..].parse::<u32>().map_or(false, |n| (1..=24).contains(&n)) => {
                vec![0x6F + k[1..].parse::<u32>().unwrap()]
            }
            other => return Err(format!("unknown key {other:?}")),
        };
        combo.push(alternatives);
    }
    if combo.is_empty() {
        return Err("empty combo".into());
    }
    Ok(combo)
}

pub fn set_combo(spec: &str) -> Result<(), String> {
    let combo = parse_combo(spec)?;
    *COMBO.lock().unwrap() = Some(combo);
    Ok(())
}

#[cfg(windows)]
unsafe extern "system" fn hook_proc(code: i32, wparam: WPARAM, lparam: LPARAM) -> LRESULT {
    if code >= 0 {
        let kb = &*(lparam.0 as *const KBDLLHOOKSTRUCT);
        let vk = kb.vkCode;
        let down = matches!(wparam.0 as u32, WM_KEYDOWN | WM_SYSKEYDOWN);
        let up = matches!(wparam.0 as u32, WM_KEYUP | WM_SYSKEYUP);

        if down || up {
            let combo_guard = COMBO.lock().unwrap();
            if let Some(combo) = combo_guard.as_ref() {
                let relevant = combo.iter().flatten().any(|&k| k == vk);
                if relevant {
                    let mut pressed_guard = PRESSED.lock().unwrap();
                    let pressed = pressed_guard.get_or_insert_with(HashSet::new);
                    if down {
                        pressed.insert(vk);
                    } else {
                        pressed.remove(&vk);
                    }
                    let all_down = combo
                        .iter()
                        .all(|alts| alts.iter().any(|k| pressed.contains(k)));
                    let was_active = ACTIVE.load(Ordering::SeqCst);
                    if all_down && !was_active {
                        ACTIVE.store(true, Ordering::SeqCst);
                        log::info!("ptt combo pressed");
                        if let Some(tx) = EVENTS.get() {
                            let _ = tx.send(true);
                        }
                    } else if !all_down && was_active {
                        ACTIVE.store(false, Ordering::SeqCst);
                        log::info!("ptt combo released");
                        if let Some(tx) = EVENTS.get() {
                            let _ = tx.send(false);
                        }
                    }
                }
            }
        }
    }
    CallNextHookEx(None, code, wparam, lparam)
}

/// Install the hook thread + the worker that talks to the engine.
#[cfg(windows)]
pub fn install(app: AppHandle, ptt_spec: &str) -> Result<(), String> {
    set_combo(ptt_spec)?;

    let (tx, rx) = mpsc::channel::<bool>();
    EVENTS.set(tx).map_err(|_| "hook already installed")?;

    // worker: engine calls happen here, never inside the hook callback
    std::thread::spawn(move || {
        while let Ok(start) = rx.recv() {
            let engine = app.state::<Engine>();
            if start {
                log::info!("ptt -> start_dictation");
                if let Err(e) = crate::commands::start_dictation(app.clone(), engine) {
                    log::error!("start_dictation failed: {e}");
                }
            } else {
                log::info!("ptt -> stop_dictation");
                let engine = app.state::<Engine>();
                if let Err(e) = crate::commands::stop_dictation(app.clone(), engine) {
                    log::error!("stop_dictation failed: {e}");
                }
            }
        }
    });

    // hook thread: needs its own message loop
    std::thread::spawn(|| unsafe {
        match SetWindowsHookExW(WH_KEYBOARD_LL, Some(hook_proc), None, 0) {
            Ok(_hook) => {
                log::info!("keyboard hook installed");
                let mut msg = MSG::default();
                while GetMessageW(&mut msg, None, 0, 0).as_bool() {}
            }
            Err(e) => log::error!("keyboard hook failed: {e}"),
        }
    });

    Ok(())
}

#[cfg(not(windows))]
pub fn install(_app: AppHandle, _ptt_spec: &str) -> Result<(), String> {
    Err("keyboard hook is Windows-only".into())
}

#[cfg(all(test, windows))]
mod tests {
    use super::parse_combo;

    #[test]
    fn parses_ctrl_super() {
        let c = parse_combo("ctrl+super").unwrap();
        assert_eq!(c.len(), 2);
        assert!(c[0].contains(&0xA2)); // either L/R control
        assert!(c[1].contains(&0x5B)); // either L/R win
    }

    #[test]
    fn parses_letters_and_fkeys() {
        assert!(parse_combo("ctrl+alt+d").is_ok());
        assert!(parse_combo("f5").is_ok());
        assert!(parse_combo("shift+space").is_ok());
    }

    #[test]
    fn rejects_unknown_and_empty() {
        assert!(parse_combo("ctrl+wat").is_err());
        assert!(parse_combo("").is_err());
    }
}
