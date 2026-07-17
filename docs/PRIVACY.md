# Privacy

OpenFlow is local-first by design:

- **Audio never leaves your machine.** Capture, VAD, transcription and text
  cleanup all run in local processes. Audio lives only in RAM for the
  duration of one utterance; it is never written to disk.
- **No telemetry, no analytics, no crash reporting.** Zero automatic network
  calls at runtime. The only network access is explicit and user-initiated:
  downloading a model (HuggingFace) and pressing "Check for updates" (which
  reads the GitHub releases API — nothing is sent, only a version is read).
- **Your data stays in %APPDATA%\OpenFlow**: config.json, snippets.json,
  dictionary.json. Plain JSON — read it, back it up, delete it anytime.
- **No accounts, no licenses, no phoning home.**

## One nuance: the clipboard

Insertion works by briefly placing the dictated text on the system clipboard,
pressing Ctrl+V, then restoring your previous clipboard (~300 ms later). During
that short window, clipboard managers (Windows Clipboard History, Ditto, etc.)
could capture the text — the same trade-off every paste-based dictation tool
makes. If that matters to you, disable clipboard history in Windows settings.
