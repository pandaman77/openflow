# Contributing

- Engine (Python 3.10+): `core/openflow-engine`. Tests in `tests/python`,
  run `pytest tests/python -q` from the repo root. Keep modules dependency-light:
  faster-whisper, numpy, sounddevice; llama-cpp-python stays optional.
- Shell (Rust, Tauri 2): `apps/desktop/src-tauri`. `cargo fmt` + `cargo clippy`.
- UI (React + TS + Tailwind): `apps/desktop/src`. `npm run build` must pass
  (tsc strict).
- One feature per PR, with tests for engine changes.
- The IPC contract (`ipc.py` docstring) is the API between worlds — change it
  in both places and document it.
