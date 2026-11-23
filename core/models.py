"""Stage 2 (YOLOv8 face detection) and Stage 3 (InsightFace 512-D embedding).

Design: YOLOv8 finds face boxes. Each box is cropped (with margin) and handed to InsightFace,
which finds 5 facial landmarks, aligns the face to 112x112 and outputs a 512-D ArcFace embedding.
If the YOLO weights are not available the system falls back to InsightFace's own SCRFD detector,
so the app always runs (the active detector is shown in the UI and in /api/health).
"""
import socket
import threading
import urllib.request
from dataclasses import dataclass
from pathlib import Path
import cv2
import numpy as np
import config

_lock = threading.Lock()


@dataclass
class Face:
    box: tuple          # x1, y1, x2, y2 in the original image
    det_conf: float
    embedding: np.ndarray   # L2-normalised, 512-D
    quality: float      # sharpness x size heuristic, 0..1


class FacePipeline:
    def __init__(self):
        self.detector_name = "none"
        self.yolo = None
        self.fa = None
        self._load()

    # ------------------------------------------------------------------ loading
    def _load(self):
        from insightface.app import FaceAnalysis
        self.fa = FaceAnalysis(name=config.INSIGHTFACE_MODEL, root=str(config.MODEL_DIR),
                               providers=["CPUExecutionProvider"])
        self.fa.prepare(ctx_id=-1, det_size=(640, 640))
        self.detector_name = "InsightFace SCRFD (fallback)"
        try:
            self.yolo = self._load_yolo()
            if self.yolo is not None:
                self.detector_name = "YOLOv8 face"
        except Exception as e:  # noqa
            print(f"[models] YOLOv8 unavailable, using SCRFD fallback: {e}")

    def _load_yolo(self):
        from ultralytics import YOLO
        socket.setdefaulttimeout(30)
        p = Path(config.YOLO_FACE_WEIGHTS)
        if not p.exists():
            print(f"[models] downloading YOLOv8 face weights -> {p}")
            for u in config.YOLO_FACE_URLS:
                try:
                    urllib.request.urlretrieve(u, p)
                    break
                except Exception as e:  # noqa
                    print("[models] download failed:", u, e)
            if not p.exists():
                return None
        return YOLO(str(p))

    # ---------------------------------------------------------------- detection
    def detect_boxes(self, img):
        """Return list of (x1,y1,x2,y2,conf)."""
        h, w = img.shape[:2]
        out = []
        if self.yolo is not None:
            res = self.yolo.predict(img, conf=config.YOLO_CONF, imgsz=config.YOLO_IMGSZ, verbose=False)[0]
            for b in res.boxes:
                x1, y1, x2, y2 = [float(v) for v in b.xyxy[0].tolist()]
                out.append((max(0, x1), max(0, y1), min(w, x2), min(h, y2), float(b.conf[0])))
        else:
            for f in self.fa.get(img):
                x1, y1, x2, y2 = f.bbox.tolist()
                out.append((max(0, x1), max(0, y1), min(w, x2), min(h, y2), float(f.det_score)))
        return out

    # ---------------------------------------------------------------- embedding
    def _embed_box(self, img, box):
        x1, y1, x2, y2, _ = box
        h, w = img.shape[:2]
        bw, bh = x2 - x1, y2 - y1
        m = 0.35  # context margin so the landmark detector sees the whole head
        cx1, cy1 = int(max(0, x1 - m * bw)), int(max(0, y1 - m * bh))
        cx2, cy2 = int(min(w, x2 + m * bw)), int(min(h, y2 + m * bh))
        crop = img[cy1:cy2, cx1:cx2]
        if crop.size == 0:
            return None
        with _lock:
            faces = self.fa.get(crop)
            if faces:
                f = max(faces, key=lambda z: (z.bbox[2] - z.bbox[0]) * (z.bbox[3] - z.bbox[1]))
                emb = f.normed_embedding
            else:  # landmarks failed: feed a plain 112x112 resize to the recogniser
                rec = self.fa.models["recognition"]
                face112 = cv2.resize(crop, (112, 112))
                emb = rec.get_feat(face112).flatten()
                emb = emb / (np.linalg.norm(emb) + 1e-9)
        return np.asarray(emb, dtype=np.float32), crop

    @staticmethod
    def _quality(crop, box):
        g = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        sharp = min(1.0, cv2.Laplacian(g, cv2.CV_64F).var() / 300.0)
        size = min(1.0, (box[2] - box[0]) / 112.0)
        return float(round(0.6 * sharp + 0.4 * size, 3))

    def extract(self, img):
        """Detect and embed every face in a BGR image."""
        faces = []
        for box in self.detect_boxes(img):
            r = self._embed_box(img, box)
            if r is None:
                continue
            emb, crop = r
            faces.append(Face(box=tuple(int(v) for v in box[:4]), det_conf=box[4],
                              embedding=emb, quality=self._quality(crop, box)))
        return faces


_pipeline = None


def get_pipeline():
    global _pipeline
    if _pipeline is None:
        _pipeline = FacePipeline()
    return _pipeline
