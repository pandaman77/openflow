# OpenFlow — план проекта

Open-source, local-first голосовой диктовщик для Windows. Локальная альтернатива Wispr Flow.
Зажал хоткей → говоришь → отпустил → чистый текст вставлен в активное окно. Всё офлайн, без облака и платных API.

---

## 1. Реальность железа (по факту, не из головы)

| Что | Ноут (эта машина) | Стационарник (`ssh desktop`, .101) |
|-----|-------------------|-------------------------------------|
| CPU | AMD Ryzen 5 6600HS | мощное (по словам Коли) |
| GPU | Radeon 660M (нет CUDA) | предположительно есть — уточним |
| Rust/MSVC | НЕТ | уточним при первой сборке |
| Node/Python | есть | уточним |

**Вывод:** код пишем здесь, Python-ядро проверяем здесь же на CPU. Rust/Tauri-сборку и GUI-проверку — на стационарнике через `ssh desktop`.

---

## 2. Архитектура — гибрид Tauri/Rust + Python-сайдкар

faster-whisper (твой выбор) — это Python. Rust её напрямую не крутит. Поэтому индустриальный стандарт: Tauri/Rust — оболочка и системная интеграция, тяжёлый ML — в Python-сайдкаре.

```
+-------------------------------------------------------------+
|  Tauri Shell (Rust)                                         |
|  +--------------+   +--------------------------------------+ |
|  | React UI (TS)|   | Rust native layer                    | |
|  | - Tray       |<--| - global hotkeys (push-to-talk/toggle)| |
|  | - Overlay    |   | - clipboard                          | |
|  | - Settings   |   | - text insertion (SendInput+paste)   | |
|  | - Onboarding |   | - active window detection            | |
|  +--------------+   | - sidecar orchestration              | |
|                     +------------------+-------------------+ |
+----------------------------------------|--------------------+
                                         | JSON-RPC over stdio
                        +----------------v-------------------+
                        |  Python sidecar (openflow-engine)  |
                        |  - audio capture (sounddevice)     |
                        |  - Silero VAD                      |
                        |  - faster-whisper STT (auto device)|
                        |  - language detect (RU/EN/mixed)   |
                        |  - Fast cleanup (rules)            |
                        |  - Smart cleanup (llama.cpp LLM)   |
                        |  - snippets / commands / dictionary|
                        +------------------------------------+
```

**Почему аудио в Python, а не в Rust (как в ТЗ):** VAD и STT всё равно Python — держим аудио рядом, чтобы не гонять PCM между процессами. Меньше IPC, надёжнее. Rust отвечает за то, что он делает лучше: системные хоткеи, вставка текста, окна, tray/overlay.

---

## 3. Структура репозитория

```
OpenFlow/
├── apps/desktop/            # Tauri-приложение
│   ├── src/                 # React + TS + Tailwind + Zustand
│   │   ├── components/      # Overlay, TrayMenu, waveform
│   │   ├── views/           # Settings (10 табов), Onboarding wizard
│   │   ├── stores/          # Zustand
│   │   └── main.tsx
│   ├── src-tauri/           # Rust
│   │   └── src/ main.rs, hotkeys.rs, insertion.rs, clipboard.rs,
│   │            active_window.rs, sidecar.rs, tray.rs, commands.rs
│   ├── package.json, vite.config.ts, tauri.conf.json
├── core/openflow-engine/    # Python-сайдкар
│   └── openflow_engine/ __main__.py, ipc.py, audio.py, vad.py, stt.py,
│         language.py, config.py, snippets.py, commands.py, dictionary.py,
│         cleanup/ rules.py, llm.py, profiles.py
├── models/                  # манифесты моделей + скрипты (НЕ веса)
├── plugins/                 # примеры сниппетов/команд
├── scripts/                 # benchmark_stt.py, download_models.py, setup-dev.ps1
├── tests/                   # python (pytest) + rust
├── docs/                    # ARCHITECTURE, ROADMAP, PERFORMANCE, PRIVACY, INSTALL, CONTRIBUTING
├── .github/workflows/       # ci.yml, release.yml
├── README.md, LICENSE (MIT)
```
(`/ui` и `/native` из ТЗ не плодим пустыми — общее живёт в apps/desktop; выделим в отдельные крейты только если реально понадобится.)

---

## 4. Волны поставки (широкий каркас, но рабочее ядро — не заглушки)

Ты выбрал «широкий скелет сразу». Совмещаю с требованием ТЗ «minimize stubs, prioritize working functionality»: создаю ВСЕ модули, но Python-ядро делаю реально работающим end-to-end (его я могу тебе показать), а не TODO.

| Волна | Что | Где проверяю | Критерий готовности |
|-------|-----|--------------|---------------------|
| **0. Фундамент** | структура, git, все конфиги, каркас доков | ноут | `git init` ок; json/toml/yaml валидны |
| **1. Python-ядро** | ipc, audio, vad, stt (faster-whisper), rules-cleanup, language, snippets, commands, dictionary | **ноут (реально!)** | pytest зелёный; транскрипция wav→чистый текст работает вживую |
| **2. Smart cleanup** | llm.py (llama.cpp + мелкий GGUF), профили, download_models | ноут (если скачаем модель) | полировка работает; без модели — graceful fallback на rules |
| **3. Rust native** | hotkeys, insertion, clipboard, active_window, sidecar IPC, tray | **стационарник** (`ssh desktop`) | `cargo build` ок; ручная проверка Колей |
| **4. React UI** | Overlay, Settings (10 табов), Onboarding, stores | ноут (vite build) + стационарник (визуал) | `vite build` ок; визуал — твоя приёмка |
| **5. Упаковка + CI** | MSI, portable zip, updater, GitHub Actions | стационарник | workflow валидны; MSI собирается на .101 |
| **6. Тесты + бенчи + доки** | pytest, cargo tests, benchmark_stt, финал доков | оба | тесты зелёные; бенчмарк даёт цифры latency/точности |

---

## 5. Честные ограничения (чтобы без сюрпризов)

1. **GUI я «увидеть» не могу** ни на ноуте (нет Tauri toolchain), ни удалённо через SSH. Визуальную приёмку Overlay/Settings делаешь ты. Скриншоты могу получать только если запустим на машине с дисплеем и заскриним.
2. **MSI/CUDA-сборка — только на стационарнике.** Сначала проверю его toolchain (`ssh desktop`), если Rust/VS Build Tools там нет — поставим (через t8 из-за DPI).
3. **Веса моделей в git не кладём** — только манифесты + скрипт скачивания. Whisper base/small ~150–500 МБ, GGUF LLM ~0.5–1 ГБ.
4. **Это не «за один проход».** Реалистично — несколько сессий. Каждую волну закрываю проверкой и показываю тебе.

---

## 6. Что делаю сразу после твоего «ОК»

Волна 0 + Волна 1: фундамент репо + рабочее Python-ядро, которое я гоняю прямо здесь на ноуте и показываю тебе живую транскрипцию (wav → чистый текст) + прохождение pytest. Это первый осязаемый результат.
