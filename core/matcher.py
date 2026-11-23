"""Stage 4: cosine similarity, Top-K ranking and calibrated rejection."""
import numpy as np
import config
from core import database as db
from core.security import decrypt_embedding


class Gallery:
    """In-memory copy of the (decrypted) gallery; rebuilt whenever a case is added."""

    def __init__(self):
        self.mat = np.zeros((0, config.EMBEDDING_DIM), dtype=np.float32)
        self.case_ids = np.zeros(0, dtype=int)
        self.reload()

    def reload(self):
        rows = db.q("""SELECT e.case_id, e.embedding FROM embeddings e
                       JOIN cases c ON c.id=e.case_id WHERE c.status='active'""")
        if not rows:
            self.mat = np.zeros((0, config.EMBEDDING_DIM), dtype=np.float32)
            self.case_ids = np.zeros(0, dtype=int)
            return
        self.mat = np.stack([decrypt_embedding(r["embedding"]) for r in rows])
        self.case_ids = np.array([r["case_id"] for r in rows])

    def size(self):
        return len(self.case_ids)


db.init()
gallery = Gallery()


def threshold():
    return float(db.get_setting("threshold", config.MATCH_THRESHOLD))


def top_k(query, k=None, thr=None):
    """Rank cases by their BEST embedding score. Returns a list of dicts sorted by score.
    'accepted' is False when the score is below the calibrated threshold (open-set rejection)."""
    k = k or int(db.get_setting("top_k", config.TOP_K))
    thr = threshold() if thr is None else thr
    if gallery.size() == 0:
        return []
    q = query / (np.linalg.norm(query) + 1e-9)
    sims = gallery.mat @ q                      # cosine similarity (both sides unit length)
    best = {}
    for cid, s in zip(gallery.case_ids, sims):
        if cid not in best or s > best[cid]:
            best[cid] = float(s)
    ranked = sorted(best.items(), key=lambda t: t[1], reverse=True)[:k]
    out = []
    for cid, s in ranked:
        level = "strong" if s >= config.STRONG_THRESHOLD else ("possible" if s >= thr else "rejected")
        out.append({"case_id": int(cid), "score": round(s, 4), "accepted": s >= thr, "level": level})
    return out
