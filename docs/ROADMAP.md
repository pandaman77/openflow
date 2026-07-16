# Roadmap

## v0.1 — core engine (done)
- [x] Python engine: capture → VAD → faster-whisper → cleanup
- [x] Fast mode (rules) + Smart mode (local LLM, graceful fallback)
- [x] Snippets, voice commands, personal dictionary, context profiles
- [x] RU/EN/mixed dictation
- [x] JSON-RPC sidecar protocol + tests

## v0.2 — desktop shell (code written, stabilizing)
- [ ] Tauri build verified on a real machine (tray, hotkeys, insertion)
- [ ] Overlay waveform polish
- [ ] Onboarding wizard with model download
- [ ] MSI/NSIS installers via CI

## v0.3 — power features
- [ ] Streaming partial transcription in overlay
- [ ] Snippet/dictionary editors in Settings UI
- [ ] Custom voice commands UI
- [ ] Auto-learning vocabulary (frequency-based suggestions)
- [ ] Whisper large-v3-turbo preset for GPU machines

## v0.4 — beyond Wispr Flow
- [ ] Whispered-speech mode (low-volume profiles)
- [ ] Per-app language pinning
- [ ] Local history with full-text search (opt-in)
- [ ] Plugin API for command handlers
- [ ] Benchmark-driven model auto-selection in onboarding
