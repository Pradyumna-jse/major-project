"""Light-weight IoU tracker used for track-level aggregation of embeddings in video.
Instead of reporting the same person once per frame, faces are linked across sampled frames
and their embeddings averaged. (Hypothesis from the review: averaging reduces false candidates.)"""
import numpy as np
import config


def iou(a, b):
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


class Track:
    _next = 1

    def __init__(self, face, frame_idx, frame):
        self.id = Track._next
        Track._next += 1
        self.box = face.box
        self.embs = [face.embedding]
        self.best_quality = face.quality
        self.best_frame_idx = frame_idx
        self.best_crop = self._crop(frame, face.box)
        self.first = self.last = frame_idx
        self.missed = 0

    @staticmethod
    def _crop(frame, box):
        x1, y1, x2, y2 = box
        return frame[max(0, y1):y2, max(0, x1):x2].copy()

    def update(self, face, frame_idx, frame):
        self.box = face.box
        self.embs.append(face.embedding)
        self.last = frame_idx
        self.missed = 0
        if face.quality >= self.best_quality:
            self.best_quality = face.quality
            self.best_frame_idx = frame_idx
            self.best_crop = self._crop(frame, face.box)

    def mean_embedding(self):
        m = np.mean(self.embs, axis=0)
        return (m / (np.linalg.norm(m) + 1e-9)).astype(np.float32)


class IoUTracker:
    def __init__(self, max_missed=3):
        self.tracks, self.done, self.max_missed = [], [], max_missed

    def step(self, faces, frame_idx, frame):
        used = set()
        for t in self.tracks:
            best, bi = 0, None
            for i, f in enumerate(faces):
                if i in used:
                    continue
                v = iou(t.box, f.box)
                if v > best:
                    best, bi = v, i
            if bi is not None and best >= config.TRACK_IOU:
                t.update(faces[bi], frame_idx, frame)
                used.add(bi)
            else:
                t.missed += 1
        for i, f in enumerate(faces):
            if i not in used:
                self.tracks.append(Track(f, frame_idx, frame))
        alive = []
        for t in self.tracks:
            (self.done if t.missed > self.max_missed else alive).append(t)
        self.tracks = alive

    def finish(self):
        return self.done + self.tracks
