"""Missing Person Identification & Tracking System - Flask application."""
import threading
import uuid
from flask import Flask, jsonify, render_template, request, send_from_directory, redirect, url_for, abort
import config
from core import database as db, matcher, service, alerts, mapper
from core.models import get_pipeline

app = Flask(__name__)
app.config["SECRET_KEY"] = config.SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = config.MAX_UPLOAD_MB * 1024 * 1024
db.init()
JOBS = {}   # video jobs: id -> {progress, result, error}


def loc_from(form):
    def f(k, d=None):
        try:
            return float(form.get(k))
        except (TypeError, ValueError):
            return d
    return {"camera": form.get("camera") or "Unnamed camera",
            "lat": f("lat", config.DEFAULT_LAT), "lng": f("lng", config.DEFAULT_LNG)}


def stats():
    one = lambda s: db.q(s, one=True)[0]
    return {
        "cases_active": one("SELECT COUNT(*) FROM cases WHERE status='active'"),
        "cases_found": one("SELECT COUNT(*) FROM cases WHERE status='found'"),
        "embeddings": one("SELECT COUNT(*) FROM embeddings"),
        "pending": one("SELECT COUNT(*) FROM sightings WHERE status='pending'"),
        "confirmed": one("SELECT COUNT(*) FROM sightings WHERE status='confirmed'"),
        "rejected": one("SELECT COUNT(*) FROM sightings WHERE status='rejected'"),
        "alerts": one("SELECT COUNT(*) FROM alerts"),
    }


@app.context_processor
def inject():
    return {"pending_count": db.q("SELECT COUNT(*) FROM sightings WHERE status='pending'", one=True)[0]}


# ---------------------------------------------------------------- pages
@app.route("/")
def dashboard():
    recent = db.q("""SELECT s.*, c.name, c.case_code FROM sightings s JOIN cases c ON c.id=s.case_id
                     ORDER BY s.id DESC LIMIT 6""")
    cases = db.q("SELECT * FROM cases ORDER BY id DESC LIMIT 5")
    return render_template("dashboard.html", s=stats(), recent=recent, cases=cases, thr=matcher.threshold(),
                           page="dashboard")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        photos = [f.read() for f in request.files.getlist("photos") if f.filename]
        if not request.form.get("name") or not photos:
            return jsonify(ok=False, error="Name and at least one photo are required"), 400
        cid, report = service.register_case(request.form, photos)
        if cid is None:
            return jsonify(ok=False, error="No usable face found in the photo(s)", report=report), 422
        return jsonify(ok=True, case_id=cid, report=report, redirect=url_for("case_detail", cid=cid))
    return render_template("register.html", page="register")


@app.route("/cases")
def cases():
    rows = db.q("""SELECT c.*, (SELECT COUNT(*) FROM embeddings e WHERE e.case_id=c.id) n_photos,
                   (SELECT COUNT(*) FROM sightings s WHERE s.case_id=c.id AND s.status='confirmed') n_conf,
                   (SELECT photo_path FROM embeddings e WHERE e.case_id=c.id LIMIT 1) photo
                   FROM cases c ORDER BY c.id DESC""")
    return render_template("cases.html", cases=rows, page="cases")


@app.route("/cases/<int:cid>")
def case_detail(cid):
    c = db.q("SELECT * FROM cases WHERE id=?", (cid,), one=True) or abort(404)
    photos = db.q("SELECT * FROM embeddings WHERE case_id=?", (cid,))
    sightings = db.q("SELECT * FROM sightings WHERE case_id=? ORDER BY id DESC", (cid,))
    return render_template("case_detail.html", c=c, photos=photos, sightings=sightings, page="cases")


@app.route("/cases/<int:cid>/status", methods=["POST"])
def case_status(cid):
    st = request.form.get("status")
    if st in ("active", "found", "closed"):
        db.x("UPDATE cases SET status=? WHERE id=?", (st, cid))
        matcher.gallery.reload()
        db.audit("case_status", f"{cid}->{st}")
    return redirect(url_for("case_detail", cid=cid))


@app.route("/cases/<int:cid>/delete", methods=["POST"])
def case_delete(cid):
    db.x("DELETE FROM cases WHERE id=?", (cid,))
    matcher.gallery.reload()
    db.audit("case_delete", str(cid))
    return redirect(url_for("cases"))


@app.route("/search")
def search():
    return render_template("search.html", page="search", d_lat=config.DEFAULT_LAT, d_lng=config.DEFAULT_LNG,
                           gallery=matcher.gallery.size(), thr=matcher.threshold())


@app.route("/review")
def review():
    rows = db.q("""SELECT s.*, c.name, c.case_code, c.age, c.gender, c.description,
                   (SELECT photo_path FROM embeddings e WHERE e.case_id=c.id LIMIT 1) ref_photo
                   FROM sightings s JOIN cases c ON c.id=s.case_id WHERE s.status='pending'
                   ORDER BY s.score DESC""")
    return render_template("review.html", rows=rows, page="review")


