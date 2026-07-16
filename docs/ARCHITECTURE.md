# Architecture

## Two processes, one contract

```
┌─────────────────────────────────────────────────────────────┐
│  OpenFlow.exe — Tauri shell (Rust + React)                  │
│                                                             │
│  React UI (webview)          Rust native layer              │
│  ├─ Home (status)            ├─ hotkeys.rs   global PTT/    │
│  ├─ Settings (10 tabs)       │               toggle keys    │
│  ├─ Onboarding wizard        ├─ insertion.rs clipboard-paste│
│  └─ Overlay (waveform)       │               + SendInput    │
│                              ├─ active_window.rs profiles   │
│                              ├─ tray.rs      tray menu      │
│                              ├─ commands.rs  UI<->engine    │
│                              └─ sidecar.rs   process mgmt   │
└──────────────────────────────┬──────────────────────────────┘
                               │ JSON-RPC 2.0, NDJSON over stdio
┌──────────────────────────────▼──────────────────────────────┐
│  openflow-engine — Python sidecar                           │
│                                                             │
│  ipc.py ── pipeline.py orchestrates:                        │
│    audio.py      sounddevice capture, 16 kHz mono f32       │
│    vad.py        cheap energy pre-check (Silero runs inside │
│                  faster-whisper as vad_filter)              │
│    stt.py        faster-whisper, auto CUDA→CPU fallback     │
│    language.py   RU/EN/mixed detection + sticky hint        │
│    commands.py   voice command detection (whole-utterance)  │
│    dictionary.py user vocabulary → initial_prompt + fixes   │
│    snippets.py   trigger phrase → expansion                 │
│    cleanup/                                                 │
│      rules.py    Fast mode: regex fillers/spacing/caps      │
│      llm.py      Smart mode: llama.cpp + small GGUF         │
│      profiles.py per-app style (coding/email/chat/...)      │
└─────────────────────────────────────────────────────────────┘
```

## Why a Python sidecar?

The best local STT stack (faster-whisper/CTranslate2) and the most portable
LLM runtime bindings (llama-cpp-python) are Python. Rust does what Rust is
best at: instant global hotkeys, synthetic input, window management, a tiny
resident footprint. The contract between them is ~12 JSON-RPC methods
(see `ipc.py` docstring), so either side can be swapped independently —
e.g. a future whisper.cpp Rust engine would implement the same methods.

## Dictation flow (push-to-talk)

1. `hotkeys.rs` catches the key-down → `start_recording` RPC → mic buffering
   starts (<150 ms); overlay window shows.
2. Key-up → `stop_recording` RPC on a worker thread.
3. Engine: energy VAD gate → faster-whisper (with personal-dictionary
   initial_prompt) → command detection → dictionary replacements → snippet
   expansion → cleanup (fast rules / smart LLM with fast fallback).
4. Shell: result type `text` → clipboard-paste insertion into the focused
   app (clipboard saved/restored); `command` → native action (undo, newline…).

## Failure policy

- No CUDA → CPU int8, transparently.
- No GGUF / llama-cpp not installed → smart mode falls back to fast rules.
- LLM translates or balloons the text → output rejected, fast fallback.
- Engine process dies → shell restarts it on next call.
- Corrupt config/snippets/dictionary JSON → defaults, never a crash.

## Latency budget (targets)

| Stage | Target |
|---|---|
| hotkey → recording | < 150 ms |
| release → text (small, GPU) | < 1 s |
| release → text (small, CPU int8) | ~1-4 s depending on utterance |
| fast cleanup | < 5 ms |
| smart cleanup (1.5B q4, CPU) | +1-3 s |
