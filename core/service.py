"""Business logic that ties the stages together (used by the Flask routes and the scripts)."""
import time
import uuid
import cv2
import numpy as np
import config
from core import database as db, matcher
from core.models import get_pipeline
from core.security import encrypt_embedding
from core.tracker import IoUTracker


# --------------------------------------------------------------------- helpers
def decode_image(data: bytes):
    arr = np.frombuffer(data, np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def save_jpg(img, folder, prefix):
    name = f"{prefix}_{uuid.uuid4().hex[:10]}.jpg"
    cv2.imwrite(str(folder / name), img)
    return name


def next_case_code():
    n = db.q("SELECT COUNT(*) c FROM cases", one=True)["c"] + 1
    return f"MP-{time.strftime('%y')}-{n:04d}"


# ----------------------------------------------------- Stage 1: register a case
def register_case(form, photos):
    """photos: list of raw image bytes. Returns (case_id, report)"""
    pipe = get_pipeline()
    embeddings, report = [], []
    for i, raw in enumerate(photos):
        img = decode_image(raw)
        if img is None:
            report.append({"photo": i + 1, "ok": False, "msg": "Not a readable image"})
            continue
        faces = pipe.extract(img)
        if not faces:
            report.append({"photo": i + 1, "ok": False, "msg": "No face found - use a clearer, front-facing photo"})
            continue
        f = max(faces, key=lambda z: (z.box[2] - z.box[0]) * (z.box[3] - z.box[1]))
        name = save_jpg(img, config.UPLOAD_DIR, "case")
        embeddings.append((f, name))
        msg = "Face registered" + (" (largest face used)" if len(faces) > 1 else "")
        if f.quality < 0.25:
            msg += " - low quality, add a sharper photo for better matching"
        report.append({"photo": i + 1, "ok": True, "msg": msg, "quality": f.quality})
    if not embeddings:
        return None, report
    code = next_case_code()
    cid = db.x("""INSERT INTO cases(case_code,name,age,gender,last_seen_place,last_seen_date,description,
                  contact_name,contact_email,contact_phone,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
               (code, form.get("name", "").strip(), form.get("age") or None, form.get("gender"),
                form.get("last_seen_place"), form.get("last_seen_date"), form.get("description"),
                form.get("contact_name"), form.get("contact_email"), form.get("contact_phone"),
                "active", db.now()))
    for f, name in embeddings:
        db.x("INSERT INTO embeddings(case_id,photo_path,embedding,quality,created_at) VALUES(?,?,?,?,?)",
             (cid, name, encrypt_embedding(f.embedding), f.quality, db.now()))
    matcher.gallery.reload()
    db.audit("register_case", f"{code} with {len(embeddings)} embedding(s)")
    return cid, report


# ----------------------------------------------- Stages 2-4: search + sightings
def _case_brief(cid):
    r = db.q("SELECT id,case_code,name,age,gender,contact_email FROM cases WHERE id=?", (cid,), one=True)
    return dict(r) if r else None


def _record_sighting(match, crop, loc, source_type, source_name, frame_idx, n_frames=1):
    snap = save_jpg(crop, config.SNAP_DIR, "sight")
    sid = db.x("""INSERT INTO sightings(case_id,score,source_type,source_name,camera_name,lat,lng,
                  frame_index,seen_at,snapshot_path,status,n_frames) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
               (match["case_id"], match["score"], source_type, source_name, loc.get("camera"),
                loc.get("lat"), loc.get("lng"), frame_idx, db.now(), snap, "pending", n_frames))
    return sid, snap


def search_image(raw, loc, source_name="upload"):
    img = decode_image(raw)
    if img is None:
        raise ValueError("Could not read the image")
    t0 = time.time()
    faces = get_pipeline().extract(img)
    results = []
    for f in faces:
        ranked = matcher.top_k(f.embedding)
        for m in ranked:
            m["case"] = _case_brief(m["case_id"])
        sighting = None
        if ranked and ranked[0]["accepted"]:
            x1, y1, x2, y2 = f.box
            sid, snap = _record_sighting(ranked[0], img[max(0, y1):y2, max(0, x1):x2], loc, "photo", source_name, 0)
            sighting = {"id": sid, "snapshot": snap}
        results.append({"box": f.box, "det_conf": round(f.det_conf, 3), "quality": f.quality,
                        "top_k": ranked, "sighting": sighting})
    preview = img.copy()
    for r in results:
        x1, y1, x2, y2 = r["box"]
        ok = r["sighting"] is not None
        cv2.rectangle(preview, (x1, y1), (x2, y2), (80, 180, 20) if ok else (160, 160, 160), max(2, img.shape[1] // 300))
    pv = save_jpg(preview, config.SNAP_DIR, "preview")
    return {"faces": len(faces), "results": results, "preview": pv, "gallery_size": matcher.gallery.size(),
            "ms": int((time.time() - t0) * 1000), "detector": get_pipeline().detector_name}


def search_video(path, loc, source_name, progress=None):
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError("Could not open the video")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    step = max(1, int(round(fps / config.VIDEO_SAMPLE_FPS)))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    pipe, tracker = get_pipeline(), IoUTracker()
    idx = used = 0
    t0 = time.time()
    while used < config.MAX_VIDEO_FRAMES:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % step == 0:
            tracker.step(pipe.extract(frame), idx, frame)
            used += 1
            if progress and total:
                progress(min(0.99, idx / total))
        idx += 1
    cap.release()
    out = []
    for t in tracker.finish():
        ranked = matcher.top_k(t.mean_embedding())        # track-level aggregation
        for m in ranked:
            m["case"] = _case_brief(m["case_id"])
        sighting = None
        if ranked and ranked[0]["accepted"] and t.best_crop.size:
            sid, snap = _record_sighting(ranked[0], t.best_crop, loc, "video", source_name,
                                         t.best_frame_idx, n_frames=len(t.embs))
            sighting = {"id": sid, "snapshot": snap}
        out.append({"track": t.id, "frames": len(t.embs), "first": t.first, "last": t.last,
                    "top_k": ranked, "sighting": sighting})
    return {"frames_processed": used, "tracks": out, "ms": int((time.time() - t0) * 1000),
            "gallery_size": matcher.gallery.size(), "detector": pipe.detector_name}


def search_frame(raw, loc, cooldown=20):
    """Live webcam: one frame at a time. A per-case cooldown avoids flooding the review queue."""
    img = decode_image(raw)
    if img is None:
        return {"faces": []}
    faces = get_pipeline().extract(img)
    boxes, hits = [], []
    for f in faces:
        ranked = matcher.top_k(f.embedding, k=1)
        top = ranked[0] if ranked else None
        if top:
            top["case"] = _case_brief(top["case_id"])
        boxes.append({"box": f.box, "match": top})
        if top and top["accepted"]:
            last = db.q("""SELECT seen_at FROM sightings WHERE case_id=? AND source_type='webcam'
                           ORDER BY id DESC LIMIT 1""", (top["case_id"],), one=True)
            fresh = True
            if last:
                try:
                    age = time.time() - time.mktime(time.strptime(last["seen_at"], "%Y-%m-%d %H:%M:%S"))
                    fresh = age > cooldown
                except ValueError:
                    pass
            if fresh:
                x1, y1, x2, y2 = f.box
                sid, _ = _record_sighting(top, img[max(0, y1):y2, max(0, x1):x2], loc, "webcam", "live webcam", 0)
                hits.append(sid)
    return {"faces": boxes, "new_sightings": hits, "w": img.shape[1], "h": img.shape[0]}
