"""End-to-end browser test of the demo (needs Playwright). Run the server first: python run.py --no-browser --port 8765"""
import sys
from playwright.sync_api import sync_playwright
URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8765"
OUT = sys.argv[2] if len(sys.argv) > 2 else "/tmp/shots"
errs = []
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=2, accept_downloads=True)
    pg.on("pageerror", lambda e: errs.append("pageerror " + str(e)))
    pg.on("console", lambda m: m.type == "error" and errs.append("console " + m.text))
    pg.goto(URL); pg.wait_for_selector("#lf")
    pg.screenshot(path=f"{OUT}/01_login.png")
    pg.fill("#nm", "Shivansh"); pg.click("button[type=submit]")
    pg.wait_for_selector("[data-sample]"); pg.screenshot(path=f"{OUT}/02_lots.png")
    pg.click("[data-sample='L07_readings_24h.csv']"); pg.wait_for_timeout(700); pg.screenshot(path=f"{OUT}/03_screening.png")
    pg.wait_for_selector(".lothead", timeout=15000); pg.wait_for_timeout(400)
    pg.screenshot(path=f"{OUT}/04_dashboard.png")
    pg.click("[data-d='Investigate']"); pg.wait_for_selector(".saved")
    pg.click(".sock[data-id='L07-B3-S13']"); pg.wait_for_timeout(200)
    pg.screenshot(path=f"{OUT}/05_board_check.png")
    pg.click("[data-d='Retest in another board']"); pg.wait_for_selector(".saved")
    pg.click("#reveal"); pg.wait_for_selector(".banner.ok"); pg.click("tr.row[data-id='L07-B1-S31']"); pg.wait_for_timeout(200)
    pg.screenshot(path=f"{OUT}/06_revealed.png", full_page=True)
    with pg.expect_download() as d: pg.click("text=Download CSV")
    d.value.save_as(f"{OUT}/report.csv")
    with pg.expect_popup() as pop: pg.click("text=QA report")
    rp = pop.value; rp.wait_for_load_state(); rp.screenshot(path=f"{OUT}/07_report.png", full_page=True); rp.close()
    pg.click("nav button[data-v='audit']"); pg.wait_for_timeout(300); pg.screenshot(path=f"{OUT}/08_audit.png")
    pg.click("nav button[data-v='model']"); pg.wait_for_timeout(300); pg.screenshot(path=f"{OUT}/09_model.png")
    # technician uploads the Excel lot and a bad file
    pg.click("#switch"); pg.wait_for_selector("#lf"); pg.fill("#nm", "Ravi")
    pg.click(".role:has-text('Lab technician')"); pg.click("button[type=submit]"); pg.wait_for_selector("#file", state="attached")
    pg.set_input_files("#file", "sample_data/L08_readings_24h.xlsx"); pg.wait_for_selector(".lothead", timeout=15000)
    pg.wait_for_timeout(300); pg.screenshot(path=f"{OUT}/10_excel_lot.png")
    dis = pg.is_disabled("[data-d='Investigate']"); print("technician Investigate disabled:", dis)
    pg.click("nav button[data-v='lots']"); pg.wait_for_selector("#file", state="attached")
    open("/tmp/bad.csv", "w").write("id,value\n1,2\n")
    pg.set_input_files("#file", "/tmp/bad.csv"); pg.wait_for_selector(".toast.err", timeout=8000)
    print("bad file message:", pg.inner_text(".toast.err"))
    # dark mode + mobile
    pg.emulate_media(color_scheme="dark"); pg.click("tr.row[data-lot='L07']"); pg.wait_for_selector(".lothead"); pg.wait_for_timeout(300)
    pg.screenshot(path=f"{OUT}/11_dark.png")
    m = b.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
    m.goto(URL); m.wait_for_selector("#lf"); m.fill("#nm", "Asha"); m.click("button[type=submit]"); m.wait_for_selector("tr.row[data-lot='L07']")
    m.click("tr.row[data-lot='L07']"); m.wait_for_selector(".lothead"); m.wait_for_timeout(300); m.screenshot(path=f"{OUT}/12_mobile.png", full_page=True)
    b.close()
print("errors:", errs)
