"""Live browser test for student CSV download and class intake (synthetic records)."""
from pathlib import Path
import uuid
import os

import pandas as pd
from playwright.sync_api import sync_playwright, expect

out = Path(__file__).resolve().parents[1] / "qa-artifacts"
out.mkdir(exist_ok=True)
with sync_playwright() as p:
    browser = p.chromium.launch(channel=os.environ.get("PLAYWRIGHT_CHANNEL", "chrome"), headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1100}, reduced_motion="reduce")
    page.goto(os.environ.get("LATTICE_TEST_URL", "http://127.0.0.1:8501"), wait_until="networkidle")
    page.get_by_role("button", name="Start a blank results sheet").click()
    expect(page.get_by_role("button", name="Build and check compound")).to_be_visible(timeout=30000)
    page.get_by_role("textbox", name="Lab group code (no names)", exact=True).fill("QA-G07")
    page.get_by_role("textbox", name="Semester / Year", exact=True).fill("Fall 2026")
    page.get_by_role("textbox", name="Instructor / Section", exact=True).fill("CHEM120-QA")
    for segment, value in [("year", "2026"), ("month", "11"), ("day", "12")]:
        field = page.get_by_role("spinbutton", name=f"{segment}, Experiment date", exact=True)
        field.click()
        field.press_sequentially(value)
    page.get_by_role("spinbutton", name="day, Experiment date", exact=True).press("Tab")
    page.get_by_role("combobox", name="Phase", exact=True).click()
    page.get_by_role("option", name="pure", exact=True).click()
    page.get_by_role("combobox", name="Bubble response", exact=True).click()
    page.get_by_role("option", name="yes", exact=True).click()
    page.get_by_role("button", name="Build and check compound").click()
    expect(page.get_by_text("This entry passed validation.", exact=True)).to_be_visible(timeout=30000)
    page.get_by_role("button", name="Add to project dataset", exact=True).click()
    download_button = page.get_by_role("button", name="Download student submission CSV", exact=True)
    expect(download_button).to_be_visible(timeout=30000)
    with page.expect_download() as download:
        download_button.click()
    assert download.value.suggested_filename == "lattice_student_results.csv"
    download.value.save_as(str(out / "student-results.csv"))
    data = pd.read_csv(out / "student-results.csv")
    assert len(data) == 1 and data.iloc[0].LabGroup == "QA-G07"
    assert "Email" not in data and "Name" not in data
    page.screenshot(path=str(out / "student-results.png"), full_page=True)
    # Add a real repeat, then remove just the first observation through its row action.
    page.get_by_role("spinbutton", name="Trial number", exact=True).fill("2")
    page.get_by_role("button", name="Build and check compound", exact=True).click()
    page.get_by_role("button", name="Add to project dataset", exact=True).click()
    delete_buttons = page.get_by_role("button", name="Delete observation", exact=True)
    expect(delete_buttons).to_have_count(2)
    delete_buttons.first.click()
    page.get_by_role("button", name="Keep observation", exact=True).click()
    expect(delete_buttons).to_have_count(2)
    delete_buttons.first.click()
    page.get_by_role("button", name="Confirm delete", exact=True).click()
    expect(delete_buttons).to_have_count(1)
    with page.expect_download() as after_delete:
        download_button.click()
    after_delete.value.save_as(str(out / "after-delete.csv"))
    remaining = pd.read_csv(out / "after-delete.csv")
    assert len(remaining) == 1 and remaining.iloc[0].Trial == 2
    assert remaining.iloc[0].ExperimentID != data.iloc[0].ExperimentID
    page.screenshot(path=str(out / "observation-deleted.png"), full_page=True)
    page.get_by_role("button", name="Start fresh", exact=True).click()
    expect(page.get_by_role("button", name="Clear recorded observations", exact=True)).to_be_visible()
    page.screenshot(path=str(out / "start-fresh-confirmation.png"), full_page=True)
    page.get_by_role("button", name="Keep my data", exact=True).click()
    expect(delete_buttons).to_have_count(1)
    page.get_by_role("button", name="Start fresh", exact=True).click()
    page.get_by_role("button", name="Clear recorded observations", exact=True).click()
    expect(delete_buttons).to_have_count(0)
    expect(download_button).to_have_count(0)
    expect(page.get_by_role("textbox", name="Lab group code (no names)", exact=True)).to_have_value("")
    expect(page.get_by_text("No recorded observations yet.", exact=True)).to_be_visible()
    # Another real trial must survive; an unchanged upload of the first must not repeat.
    (out / "student-results-again.csv").write_bytes((out / "student-results.csv").read_bytes())
    repeat = data.copy()
    repeat["ExperimentID"] = uuid.uuid4().hex
    repeat["Trial"] = 2
    repeat.to_csv(out / "student-repeat-trial.csv", index=False)
    page.wait_for_timeout(1000)  # Download triggers a Streamlit rerun.
    page.get_by_test_id("stMain").evaluate("el => el.scrollTop = 0")
    page.wait_for_timeout(300)
    page.get_by_role("combobox", name="Task", exact=True).click()
    page.get_by_role("option", name="Combine submission CSVs", exact=True).click()
    if page.get_by_role("checkbox", name="Include the whole current project dataset").is_checked():
        page.get_by_text("Include the whole current project dataset", exact=True).click()
    expect(page.get_by_role("checkbox", name="Include the whole current project dataset")).not_to_be_checked()
    uploader = page.get_by_test_id("stFileUploader").filter(has_text="Student submission CSVs")
    uploader.locator('input[type="file"]').set_input_files([str(out / name) for name in
        ["student-results.csv", "student-results-again.csv", "student-repeat-trial.csv"]])
    expect(page.get_by_text("2 experiments · 1 unchanged resubmitted rows removed", exact=True)).to_be_visible(timeout=30000)
    expect(page.get_by_role("heading", name="Submission coverage", exact=True)).to_be_visible()
    page.screenshot(path=str(out / "class-intake.png"), full_page=True)
    page.get_by_role("button", name="Open combined class results as a new project").click()
    expect(page.get_by_role("heading", name="Class results", exact=True)).to_be_visible(timeout=30000)
    expect(page.get_by_test_id("stMetricValue").first).to_have_text("2")
    expect(page.get_by_text("Submission coverage by lab group", exact=True)).to_be_visible()
    assert page.get_by_test_id("stException").count() == 0
    print("Passed: student entry, single deletion, reset, CSV download, and class intake preserving repeat trials.")
    browser.close()
