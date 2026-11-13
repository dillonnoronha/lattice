from datetime import date
import io
import uuid
from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

from pipeline import (load_atomic_table_from_bytes, normalize_to_long_format, read_table_from_bytes,
                      combine_long_tables, find_merge_duplicates, clean_and_encode_data)
from projects import new_project, encode_frame, bundle_bytes, read_bundle, decode_frame
from submissions import submission_table, conflicting_experiments


def record(**changes):
    row = dict(ExperimentID=uuid.uuid4().hex, LabGroup="G07", Instructor="CHEM120-L02",
               Semester="Fall 2026", ExperimentDate="2026-11-12", Trial=1,
               A="La", AN=2, AP="", APN=0, B="Ni", BN=1, BP="", BPN=0,
               BDP="", BDPN=0, O="O", ON=4, P="pure", Bub="yes", ObservationNotes="Observed after testing.")
    row.update(changes)
    return row


def test_submission_csv_round_trip_preserves_identity_and_metadata():
    original = pd.DataFrame([record()])
    table, issues = submission_table(original, load_atomic_table_from_bytes(None))
    assert issues.empty
    uploaded = read_table_from_bytes(table.to_csv(index=False).encode(), "results.csv")
    normalized, warnings = normalize_to_long_format(uploaded)
    assert not warnings
    for column in ["ExperimentID", "LabGroup", "Semester", "Instructor", "ExperimentDate", "Trial", "ObservationNotes"]:
        assert normalized.iloc[0][column] == original.iloc[0][column]
    again, issues = submission_table(normalized, load_atomic_table_from_bytes(None))
    assert issues.empty
    p = new_project()
    p["manual_entries"] = encode_frame(normalized)
    restored = decode_frame(read_bundle(bundle_bytes(p))["manual_entries"])
    assert restored.iloc[0].ExperimentID == original.iloc[0].ExperimentID
    assert restored.iloc[0].LabGroup == "G07"


def test_repeat_trials_and_legacy_rows_are_not_deleted():
    first = pd.DataFrame([record()])
    second = first.copy()
    second["ExperimentID"] = uuid.uuid4().hex
    merged, removed = combine_long_tables([first, second])
    assert len(merged) == 2 and removed == 0
    legacy = first.drop(columns=["ExperimentID"])
    merged, removed = combine_long_tables([legacy, legacy])
    assert len(merged) == 2 and removed == 0
    assert find_merge_duplicates(legacy, legacy).empty


def test_reupload_removed_but_mixed_site_changes_are_conflicts():
    first = pd.DataFrame([record()])
    same = first.copy()
    same["AN"] = "2.0"
    combined, removed = combine_long_tables([first, same])
    assert len(combined) == 1 and removed == 1
    changed = first.copy()
    changed["AP"] = "Sr"; changed["APN"] = .2
    assert find_merge_duplicates(first, changed).empty
    combined, removed = combine_long_tables([first, changed])
    assert len(combined) == 2 and removed == 0
    assert len(conflicting_experiments(combined)) == 2


def test_unknown_and_unperformed_outcomes_are_not_failures():
    atomic = load_atomic_table_from_bytes(None)
    for phase in ["pure", "not made"]:
        table, issues = submission_table(pd.DataFrame([record(P=phase, Bub="not tested")]), atomic)
        assert issues.empty
        assert pd.isna(clean_and_encode_data(table, atomic).iloc[0].BubbleYes)
    _, issues = submission_table(pd.DataFrame([record(P="not made", Bub="yes")]), atomic)
    assert "Bub" in issues.Field.tolist()


def test_submission_requires_metadata_and_no_default_outcomes():
    _, issues = submission_table(pd.DataFrame([record(LabGroup="", Semester="", ExperimentDate="", P="", Bub="")]),
                                load_atomic_table_from_bytes(None))
    assert {"LabGroup", "Semester", "ExperimentDate", "P", "Bub"}.issubset(issues.Field)


def test_student_starts_blank_and_downloads_only_own_records():
    at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=45).run()
    next(b for b in at.button if b.label == "Start a blank results sheet").click().run()
    assert not at.exception
    assert at.session_state["raw_long"].empty
    assert at.session_state["manual_entries"].empty
    assert at.selectbox(key="add_phase").value == ""
    assert at.selectbox(key="add_bub").value == ""
    at.text_input(key="add_group").set_value("G07")
    at.text_input(key="add_semester").set_value("Fall 2026")
    at.text_input(key="add_instructor").set_value("CHEM120-L02")
    at.date_input(key="add_date").set_value(date(2026,11,12))
    at.selectbox(key="add_phase").set_value("pure")
    at.selectbox(key="add_bub").set_value("yes")
    next(b for b in at.button if b.label == "Build and check compound").click().run()
    assert not at.exception
    assert at.session_state["pending_manual_issues"].empty
    at.button(key="confirm_add_manual_entry").click().run()
    assert not at.exception
    assert len(at.session_state["manual_entries"]) == 1
    assert any(b.label == "Download student submission CSV" for b in at.get("download_button"))
    identity = at.session_state["manual_entries"].iloc[0].ExperimentID
    next(b for b in at.button if b.label == "Edit selected observation").click().run()
    assert not at.exception
    at.selectbox(key="add_bub").set_value("no")
    next(b for b in at.button if b.label == "Build and check compound").click().run()
    at.button(key="confirm_add_manual_entry").click().run()
    assert not at.exception
    assert len(at.session_state["manual_entries"]) == 1
    assert at.session_state["manual_entries"].iloc[0].ExperimentID == identity
    assert at.session_state["manual_entries"].iloc[0].Bub == "no"
    at.radio(key="workspace_page").set_value("Share findings").run()
    assert not at.exception
    assert any(b.label == "Download student submission CSV" for b in at.get("download_button"))


def test_sample_data_cannot_be_downloaded_as_student_results():
    at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=45).run()
    next(b for b in at.button if b.label == "Try the sample investigation").click().run()
    at.radio(key="workspace_page").set_value("Share findings").run()
    assert not at.exception
    assert not any(b.label == "Download student submission CSV" for b in at.get("download_button"))
