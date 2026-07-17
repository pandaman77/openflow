# Third-party notices

OpenFlow is MIT-licensed. It builds on the following open-source components,
each under its own permissive license. This file is a courtesy summary; the
authoritative license text ships with each dependency.

## Runtime engine (Python)

| Component | License | Role |
|-----------|---------|------|
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | MIT | speech-to-text |
| [CTranslate2](https://github.com/OpenNMT/CTranslate2) | MIT | inference backend |
| [sounddevice](https://github.com/spatialaudio/python-sounddevice) | MIT | microphone capture |
| [NumPy](https://github.com/numpy/numpy) | BSD-3-Clause | audio math |
| [llama-cpp-python](https://github.com/abetlen/llama-cpp-python) | MIT | optional smart-cleanup LLM |

## Desktop shell (Rust / Tauri)

| Component | License |
|-----------|---------|
| [Tauri](https://github.com/tauri-apps/tauri) and plugins | MIT / Apache-2.0 |
| [windows-rs](https://github.com/microsoft/windows-rs) | MIT / Apache-2.0 |
| serde, serde_json, log, env_logger, ureq | MIT / Apache-2.0 |

## UI (TypeScript)

| Component | License |
|-----------|---------|
| [React](https://github.com/facebook/react) | MIT |
| [Zustand](https://github.com/pmndrs/zustand) | MIT |
| [Tailwind CSS](https://github.com/tailwindlabs/tailwindcss) | MIT |
| [Vite](https://github.com/vitejs/vite) | MIT |

## Models (downloaded on first run, not bundled)

- **Whisper** weights — MIT (OpenAI).
- **Qwen2.5-Instruct** (smart-cleanup, optional) — the 0.5B/1.5B sizes are
  Apache-2.0. Larger sizes (3B, 72B) use the separate Tongyi Qianwen License;
  check it before shipping those.

No component here is GPL/AGPL-licensed, so OpenFlow's own MIT license imposes
no copyleft obligations.
