"""Build `latest.json` — the manifest the app reads to find a new version.

Every release must publish three things together: the NSIS installer, this
manifest, and nothing else changed. The manifest carries the signature the
installed copies verify with the public key baked into tauri.conf.json, so a
release without it (or with a stale one) means nobody gets the update.

    python scripts/make_update_manifest.py [--notes "text"]

Reads the version and the .sig produced by `tauri build`, writes dist/latest.json.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

REPO = "pandaman77/openflow"
ROOT = Path(__file__).resolve().parent.parent
CONF = ROOT / "apps" / "desktop" / "src-tauri" / "tauri.conf.json"
BUNDLE = ROOT / "apps" / "desktop" / "src-tauri" / "target" / "release" / "bundle" / "nsis"
OUT = ROOT / "dist" / "latest.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--notes", default="", help="release notes shown by the updater")
    args = parser.parse_args()

    version = json.loads(CONF.read_text(encoding="utf-8"))["version"]
    installer = BUNDLE / f"OpenFlow_{version}_x64-setup.exe"
    signature = installer.with_suffix(".exe.sig")

    if not installer.exists():
        print(f"нет инсталлятора: {installer}")
        print("сначала собери: scripts\\build-on-desktop.cmd build")
        return 1
    if not signature.exists():
        print(f"нет подписи: {signature}")
        print("сборка прошла без ключа — проверь TAURI_SIGNING_PRIVATE_KEY_PATH")
        return 1

    manifest = {
        "version": version,
        "notes": args.notes,
        "pub_date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "platforms": {
            "windows-x86_64": {
                "signature": signature.read_text(encoding="utf-8").strip(),
                "url": (
                    f"https://github.com/{REPO}/releases/download/"
                    f"v{version}/OpenFlow_{version}_x64-setup.exe"
                ),
            }
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK: {OUT} (версия {version})")
    print("загрузи его в релиз вместе с инсталлятором:")
    print(f"  gh release upload v{version} \"{OUT}\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
