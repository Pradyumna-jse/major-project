"""Download model weights once (needs internet). Run:  python scripts/download_models.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import urllib.request
import config

print("1/2 YOLOv8 face weights ...")
p = Path(config.YOLO_FACE_WEIGHTS)
if p.exists():
    print("   already present:", p)
else:
    for u in config.YOLO_FACE_URLS:
        try:
            urllib.request.urlretrieve(u, p)
            print("   saved to", p)
            break
        except Exception as e:
            print("   failed:", u, e)
    if not p.exists():
        print("   The app will fall back to InsightFace SCRFD. You can also place any yolov8*-face.pt at", p)

print("2/2 InsightFace buffalo_l (ArcFace 512-D) ...")
from insightface.app import FaceAnalysis
fa = FaceAnalysis(name=config.INSIGHTFACE_MODEL, root=str(config.MODEL_DIR), providers=["CPUExecutionProvider"])
fa.prepare(ctx_id=-1, det_size=(640, 640))
print("   ready.")