@app.route("/sightings")
def sightings():
    rows = db.q("""SELECT s.*, c.name, c.case_code FROM sightings s JOIN cases c ON c.id=s.case_id
                   ORDER BY s.id DESC LIMIT 200""")
    outbox = db.q("SELECT * FROM alerts ORDER BY id DESC LIMIT 20")
    return render_template("sightings.html", rows=rows, outbox=outbox, page="sightings")


@app.route("/map")
def map_page():
    return render_template("map.html", page="map", cases=db.q("SELECT id,name,case_code FROM cases"))


@app.route("/map/embed")
def map_embed():
    cid = request.args.get("case", type=int)
    return mapper.build_map(cid, include_rejected=request.args.get("rejected") == "1")


@app.route("/settings", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        for k in ("threshold", "top_k", "smtp_host", "smtp_port", "smtp_user", "smtp_pass", "authority_email"):
            if request.form.get(k) not in (None, ""):
                db.set_setting(k, request.form[k])
        db.audit("settings", "updated")
        return redirect(url_for("settings", saved=1))
    g = db.get_setting
    vals = {"threshold": matcher.threshold(), "top_k": g("top_k", config.TOP_K),
            "smtp_host": g("smtp_host", config.SMTP_HOST), "smtp_port": g("smtp_port", config.SMTP_PORT),
            "smtp_user": g("smtp_user", config.SMTP_USER), "authority_email": g("authority_email", config.AUTHORITY_EMAIL)}
    return render_template("settings.html", v=vals, page="settings", saved=request.args.get("saved"),
                           detector=get_pipeline().detector_name)


@app.route("/about")
def about():
    return render_template("about.html", page="about", detector=get_pipeline().detector_name)


# ---------------------------------------------------------------- APIs
@app.route("/api/health")
def health():
    return jsonify(ok=True, detector=get_pipeline().detector_name, gallery=matcher.gallery.size(),
                   threshold=matcher.threshold())


@app.route("/api/stats")
def api_stats():
    return jsonify(stats())


@app.route("/api/search/image", methods=["POST"])
def api_search_image():
    f = request.files.get("file")
    if not f:
        return jsonify(error="No file uploaded"), 400
    try:
        return jsonify(service.search_image(f.read(), loc_from(request.form), f.filename))
    except ValueError as e:
        return jsonify(error=str(e)), 400


@app.route("/api/search/video", methods=["POST"])
def api_search_video():
    f = request.files.get("file")
    if not f:
        return jsonify(error="No file uploaded"), 400
    jid = uuid.uuid4().hex[:8]
    path = config.UPLOAD_DIR / f"video_{jid}_{f.filename.replace(' ', '_')}"
    f.save(path)
    loc, name = loc_from(request.form), f.filename
    JOBS[jid] = {"progress": 0, "result": None, "error": None}

    def run():
        try:
            JOBS[jid]["result"] = service.search_video(path, loc, name, lambda p: JOBS[jid].update(progress=p))
            JOBS[jid]["progress"] = 1
        except Exception as e:  # noqa
            JOBS[jid]["error"] = str(e)
    threading.Thread(target=run, daemon=True).start()
    return jsonify(job=jid)


@app.route("/api/job/<jid>")
def api_job(jid):
    return jsonify(JOBS.get(jid) or {"error": "unknown job"})


@app.route("/api/search/frame", methods=["POST"])
def api_search_frame():
    f = request.files.get("frame")
    if not f:
        return jsonify(error="no frame"), 400
    return jsonify(service.search_frame(f.read(), loc_from(request.form)))


@app.route("/api/sightings/<int:sid>/<action>", methods=["POST"])
def api_review(sid, action):
    if action not in ("confirm", "reject"):
        abort(400)
    s = db.q("SELECT * FROM sightings WHERE id=?", (sid,), one=True) or abort(404)
    status = "confirmed" if action == "confirm" else "rejected"
    db.x("UPDATE sightings SET status=?, reviewed_at=? WHERE id=?", (status, db.now(), sid))
    db.audit(f"sighting_{status}", f"sighting {sid} score {s['score']:.3f}")
    sent = []
    if action == "confirm":
        case = db.q("SELECT * FROM cases WHERE id=?", (s["case_id"],), one=True)
        sent = alerts.send_sighting_alert(dict(s), dict(case))
    return jsonify(ok=True, status=status, alerts=sent)


@app.route("/uploads/<path:name>")
def uploads(name):
    return send_from_directory(config.UPLOAD_DIR, name)


@app.route("/snapshots/<path:name>")
def snaps(name):
    return send_from_directory(config.SNAP_DIR, name)


@app.route("/outbox/<path:name>")
def outbox_file(name):
    return send_from_directory(config.OUTBOX_DIR, name)


if __name__ == "__main__":
    print("Loading models (first run downloads them) ...")
    get_pipeline()
    print("Open http://127.0.0.1:5000")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
