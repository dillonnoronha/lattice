"""Exercise deletion/reset through Streamlit callbacks, exports, and persistence."""
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import projects as pr
from pipeline import load_atomic_table_from_bytes
from submissions import submission_table


def recorded(identifier, trial=1):
    return dict(ExperimentID=identifier, LabGroup="DEMO-01", Instructor="Demo section",
                Semester="Demo Fall 2026", ExperimentDate="2026-11-15", Trial=trial,
                A="La", AN=2, AP="", APN=0, B="Ni", BN=1, BP="", BPN=0,
                BDP="", BDPN=0, O="O", ON=4, P="pure", Bub="yes", ObservationNotes="Demo")


@pytest.fixture
def sheet(monkeypatch, tmp_path):
    monkeypatch.setenv("LATTICE_LOCAL_MODE", "1")
    monkeypatch.setattr(pr, "ROOT", tmp_path)
    at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=45).run()
    next(b for b in at.button if b.label == "Start a blank results sheet").click().run()
    at.session_state["manual_entries"] = pd.DataFrame([recorded("a" * 32), recorded("b" * 32, 2)])
    at.run()
    assert not at.exception
    return at


def click(at, label):
    next(b for b in at.button if b.label == label).click().run()
    assert not at.exception


def test_delete_during_edit_preserves_other_trial_and_saved_csv(sheet):
    at = sheet
    identity = at.session_state["project"]["id"]
    click(at, "Edit selected observation")
    at.selectbox(key="add_bub").set_value("no")
    click(at, "Build and check compound")
    assert not at.session_state["pending_manual_entry"].empty
    at.button(key="delete_observation_" + "a" * 32).click().run()
    assert len(at.session_state["manual_entries"]) == 2
    click(at, "Keep observation")
    assert len(at.session_state["manual_entries"]) == 2
    at.button(key="delete_observation_" + "a" * 32).click().run()
    click(at, "Confirm delete")
    assert at.session_state["manual_entries"].ExperimentID.tolist() == ["b" * 32]
    assert "editing_entry_id" not in at.session_state
    assert at.session_state["pending_manual_entry"].empty
    assert at.selectbox(key="add_phase").value == ""
    assert not any(b.label == "Save changes to observation" for b in at.button)
    table, issues = submission_table(at.session_state["manual_entries"], load_atomic_table_from_bytes(None))
    assert issues.empty and table.ExperimentID.tolist() == ["b" * 32]
    restored = pr.ProjectStore("local-workstation").load(identity)
    assert pr.decode_frame(restored["manual_entries"]).ExperimentID.tolist() == ["b" * 32]
    # Deleting the final row also removes the submission download on both pages.
    at.button(key="delete_observation_" + "b" * 32).click().run()
    click(at, "Confirm delete")
    assert at.session_state["manual_entries"].empty
    at.radio(key="workspace_page").set_value("Share findings").run()
    assert not at.exception
    assert not any(b.label == "Download student submission CSV" for b in at.get("download_button"))


def test_delete_unlinks_notebook_snapshot_without_losing_notebook_observation(sheet):
    at = sheet
    candidate = dict(id="a" * 32, formula="La2NiO4", row=pr.encode_frame(pd.DataFrame([recorded("a" * 32)])),
                     rationale="Demo", created=pr.now(), added_to_dataset=True,
                     observation={"phase": "pure", "bubble": "yes"})
    at.session_state["project"]["candidates"] = [candidate]
    at.run()
    at.button(key="delete_observation_" + "a" * 32).click().run()
    click(at, "Confirm delete")
    saved = at.session_state["project"]["candidates"][0]
    assert not saved.get("added_to_dataset")
    assert saved["observation"] == {"phase": "pure", "bubble": "yes"}


def test_start_fresh_clears_added_observations_preserving_imports_and_notebook(sheet):
    at = sheet
    original_id = at.session_state["project"]["id"]
    raw = pd.DataFrame([recorded("c" * 32)])
    at.session_state["raw_long"] = raw
    at.session_state["project"]["dataset"] = pr.encode_frame(raw)
    notebook_entry = dict(
        id="a" * 32, formula="La2NiO4", row=pr.encode_frame(pr.anonymous_data(pd.DataFrame([recorded("a" * 32)]))),
        rationale="Demo", created=pr.now(), prediction={}, manifest={},
        observation={"phase": "pure", "bubble": "yes", "semester": "Demo Fall 2026",
                     "group": "DEMO-01", "instructor": "Demo section", "date": "2026-11-15", "trial": 1})
    at.session_state["project"]["candidates"] = [dict(notebook_entry, added_to_dataset=True)]
    at.run()
    click(at, "Edit selected observation")
    click(at, "Build and check compound")
    click(at, "Start fresh")
    click(at, "Keep my data")
    assert len(at.session_state["manual_entries"]) == 2
    assert len(at.session_state["raw_long"]) == 1
    assert len(at.session_state["project"]["candidates"]) == 1
    store = pr.ProjectStore("local-workstation")
    other = pr.new_project("Other project")
    store.save(other)
    old_revisions = set(store.revisions(original_id))
    click(at, "Start fresh")
    click(at, "Clear recorded observations")
    assert at.session_state["project"]["id"] == original_id
    pd.testing.assert_frame_equal(at.session_state["raw_long"], raw)
    assert at.session_state["manual_entries"].empty
    assert at.session_state["pending_manual_entry"].empty
    assert at.session_state["project"]["candidates"] == [notebook_entry]
    assert at.session_state["element_fixes"] == {}
    assert "editing_entry_id" not in at.session_state
    assert at.text_input(key="add_group").value == ""
    assert at.selectbox(key="add_phase").value == ""
    assert at.date_input(key="add_date").value is None
    assert not any(b.label == "Download student submission CSV" for b in at.get("download_button"))
    saved = store.load(original_id)
    pd.testing.assert_frame_equal(pr.decode_frame(saved["dataset"]), raw, check_like=True)
    assert pr.decode_frame(saved["manual_entries"]).empty
    assert saved["candidates"] == [notebook_entry]
    assert old_revisions.issubset(store.revisions(original_id))
    assert store.load(other["id"])["name"] == "Other project"
    at.radio(key="workspace_page").set_value("Lab notebook").run()
    assert not at.exception
    assert not next(b for b in at.button if b.label == "Add observed experiment to project data").disabled
    at.radio(key="workspace_page").set_value("Prepare data").run()
    at.selectbox(key="prepare_task").set_value("Add an observation").run()
    # A fresh form is usable immediately after clearing.
    at.text_input(key="add_group").set_value("DEMO-NEW")
    at.text_input(key="add_semester").set_value("Demo Fall 2026")
    at.text_input(key="add_instructor").set_value("Demo section")
    at.date_input(key="add_date").set_value(date(2026, 11, 15))
    at.selectbox(key="add_phase").set_value("pure")
    at.selectbox(key="add_bub").set_value("yes")
    click(at, "Build and check compound")
    click(at, "Add to project dataset")
    assert at.session_state["manual_entries"].LabGroup.tolist() == ["DEMO-NEW"]
