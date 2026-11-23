# MPIS – Missing Person Identification & Tracking System
YOLOv8 face detection → InsightFace 512-D embeddings → cosine Top-K → officer verification → SQLite sighting log → e-mail alert → Folium map.

## Run (Windows / Mac / Linux, Python 3.10–3.12)
```
python -m venv venv
venv\Scripts\activate          # Mac/Linux: source venv/bin/activate
pip install -r requirements.txt
python scripts/download_models.py   # first time only (InsightFace buffalo_l ≈ 280 MB; YOLO face weights are already included)
python app.py
```
Open http://127.0.0.1:5000

## Try it in 2 minutes
1. **Register a case** → add a name and 1–3 clear photos.
2. **Search & scan** → upload another photo (or a video / live webcam) of the same person.
3. **Review matches** → press Confirm. An alert e-mail is saved in `data/outbox/` (or really sent if SMTP is set in Settings).
4. Open **Map** and **Sightings & alerts**.

## Measure it (for the report / PPT)
```
python scripts/evaluate.py --data dataset --seeds 3     # dataset/<person>/<img>.jpg  (e.g. an LFW subset)
```
Writes `results/metrics.json` (Rank-1/5, TAR at fixed FAR, thresholds, absent-person rejection, speed, mean ± std).

## Folder map
- `app.py` – web routes · `config.py` – all settings (env overridable)
- `core/models.py` – YOLOv8 + InsightFace · `core/matcher.py` – cosine / Top-K / threshold
- `core/tracker.py` – IoU tracker for video · `core/service.py` – the workflow
- `core/database.py` – SQLite · `core/security.py` – embedding encryption
- `core/alerts.py` – e-mail · `core/mapper.py` – Folium map
- `templates/`, `static/` – the interface
