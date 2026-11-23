"""Evaluation protocol from the literature review (Section VII).

Dataset layout (any public set such as LFW, or your own photos):
    dataset/<person_name>/<image1>.jpg, <image2>.jpg ...
Protocol (open-set):
  * People with >= 2 images are split: first image -> gallery, remaining -> genuine probes.
  * A fraction of people (--absent, default 0.3) are NOT put in the gallery; their images are
    ABSENT probes, which a good system must reject.
Outputs: Rank-1/Rank-5 (closed-set), TAR at fixed FAR, the threshold for each FAR, rejection rate for
absent probes, detection rate and speed. Results go to results/metrics.json.
Usage: python scripts/evaluate.py --data dataset --seeds 3
"""
import argparse, json, random, sys, time
from pathlib import Path
import cv2, numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.models import get_pipeline

ap = argparse.ArgumentParser()
ap.add_argument("--data", required=True)
ap.add_argument("--absent", type=float, default=0.3)
ap.add_argument("--seeds", type=int, default=3)
ap.add_argument("--max_people", type=int, default=0)
a = ap.parse_args()

pipe = get_pipeline()
people = {}
for d in sorted(Path(a.data).iterdir()):
    if d.is_dir():
        imgs = [p for p in sorted(d.iterdir()) if p.suffix.lower() in (".jpg", ".jpeg", ".png")]
        if imgs:
            people[d.name] = imgs
if a.max_people:
    people = dict(list(people.items())[: a.max_people])

emb, times, n_img, n_det = {}, [], 0, 0
for name, imgs in people.items():
    for p in imgs:
        img = cv2.imread(str(p))
        if img is None:
            continue
        n_img += 1
        t = time.time()
        faces = pipe.extract(img)
        times.append(time.time() - t)
        if faces:
            n_det += 1
            f = max(faces, key=lambda z: (z.box[2] - z.box[0]) * (z.box[3] - z.box[1]))
            emb[(name, p.name)] = f.embedding
print(f"images: {n_img}, faces found: {n_det} ({100*n_det/max(1,n_img):.1f}%), mean {1000*np.mean(times):.0f} ms/img")


def run(seed):
    rnd = random.Random(seed)
    names = [n for n in people if sum((n, p.name) in emb for p in people[n]) >= 1]
    rnd.shuffle(names)
    n_abs = int(len(names) * a.absent)
    absent, present = names[:n_abs], names[n_abs:]
    gal, gl, gen, imp, absent_p = [], [], [], [], []
    for n in present:
        es = [(emb[(n, p.name)]) for p in people[n] if (n, p.name) in emb]
        gal.append(es[0]); gl.append(n)
        gen += [(n, e) for e in es[1:]]
    for n in absent:
        absent_p += [emb[(n, p.name)] for p in people[n] if (n, p.name) in emb]
    G = np.stack(gal)
    r1 = r5 = 0
    gscores, iscores = [], []
    for n, e in gen:
        s = G @ e
        order = np.argsort(-s)
        r1 += gl[order[0]] == n
        r5 += n in [gl[i] for i in order[:5]]
        gscores.append(s[gl.index(n)])
        iscores += [v for i, v in enumerate(s) if gl[i] != n]
    for e in absent_p:
        iscores += list(G @ e)
    ab_top = [float((G @ e).max()) for e in absent_p]
    gscores, iscores = np.array(gscores), np.array(iscores)
    res = {"n_gallery": len(gl), "n_genuine": len(gen), "n_absent_probes": len(absent_p),
           "rank1": r1 / max(1, len(gen)), "rank5": r5 / max(1, len(gen))}
    for far in (0.01, 0.001):
        thr = float(np.quantile(iscores, 1 - far)) if len(iscores) else 1.0
        res[f"thr@FAR{far}"] = thr
        res[f"TAR@FAR{far}"] = float((gscores >= thr).mean()) if len(gscores) else 0
        res[f"absent_rejected@FAR{far}"] = float((np.array(ab_top) < thr).mean()) if ab_top else None
    return res


runs = [run(s) for s in range(a.seeds)]
summary = {"images": n_img, "detection_rate": n_det / max(1, n_img), "ms_per_image": 1000 * float(np.mean(times)),
           "detector": pipe.detector_name, "seeds": a.seeds, "runs": runs}
for k in runs[0]:
    if isinstance(runs[0][k], (int, float)) and runs[0][k] is not None:
        v = np.array([r[k] for r in runs], dtype=float)
        summary[k] = {"mean": float(v.mean()), "std": float(v.std())}
Path("results").mkdir(exist_ok=True)
Path("results/metrics.json").write_text(json.dumps(summary, indent=2))
print(json.dumps({k: v for k, v in summary.items() if k != "runs"}, indent=2))
print("saved results/metrics.json  -> put the numbers in your PPT (mean ± std over seeds)")
