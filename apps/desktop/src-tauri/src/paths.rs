//! Where OpenFlow keeps its data.
//!
//! Portable mode: a `portable.txt` next to the exe switches everything
//! (config, logs, first-run marker, WebView2 profile, downloaded models)
//! to `<exe dir>\data`, so the whole app lives in one movable folder.
//! Otherwise data goes to `%APPDATA%\OpenFlow` as before.

use std::path::PathBuf;

pub fn exe_dir() -> Option<PathBuf> {
    std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(|d| d.to_path_buf()))
}

pub fn is_portable() -> bool {
    exe_dir()
        .map(|d| d.join("portable.txt").exists())
        .unwrap_or(false)
}

/// The single root for all mutable app data. Never fails: worst case it
/// degrades to a relative path, which still lets the app start.
pub fn data_dir() -> PathBuf {
    if is_portable() {
        if let Some(dir) = exe_dir() {
            return dir.join("data");
        }
    }
    let appdata = std::env::var_os("APPDATA").unwrap_or_default();
    PathBuf::from(appdata).join("OpenFlow")
}
