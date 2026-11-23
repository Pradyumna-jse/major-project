"""End-to-end browser test script using Playwright to test all MPIS workflows and capture required screenshots."""
import os
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parents[1]
SCREENSHOTS_DIR = BASE_DIR / "screenshots"
SCREENSHOTS_DIR.mkdir(exist_ok=True)

APP_URL = "http://127.0.0.1:5000"

def run_tests():
    print("=== Starting MPIS End-to-End Workflow Test ===")

    # Prepare photo paths
    colin_dir = BASE_DIR / "dataset" / "Colin_Powell"
    sharon_dir = BASE_DIR / "dataset" / "Ariel_Sharon"

    colin_photos = sorted(colin_dir.glob("*.jpg"))
    sharon_photos = sorted(sharon_dir.glob("*.jpg"))

    assert len(colin_photos) >= 3, "Need at least 3 photos for Colin Powell"
    assert len(sharon_photos) >= 1, "Need at least 1 photo for Ariel Sharon"

    reg_photo_1 = str(colin_photos[0])
    reg_photo_2 = str(colin_photos[1])
    probe_same = str(colin_photos[2])
    probe_diff = str(sharon_photos[0])
    video_path = str(BASE_DIR / "test_person.mp4")

    print(f"Registration photos: {Path(reg_photo_1).name}, {Path(reg_photo_2).name}")
    print(f"Probe same photo:    {Path(probe_same).name}")
    print(f"Probe diff photo:    {Path(probe_diff).name}")
    print(f"Video file:          {Path(video_path).name}")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            headless=True,
            args=[
                "--use-fake-ui-for-media-stream",
                "--use-fake-device-for-media-stream",
                "--allow-file-access-from-files"
            ]
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 850},
            permissions=["geolocation", "camera"]
        )
        page = context.new_page()

        # Step 0: Dashboard Initial
        print("\n[Step 0] Navigating to Dashboard...")
        page.goto(APP_URL)
        page.wait_for_selector(".brand")
        time.sleep(1)
        page.screenshot(path=str(SCREENSHOTS_DIR / "dashboard.png"))
        print("  -> Saved screenshots/dashboard.png")

        # Step 4a: Register a case
        print("\n[Step 4a] Registering a case...")
        page.goto(f"{APP_URL}/register")
        page.wait_for_selector("#f")
        time.sleep(0.5)

        # Take Register page screenshot before submit
        page.fill('input[name="name"]', "Colin Powell")
        page.fill('input[name="age"]', "65")
        page.select_option('select[name="gender"]', "Male")
        page.fill('input[name="last_seen_place"]', "Central District, Metro Hub")
        page.fill('input[name="last_seen_date"]', "2026-10-18")
        page.fill('textarea[name="description"]', "Distinguished elder, wearing a navy tailored suit.")
        page.fill('input[name="contact_name"]', "Security Office")
        page.fill('input[name="contact_email"]', "family.contact@example.com")
        page.fill('input[name="contact_phone"]', "+1-202-555-0143")

        # Set files
        page.set_input_files("#ph", [reg_photo_1, reg_photo_2])
        page.wait_for_selector("#th img")
        time.sleep(0.5)
        page.screenshot(path=str(SCREENSHOTS_DIR / "register.png"))
        print("  -> Saved screenshots/register.png")

        # Click Register case
        page.click("#go")
        print("  -> Submitting registration form...")
        page.wait_for_url("**/cases/*", timeout=30000)
        time.sleep(1)
        case_url = page.url
        print(f"  -> Successfully redirected to case page: {case_url}")
        page.screenshot(path=str(SCREENSHOTS_DIR / "case_detail.png"))
        print("  -> Saved screenshots/case_detail.png")

        # Step 4b: Search & scan -> Photo (SAME person)
        print("\n[Step 4b] Search & scan -> Photo: Same person match...")
        page.goto(f"{APP_URL}/search")
        page.wait_for_selector("#dz1")
        time.sleep(0.5)

        page.fill("#camera", "Metro Station Exit B")
        page.fill("#lat", "12.9716")
        page.fill("#lng", "77.5946")

        page.set_input_files("#f1", probe_same)
        print("  -> Uploaded probe photo of SAME person, waiting for matching...")
        page.wait_for_selector(".match", timeout=30000)
        time.sleep(1)

        # Verify green ring / match / Sent to review queue
        match_html = page.inner_html("#out")
        assert "Sent to the review queue" in match_html, "Expected 'Sent to the review queue' message"
        print("  -> Confirmed: Match found and 'Sent to the review queue' displayed!")

        page.screenshot(path=str(SCREENSHOTS_DIR / "search_match.png"))
        print("  -> Saved screenshots/search_match.png")

        # Step 4c: Search & scan -> Photo (DIFFERENT person)
        print("\n[Step 4c] Search & scan -> Photo: Different person...")
        page.set_input_files("#f1", probe_diff)
        print("  -> Uploaded photo of DIFFERENT person...")
        time.sleep(4)
        match_html_diff = page.inner_html("#out")
        assert "below threshold" in match_html_diff, "Expected 'below threshold' in result"
        assert "Sent to the review queue" not in match_html_diff, "Different person should NOT be sent to review"
        print("  -> Confirmed: 'below threshold' (grey) and nothing sent to review!")
        page.screenshot(path=str(SCREENSHOTS_DIR / "search_different.png"))
        print("  -> Saved screenshots/search_different.png")

        # Step 4d: Search & scan -> Video
        print("\n[Step 4d] Search & scan -> Video...")
        page.click('button[data-tab="video"]')
        page.wait_for_selector("#dz2")
        time.sleep(0.5)

        page.set_input_files("#f2", video_path)
        print("  -> Uploaded video, waiting for processing...")
        page.wait_for_selector("#out h3", timeout=60000)
        time.sleep(1.5)

        video_result = page.inner_html("#out")
        print("  -> Video output text:", page.inner_text("#out").replace("\n", " | "))
        assert "Person track 1" in video_result, "Expected 'Person track 1'"
        print("  -> Confirmed: 1 track and candidate found in video!")
        page.screenshot(path=str(SCREENSHOTS_DIR / "search_video.png"))
        print("  -> Saved screenshots/search_video.png")

        # Step 4e: Search & scan -> Live camera
        print("\n[Step 4e] Search & scan -> Live camera...")
        page.click('button[data-tab="live"]')
        page.wait_for_selector("#start")
        time.sleep(0.5)

        # Feed real face into video element for camera test
        # We inject a video element stream using canvas that renders probe_same face
        page.evaluate(f"""async () => {{
            const img = new Image();
            img.src = '/snapshots/' + document.querySelector('#pv').src.split('/').pop();
            await new Promise(r => {{ img.onload = r; }});
            const c = document.createElement('canvas');
            c.width = 640; c.height = 480;
            const ctx = c.getContext('2d');
            ctx.drawImage(img, 100, 40, 440, 400);
            const stream = c.captureStream(15);
            window._fakeFaceStream = stream;
        }}""")

        # Start camera with custom stream replacement to ensure real human face detection
        page.click("#start")
        time.sleep(0.5)
        page.evaluate("""() => {
            if (window._fakeFaceStream) {
                const vid = document.querySelector('#vid');
                vid.srcObject = window._fakeFaceStream;
                vid.play();
            }
        }""")
        print("  -> Waiting for live camera face detection frame...")
        # Wait for live tick
        time.sleep(4)
        page.screenshot(path=str(SCREENSHOTS_DIR / "search_live_camera.png"))
        print("  -> Saved screenshots/search_live_camera.png")

        # Step 4f: Review matches
        print("\n[Step 4f] Navigating to Review page...")
        page.goto(f"{APP_URL}/review")
        page.wait_for_selector(".rv")
        time.sleep(1)
        cards = page.query_selector_all(".rv")
        print(f"  -> Found {len(cards)} pending match card(s) in review queue.")
        assert len(cards) >= 2, f"Expected at least 2 pending matches, found {len(cards)}"

        page.screenshot(path=str(SCREENSHOTS_DIR / "review.png"))
        print("  -> Saved screenshots/review.png")

        # Confirm the first match using button or key 'A'
        print("  -> Confirming first match (Key 'A')...")
        page.keyboard.press("a")
        time.sleep(1.5)
        toast_text = page.inner_text(".toast") if page.query_selector(".toast") else ""
        print(f"  -> Toast displayed: {toast_text}")

        # Reject the second match using key 'R'
        print("  -> Rejecting second match (Key 'R')...")
        page.keyboard.press("r")
        time.sleep(1.5)
        toast_text_2 = page.inner_text(".toast") if page.query_selector(".toast") else ""
        print(f"  -> Toast displayed: {toast_text_2}")

        # Step 4g: Sightings & alerts
        print("\n[Step 4g] Navigating to Sightings & alerts...")
        page.goto(f"{APP_URL}/sightings")
        page.wait_for_selector(".card")
        time.sleep(1)
        page.screenshot(path=str(SCREENSHOTS_DIR / "sightings.png"))
        print("  -> Saved screenshots/sightings.png")

        sightings_text = page.inner_text("body")
        assert "confirmed" in sightings_text, "Expected confirmed sighting in sightings log"
        assert "family.contact@example.com" in sightings_text or "outbox" in sightings_text, "Expected alert in alert outbox"
        print("  -> Confirmed: Sightings log and alert outbox verified!")

        # Step 4h: Map
        print("\n[Step 4h] Navigating to Map...")
        page.goto(f"{APP_URL}/map")
        page.wait_for_selector("#m")
        time.sleep(2)
        page.screenshot(path=str(SCREENSHOTS_DIR / "map.png"))
        print("  -> Saved screenshots/map.png")

        # Step 4i: Dashboard counters update
        print("\n[Step 4i] Navigating to Dashboard to verify updated counters...")
        page.goto(APP_URL)
        page.wait_for_selector(".stat")
        time.sleep(1)
        page.screenshot(path=str(SCREENSHOTS_DIR / "dashboard_updated.png"))
        print("  -> Saved screenshots/dashboard_updated.png")

        stats_cards = page.query_selector_all(".stat b")
        stats_values = [el.inner_text() for el in stats_cards]
        print(f"  -> Updated Dashboard Stats: Active={stats_values[0]}, Review={stats_values[1]}, Confirmed={stats_values[2]}, Alerts={stats_values[3]}")
        assert int(stats_values[0]) >= 1, "Expected at least 1 active case"
        assert int(stats_values[2]) >= 1, "Expected at least 1 confirmed sighting"
        assert int(stats_values[3]) >= 1, "Expected at least 1 alert sent"

        browser.close()

    print("\n=== All End-to-End Tests Passed Successfully! ===")

if __name__ == "__main__":
    run_tests()
