"""
archive.py — RetailAI Agent ZIP Builder

Produces RetailAI_Agent_Production_Ready.zip (~700 KB)
Ready for Windows deployment via bootstrapper.ps1

Excludes:
  - .git, node_modules, .next, .venv, venv, __pycache__  (large dependency folders)
  - .pt files       (YOLO weights — downloaded by installer at runtime)
  - .db, .db-shm, .db-wal files  (local database — must not ship user data)
  - backend/        (legacy ROOT-LEVEL backend only — NOT apps/backend/)
  - .zip files      (prevent ZIP-in-ZIP)
  - archive.py      (this script itself)
"""

import os
import zipfile

# Dirs to always skip by name (anywhere in the tree)
EXCLUDE_DIR_NAMES = {
    '.git', 'node_modules', '.next', '.venv', 'venv',
    '__pycache__', '.pytest_cache', 'dist', 'build',
}

# Root-level dirs to skip entirely (only matched at depth=1)
EXCLUDE_ROOT_DIRS = {'backend'}

EXCLUDE_EXTENSIONS = {'.zip', '.pt', '.db', '.db-shm', '.db-wal', '.pyc'}
EXCLUDE_FILES = {'archive.py'}


def should_exclude_file(file_name: str) -> bool:
    if file_name in EXCLUDE_FILES:
        return True
    _, ext = os.path.splitext(file_name)
    return ext.lower() in EXCLUDE_EXTENSIONS


def zipdir(base_path: str, ziph: zipfile.ZipFile):
    for root, dirs, files in os.walk(base_path):
        # Compute the relative path from the base
        rel_root = os.path.relpath(root, base_path)

        # Prune directories:
        # 1. Always skip dirs matched by name (venv, node_modules, etc.)
        # 2. Skip root-level dirs in EXCLUDE_ROOT_DIRS (only at depth 1)
        pruned = []
        for d in dirs:
            if d in EXCLUDE_DIR_NAMES:
                continue
            # Only exclude root-level "backend/" — not apps/backend/
            if d in EXCLUDE_ROOT_DIRS and rel_root == '.':
                continue
            pruned.append(d)
        dirs[:] = pruned

        for file in files:
            if should_exclude_file(file):
                continue
            file_path = os.path.join(root, file)
            archive_name = os.path.relpath(file_path, base_path)
            ziph.write(file_path, archive_name)


if __name__ == '__main__':
    output_zip = 'RetailAI_Agent_Production_Ready.zip'
    print(f"Building {output_zip}...")

    with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zipf:
        zipdir('.', zipf)
        file_count = len(zipf.namelist())

    size_kb = os.path.getsize(output_zip) / 1024
    print(f"Done! {file_count} files, {size_kb:.0f} KB")
    print(f"\nInstaller one-liner (cloud):")
    print(f"  iwr -useb https://storage.googleapis.com/retailai-downloads/bootstrapper.ps1 | iex")
    print(f"\nInstaller one-liner (local ZIP on Windows):")
    print(f"  Expand-Archive RetailAI_Agent_Production_Ready.zip -Force; cd RetailAI_Agent_Production_Ready; .\\deploy\\windows\\bootstrapper.ps1")
