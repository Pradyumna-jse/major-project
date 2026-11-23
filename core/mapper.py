"""Stage 8: Folium map of confirmed and pending sightings."""
import folium
from folium.plugins import MarkerCluster
import config
from core import database as db

COLORS = {"confirmed": "green", "pending": "orange", "rejected": "gray"}


def build_map(case_id=None, include_rejected=False):
    sql = """SELECT s.*, c.name, c.case_code FROM sightings s JOIN cases c ON c.id=s.case_id
             WHERE s.lat IS NOT NULL"""
    args = []
    if case_id:
        sql += " AND s.case_id=?"
        args.append(case_id)
    if not include_rejected:
        sql += " AND s.status!='rejected'"
    rows = db.q(sql + " ORDER BY s.seen_at", args)
    m = folium.Map(location=[config.DEFAULT_LAT, config.DEFAULT_LNG], zoom_start=12,
                   tiles="OpenStreetMap", control_scale=True)
    cluster = MarkerCluster().add_to(m)
    pts = []
    for r in rows:
        pts.append([r["lat"], r["lng"]])
        img = f"<img src='/snapshots/{r['snapshot_path']}' width='110' style='border-radius:8px'><br>" if r["snapshot_path"] else ""
        html = (f"<div style='font-family:Inter,sans-serif;font-size:13px'>{img}<b>{r['name']}</b> "
                f"({r['case_code']})<br>Score {r['score']:.2f} &middot; <i>{r['status']}</i><br>"
                f"{r['camera_name'] or r['source_name'] or ''}<br>{r['seen_at']}</div>")
        folium.Marker([r["lat"], r["lng"]], popup=folium.Popup(html, max_width=220),
                      tooltip=f"{r['name']} - {r['status']}",
                      icon=folium.Icon(color=COLORS.get(r["status"], "blue"), icon="user", prefix="fa")).add_to(cluster)
    confirmed = [[r["lat"], r["lng"]] for r in rows if r["status"] == "confirmed"]
    if len(confirmed) > 1:   # movement path of the confirmed sightings, in time order
        folium.PolyLine(confirmed, color="#0f766e", weight=3, opacity=.7, dash_array="6").add_to(m)
    if pts:
        m.fit_bounds(pts, max_zoom=15)
    return m.get_root().render()
