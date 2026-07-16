# Install

## Users

Grab the latest MSI (or portable ZIP) from GitHub Releases and run it.
On first launch the onboarding wizard picks a microphone, downloads the
STT model (~500 MB for `small`) and tests dictation.

Requirements: Windows 10/11 x64, 8 GB RAM. NVIDIA GPU optional (CUDA 12
runtime) — everything works on CPU, just slower.

## Developers

```powershell
# 1. Engine
cd core/openflow-engine
python -m venv .venv
.venv\Scripts\pip install -e .[dev]
.venv\Scripts\python -m pytest ../../tests/python -q     # unit tests
.venv\Scripts\python -m openflow_engine --selftest       # offline check

# optional: smart mode
.venv\Scripts\pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
python ../../scripts/download_models.py --llm qwen2.5-1.5b-instruct-q4

# 2. Frontend
cd ../../apps/desktop
npm install
npm run build

# 3. Desktop app (needs Rust + VS Build Tools)
$env:OPENFLOW_ENGINE_CMD = "<repo>\core\openflow-engine\.venv\Scripts\python.exe -m openflow_engine"
npx tauri dev
```
