"""Central configuration. Every value can be overridden with an environment variable."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
SNAP_DIR = DATA_DIR / "snapshots"
OUTBOX_DIR = DATA_DIR / "outbox"
MODEL_DIR = DATA_DIR / "models"
DB_PATH = DATA_DIR / "mpis.db"
KEY_PATH = DATA_DIR / "embedding.key"
for d in (UPLOAD_DIR, SNAP_DIR, OUTBOX_DIR, MODEL_DIR):
    d.mkdir(parents=True, exist_ok=True)


def env(name, default):
    return os.environ.get(name, default)


# ---- Face detection (Stage 2) -------------------------------------------------
# YOLOv8 face weights. Downloaded automatically by scripts/download_models.py.
YOLO_FACE_WEIGHTS = env("MPIS_YOLO_WEIGHTS", str(MODEL_DIR / "yolov8n-face.pt"))
YOLO_FACE_URLS = [
    env("MPIS_YOLO_URL", "https://github.com/akanametov/yolo-face/releases/download/1.0.0/yolov8n-face.pt"),
    "https://github.com/akanametov/yolo-face/releases/download/v0.0.0/yolov8n-face.pt",
]
YOLO_CONF = float(env("MPIS_YOLO_CONF", "0.35"))
YOLO_IMGSZ = int(env("MPIS_YOLO_IMGSZ", "640"))

# ---- Face embedding (Stage 3) -------------------------------------------------
INSIGHTFACE_MODEL = env("MPIS_INSIGHTFACE_MODEL", "buffalo_l")  # 512-D ArcFace
EMBEDDING_DIM = 512

# ---- Matching (Stage 4) -------------------------------------------------------
TOP_K = int(env("MPIS_TOP_K", "5"))
# Cosine-similarity threshold. Below it a candidate is REJECTED (open-set rule).
# Tune with scripts/evaluate.py at a chosen FAR; the default is a common ArcFace value.
MATCH_THRESHOLD = float(env("MPIS_THRESHOLD", "0.40"))
STRONG_THRESHOLD = float(env("MPIS_STRONG_THRESHOLD", "0.55"))

# ---- Video ----------------------------------------------------------------------
VIDEO_SAMPLE_FPS = float(env("MPIS_VIDEO_SAMPLE_FPS", "2"))
TRACK_IOU = float(env("MPIS_TRACK_IOU", "0.3"))
MAX_VIDEO_FRAMES = int(env("MPIS_MAX_VIDEO_FRAMES", "600"))

# ---- Alerts (Stage 7) -----------------------------------------------------------
SMTP_HOST = env("MPIS_SMTP_HOST", "")          # e.g. smtp.gmail.com
SMTP_PORT = int(env("MPIS_SMTP_PORT", "587"))
SMTP_USER = env("MPIS_SMTP_USER", "")
SMTP_PASS = env("MPIS_SMTP_PASS", "")           # use an app password
ALERT_FROM = env("MPIS_ALERT_FROM", SMTP_USER or "alerts@mpis.local")
AUTHORITY_EMAIL = env("MPIS_AUTHORITY_EMAIL", "police.control@example.com")

# ---- Map (Stage 8) ----------------------------------------------------------------
DEFAULT_LAT = float(env("MPIS_DEFAULT_LAT", "12.9716"))
DEFAULT_LNG = float(env("MPIS_DEFAULT_LNG", "77.5946"))

SECRET_KEY = env("MPIS_SECRET", "change-me-in-production")
MAX_UPLOAD_MB = 200
