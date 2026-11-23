"""Optional: register a few people from a folder so the UI is not empty.
Usage: python scripts/seed_demo.py path/to/dataset   (folder per person, as in evaluate.py)"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import database as db, service

db.init()
root = Path(sys.argv[1])
for i, d in enumerate(sorted(p for p in root.iterdir() if p.is_dir())[:5]):
    imgs = [p.read_bytes() for p in sorted(d.iterdir()) if p.suffix.lower() in (".jpg", ".jpeg", ".png")][:2]
    cid, rep = service.register_case({"name": d.name.replace("_", " "), "gender": "Male",
                                      "contact_email": "family@example.com", "last_seen_place": "Demo"}, imgs)
    print(d.name, "->", cid, rep)
