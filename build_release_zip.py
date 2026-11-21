#!/usr/bin/env python3
"""
===============================================================================
 CAMELOT PRO — CLEAN RELEASE BUILDER (Step 1 & Step 2)
 Creates a clean distribution folder and a ready-to-upload ZIP archive
 without any macOS hidden AppleDouble (._*) files, backups (.bak), or caches.
===============================================================================
"""

import os
import shutil
import stat
import zipfile
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
DIST_ROOT = PROJECT_DIR / "DIST"
RELEASE_FOLDER_NAME = "CAMELOT PRO"
RELEASE_STAGE_DIR = DIST_ROOT / "CAMELOT_PRO_RELEASE" / RELEASE_FOLDER_NAME
ZIP_OUTPUT_PATH = DIST_ROOT / "CAMELOT_PRO_v1.0_Release.zip"

# Whitelist of exact files to include in the public distribution
ESSENTIAL_FILES = [
    "Camelot_Pro.amxd",
    "camelot.py",
    "camelot_live_lite.js",
    "camelot_pro_m4l.js",
    "camelot_pro_runner.js",
    "vectorscope.js",
    "Camelot_Pro_Icon.png",
    "Camelot_Pro_Icon_128.png",
    "Camelot_Pro_Icon.icns",
    "Camelot_Pro_Icon.ico",
    "requirements.txt",
    "Install_Camelot_Pro.command",
    "Install_Camelot_Pro_Windows.bat",
    "README.txt",
    "README.md",
    "LICENSE",
]


def build_clean_release():
    print("=================================================================")
    print(" 📦 CAMELOT PRO — Creazione Pacchetto di Rilascio Pulito")
    print("=================================================================")

    # 1. Clean previous DIST folder if present
    if DIST_ROOT.exists():
        shutil.rmtree(DIST_ROOT)

    RELEASE_STAGE_DIR.mkdir(parents=True, exist_ok=True)
    (RELEASE_STAGE_DIR / "MIX ANALYSIS").mkdir(parents=True, exist_ok=True)

    # Create a placeholder README inside MIX ANALYSIS so the folder is preserved in ZIP
    mix_readme = RELEASE_STAGE_DIR / "MIX ANALYSIS" / "LEGGIMI_MIX_ANALYSIS.txt"
    mix_readme.write_text(
        "In questa cartella verranno salvati i report: esporta qui il file audio della tua sessione.\n",
        encoding="utf-8",
    )

    # 2. Copy only essential files and set executable permissions on scripts
    copied_files = []
    for filename in ESSENTIAL_FILES:
        src = PROJECT_DIR / filename
        if not src.exists():
            raise FileNotFoundError(f"File essenziale mancante: {src}")
        dst = RELEASE_STAGE_DIR / filename
        shutil.copy2(src, dst)

        # Ensure .command and .py are executable
        if filename.endswith((".command", ".py")):
            st = os.stat(dst)
            os.chmod(dst, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        copied_files.append(filename)
        print(f"  ✅ Incluso: {filename} ({src.stat().st_size / 1024:.1f} KB)")

    # 3. Remove any AppleDouble ._* files created by exFAT filesystem on external drive
    for p in DIST_ROOT.rglob("._*"):
        try:
            p.unlink()
        except OSError:
            pass

    # 4. Build ZIP archive strictly filtering out any ._* or __pycache__ or .DS_Store
    with zipfile.ZipFile(ZIP_OUTPUT_PATH, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for file_path in sorted(RELEASE_STAGE_DIR.rglob("*")):
            if file_path.name.startswith("._") or file_path.name == ".DS_Store":
                continue
            rel_arcname = Path(RELEASE_FOLDER_NAME) / file_path.relative_to(RELEASE_STAGE_DIR)
            if file_path.is_dir():
                continue

            # Preserve Unix executable permissions inside the ZIP archive
            z_info = zipfile.ZipInfo.from_file(file_path, arcname=str(rel_arcname))
            z_info.compress_type = zipfile.ZIP_DEFLATED
            if file_path.name.endswith((".command", ".py")):
                z_info.external_attr = (0o100755 << 16)
            else:
                z_info.external_attr = (0o100644 << 16)

            with open(file_path, "rb") as f:
                zf.writestr(z_info, f.read())

    # Remove any ._* generated next to the zip file if possible
    for p in DIST_ROOT.rglob("._*"):
        try:
            p.unlink()
        except OSError:
            pass

    zip_size_kb = ZIP_OUTPUT_PATH.stat().st_size / 1024
    print("\n-----------------------------------------------------------------")
    print(f" 🎉 Pacchetto ZIP creato con successo: {ZIP_OUTPUT_PATH}")
    print(f" 📏 Dimensione archivio: {zip_size_kb:.1f} KB")
    print("-----------------------------------------------------------------")

    # 5. Verify ZIP contents
    print("\n🔍 Contenuto verificato dentro CAMELOT_PRO_v1.0_Release.zip:")
    with zipfile.ZipFile(ZIP_OUTPUT_PATH, "r") as zf:
        for info in zf.infolist():
            perm = oct(info.external_attr >> 16)
            print(f"   • {info.filename:<48} ({info.file_size:>7} bytes) [perm: {perm}]")


if __name__ == "__main__":
    build_clean_release()

