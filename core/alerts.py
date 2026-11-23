"""Stage 7: e-mail alerts. Real SMTP if configured; otherwise the e-mail is written to data/outbox
as a .eml file (demo mode) so the whole flow can be shown without any account."""
import smtplib
import time
from email.message import EmailMessage
import config
from core import database as db


def _smtp_conf():
    g = db.get_setting
    return {
        "host": g("smtp_host", config.SMTP_HOST), "port": int(g("smtp_port", config.SMTP_PORT)),
        "user": g("smtp_user", config.SMTP_USER), "pw": g("smtp_pass", config.SMTP_PASS),
        "authority": g("authority_email", config.AUTHORITY_EMAIL),
    }


def send_sighting_alert(sighting, case, base_url=""):
    conf = _smtp_conf()
    recipients = [e for e in {case["contact_email"], conf["authority"]} if e]
    subject = f"[MPIS] Confirmed sighting of {case['name']} ({case['case_code']})"
    maps = f"https://www.google.com/maps?q={sighting['lat']},{sighting['lng']}"
    body = (f"A sighting was confirmed by a verifying officer.\n\n"
            f"Case: {case['case_code']} - {case['name']}\n"
            f"Similarity score: {sighting['score']:.2f}\n"
            f"Camera / source: {sighting['camera_name'] or sighting['source_name']}\n"
            f"Time: {sighting['seen_at']}\n"
            f"Location: {sighting['lat']}, {sighting['lng']}  ({maps})\n\n"
            f"This is an automated message from the Missing Person Identification System. "
            f"A human officer has reviewed the match, but please verify before acting.")
    results = []
    for to in recipients:
        msg = EmailMessage()
        msg["Subject"], msg["From"], msg["To"] = subject, config.ALERT_FROM, to
        msg.set_content(body)
        mode, status = "outbox", "saved"
        if conf["host"] and conf["user"]:
            try:
                with smtplib.SMTP(conf["host"], conf["port"], timeout=15) as s:
                    s.starttls()
                    s.login(conf["user"], conf["pw"])
                    s.send_message(msg)
                mode, status = "smtp", "sent"
            except Exception as e:  # noqa
                mode, status = "outbox", f"smtp failed ({e.__class__.__name__}); saved"
        if mode == "outbox":
            fn = config.OUTBOX_DIR / f"alert_{sighting['id']}_{int(time.time())}_{to.replace('@', '_at_')}.eml"
            fn.write_bytes(bytes(msg))
        db.x("INSERT INTO alerts(sighting_id,to_email,subject,mode,status,created_at) VALUES(?,?,?,?,?,?)",
             (sighting["id"], to, subject, mode, status, db.now()))
        results.append({"to": to, "mode": mode, "status": status})
    return results
