"""Optional live-browser QA: run the app on port 8501 first, then execute this file."""
from pathlib import Path
import os
from playwright.sync_api import sync_playwright, expect

output = Path(__file__).resolve().parents[1] / "qa-artifacts"
output.mkdir(exist_ok=True)
with sync_playwright() as p:
    browser = p.chromium.launch(channel=os.environ.get("PLAYWRIGHT_CHANNEL", "chrome"), headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1050}, reduced_motion="reduce")
    page.goto(os.environ.get("LATTICE_TEST_URL", "http://127.0.0.1:8501"), wait_until="networkidle")
    # A fresh desktop environment may need extra time to load the science packages.
    expect(page).to_have_title("Lattice", timeout=30000)
    expect(page.get_by_role("heading", name="Lattice", exact=True)).to_be_visible()
    page.get_by_role("button", name="Try the sample investigation").click()
    expect(page.get_by_text("Your investigation at a glance")).to_be_visible(timeout=30000)
    expect(page.get_by_test_id("stMetricValue").first).to_have_text("4")
    page.wait_for_timeout(800)
    page.screenshot(path=str(output / "overview-desktop.png"), full_page=True)
    page.get_by_text("Experiment Designer", exact=True).click()
    expect(page.get_by_role("button", name="Evaluate candidate")).to_be_visible(timeout=30000)
    page.wait_for_timeout(500)
    page.get_by_test_id("stMain").evaluate("el => el.scrollTop = 0")
    page.screenshot(path=str(output / "designer-desktop.png"), full_page=True)
    page.get_by_text("Investigate", exact=True).click()
    expect(page.get_by_text("Response counts", exact=True)).to_be_visible(timeout=30000)
    page.wait_for_timeout(500)
    page.get_by_test_id("stMain").evaluate("el => el.scrollTop = 0")
    page.screenshot(path=str(output / "investigate-desktop.png"), full_page=True)
    assert page.get_by_test_id("stException").count() == 0
    page.get_by_text("Overview", exact=True).click()
    expect(page.get_by_text("Your investigation at a glance")).to_be_visible()
    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_timeout(500)
    page.get_by_test_id("stMain").evaluate("el => el.scrollTop = 0")
    page.screenshot(path=str(output / "overview-mobile.png"), full_page=True)
    page.set_viewport_size({"width": 1440, "height": 1050})
    page.get_by_test_id("stMainMenu").click()
    page.get_by_test_id("stMainMenuItem-theme-Dark").click()
    page.keyboard.press("Escape")
    page.wait_for_timeout(700)
    page.get_by_test_id("stMain").evaluate("el => el.scrollTop = 0")
    page.screenshot(path=str(output / "overview-dark.png"), full_page=True)
    assert page.get_by_test_id("stException").count() == 0
    print("Browser QA passed: overview, designer, investigate, mobile, native dark theme.")
    browser.close()
