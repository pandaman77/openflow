"""Build the portable distribution of OpenFlow.

Takes the already-built shell exe (npx tauri build) and the PyInstaller
engine sidecar, lays them out in a self-contained folder and zips it:

    OpenFlow-Portable-<version>/
        OpenFlow.exe          <- apps/desktop/src-tauri/target/release/openflow.exe
        openflow-engine.exe   <- apps/desktop/src-tauri/binaries/openflow-engine-*.exe
        portable.txt          <- marker: the app keeps all data in .\\data
        README.txt

The exe must come from `npx tauri build` (a bare `cargo build --release`
lacks the custom-protocol feature and shows a blank window).

Usage: python scripts/make_portable.py
"""

from __future__ import annotations

import json
import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TAURI = REPO / "apps" / "desktop" / "src-tauri"

PORTABLE_TXT = """\
OpenFlow portable mode.

Этот файл — маркер портативного режима. Пока он лежит рядом с OpenFlow.exe,
все данные (настройки, логи, словарь, сниппеты, скачанные модели) хранятся
в папке .\\data рядом с программой, а не в %APPDATA%.

Удалите этот файл — и приложение снова будет вести себя как установленное.
"""

README_TXT = """\
OpenFlow — локальная голосовая диктовка для Windows (портативная версия)

Запуск: распакуйте папку в короткий путь (например C:\\OpenFlow)
и откройте OpenFlow.exe. Установка не нужна.

Важно: не кладите папку слишком глубоко. Если полный путь к ней
длиннее ~180 символов, Windows не даст скачать модель распознавания
(ограничение длины пути MAX_PATH).

Диктовка: зажмите Ctrl+Win и говорите, отпустите — текст вставится
в активное окно. Переключатель диктовки: Ctrl+Win+Space.

При первом запуске приложение скачает модель распознавания (~500 МБ)
в папку .\\data\\models — нужен интернет. Дальше всё работает офлайн.

Все данные лежат рядом с программой в папке .\\data:
  config.json     настройки
  dictionary.json словарь
  snippets.json   сниппеты
  models\\         модели распознавания
  app.log, engine.log  логи

Папку можно целиком переносить на другой компьютер или флешку.

Требования: Windows 10/11 x64, микрофон.
Проект: https://github.com/pandaman77/openflow
"""


def fail(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    version = json.loads((TAURI / "tauri.conf.json").read_text(encoding="utf-8"))["version"]

    shell = TAURI / "target" / "release" / "openflow.exe"
    if not shell.exists():
        fail(f"{shell} not found — run `npx tauri build` first")
    engine = TAURI / "binaries" / "openflow-engine-x86_64-pc-windows-msvc.exe"
    if not engine.exists():
        fail(f"{engine} not found — build the PyInstaller sidecar first")

    for exe in (shell, engine):
        age = datetime.now() - datetime.fromtimestamp(exe.stat().st_mtime)
        print(f"  {exe.name}: {exe.stat().st_size / 1e6:.1f} MB, built {age} ago")

    out_dir = REPO / "dist" / f"OpenFlow-Portable-{version}"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    shutil.copy2(shell, out_dir / "OpenFlow.exe")
    shutil.copy2(engine, out_dir / "openflow-engine.exe")
    (out_dir / "portable.txt").write_text(PORTABLE_TXT, encoding="utf-8")
    (out_dir / "README.txt").write_text(README_TXT, encoding="utf-8")

    zip_path = REPO / "dist" / f"OpenFlow-Portable-{version}-x64.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for file in sorted(out_dir.rglob("*")):
            zf.write(file, file.relative_to(out_dir.parent))

    print(f"OK: {zip_path} ({zip_path.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
