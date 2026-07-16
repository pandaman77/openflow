# OpenFlow

**Open-source, local-first voice dictation layer for Windows.**
A free alternative to [Wispr Flow](https://wisprflow.ai/) that runs 100% on your machine — no cloud, no subscriptions, no data leaving your PC.

![platform](https://img.shields.io/badge/platform-Windows%2010%2F11-0b7ec2)
![license](https://img.shields.io/badge/license-MIT-green)
![local](https://img.shields.io/badge/inference-100%25%20local-f2a35c)

Hold a hotkey → speak naturally → release → polished text appears in whatever app you're using. Cursor, VS Code, browsers, Telegram, Word, terminals — anywhere.

## Download

Grab the latest installer from the [**Releases**](../../releases) page (`OpenFlow_x64-setup.exe`).
On first launch a short wizard picks your microphone and downloads the speech model (~500 MB, once).

- Hold **Ctrl + Win**, speak, release — the text lands where your cursor is.
- Everything runs on your machine. NVIDIA GPU is used automatically if present; otherwise it runs on CPU.

## How it works

```
┌──────────────────────────────────────────────────────┐
│  Tauri Shell (Rust)                                  │
│  tray · overlay · settings UI (React)                │
│  global hotkeys · text insertion · window detection  │
└──────────────────────┬───────────────────────────────┘
                       │ JSON-RPC over stdio
┌──────────────────────▼───────────────────────────────┐
│  Python Engine (sidecar)                             │
│  mic capture · Silero VAD · faster-whisper STT       │
│  RU/EN + mixed language · Fast/Smart text cleanup    │
│  snippets · voice commands · personal dictionary     │
└──────────────────────────────────────────────────────┘
```

- **Fast mode** — rule-based cleanup (fillers, spacing, capitalization). Near-zero added latency.
- **Smart mode** — local LLM polishing via llama.cpp (punctuation, formatting, style). Fully offline.

## Status

Working alpha. End-to-end dictation runs today: capture → VAD → faster-whisper → cleanup → insertion, with a system tray, an always-on overlay, global push-to-talk, and a settings UI. CUDA (int8) and CPU are both supported. See [docs/ROADMAP.md](docs/ROADMAP.md) for what's next.

## Repository layout

| Path | What |
|------|------|
| `apps/desktop/` | Tauri app: React UI + Rust native layer |
| `core/openflow-engine/` | Python sidecar: audio, VAD, STT, cleanup |
| `models/` | Model manifests + download scripts (weights are not committed) |
| `plugins/` | Example snippets and command packs |
| `scripts/` | Dev setup, benchmarks, model downloads |
| `tests/` | Python and Rust tests |
| `docs/` | Architecture, roadmap, performance, privacy |

## Quick start (engine only, for now)

```powershell
cd core/openflow-engine
python -m venv .venv
.venv\Scripts\pip install -e .[dev]
.venv\Scripts\python -m openflow_engine --selftest
```

## Privacy

Everything runs locally. No telemetry, no network calls at runtime (model downloads are explicit and one-time). See [docs/PRIVACY.md](docs/PRIVACY.md).

## License

MIT
