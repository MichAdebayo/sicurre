import os
import shutil
from pathlib import Path

root = Path("/Users/michaeladebayo/Documents/Simplon/brief_projects/sicurre")

dest_scripts = root / "scripts" / "data_platform"
dest_notebooks = root / "notebooks" / "data_platform"
dest_scripts.parent.mkdir(parents=True, exist_ok=True)
dest_notebooks.parent.mkdir(parents=True, exist_ok=True)

src_scripts = root / "src" / "data_platform" / "scripts"
src_notebooks = root / "src" / "data_platform" / "notebooks"

if src_scripts.exists():
    shutil.move(str(src_scripts), str(dest_scripts))
if src_notebooks.exists():
    shutil.move(str(src_notebooks), str(dest_notebooks))

(root / "scripts" / "app").mkdir(parents=True, exist_ok=True)
(root / "notebooks" / "app").mkdir(parents=True, exist_ok=True)

dest_db_dir = root / "data" / "local"
dest_db_dir.mkdir(parents=True, exist_ok=True)

src_db = root / "src" / "db" / "sicurre.db"
if src_db.exists():
    shutil.move(str(src_db), str(dest_db_dir / "sicurre.db"))

for d in [dest_scripts, dest_notebooks]:
    if not d.exists(): continue
    for r, _, files in os.walk(d):
        for f in files:
            if not f.endswith(".py"): continue
            path = Path(r) / f
            try:
                content = path.read_text()
            except: continue
            
            orig = content
            # Move from finding `.parent.parent` to `.parents[2]` which maps to project root appropriately.
            content = content.replace("Path(__file__).resolve().parent.parent", "Path(__file__).resolve().parents[2]")
            
            # Remove / "backend" from paths since we are unified now
            content = content.replace(' / "backend" / "src"', ' / "src"')
            content = content.replace(' / "backend" / ".env"', ' / ".env"')
            
            if content != orig:
                path.write_text(content)
                print(f"Updated paths in {path.name}")
