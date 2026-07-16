# Privacy

OpenFlow is local-first by design:

- **Audio never leaves your machine.** Capture, VAD, transcription and text
  cleanup all run in local processes. Audio lives only in RAM for the
  duration of one utterance; it is never written to disk.
- **No telemetry, no analytics, no crash reporting.** Zero network calls at
  runtime. The only network access is the explicit, user-initiated download
  of models (HuggingFace) and the optional update check (GitHub releases).
- **Your data stays in %APPDATA%\OpenFlow**: config.json, snippets.json,
  dictionary.json. Plain JSON — read it, back it up, delete it anytime.
- **No accounts, no licenses, no phoning home.**

The updater can be disabled entirely in Settings → Privacy.
