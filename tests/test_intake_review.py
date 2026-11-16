"""Row-level class intake review must not confuse repeats or conflicting versions."""
import pandas as pd
from streamlit.testing.v1 import AppTest

from pipeline import load_atomic_table_from_bytes
from submissions import conflicting_experiments, intake_validation_issues


def row(identifier, **changes):
    result = dict(ExperimentID=identifier, LabGroup="DEMO-01", Instructor="Demo section",
                  Semester="Demo Fall 2026", ExperimentDate="2026-11-15", Trial=1,
                  A="La", AN=2, AP="", APN=0, B="Ni", BN=1, BP="", BPN=0,
                  BDP="", BDPN=0, O="O", ON=4, P="pure", Bub="yes", ObservationNotes="Demo",
                  _IntakeFile="demo.csv", _IntakeRow=1, _IntakeValidate=True)
    result.update(changes)
    return result


def review_app():
    import streamlit as st
    from submissions import render_intake_review
    st.session_state.reviewed = render_intake_review(st.session_state.rows, st.session_state.get("batch_key", ""))


def review(frame):
    at = AppTest.from_function(review_app)
    at.session_state["rows"] = frame
    at.run()
    assert not at.exception
    return at


def click(at, label):
    next(b for b in at.button if b.label == label).click().run()
    assert not at.exception


def test_remove_exact_row_cancel_restore_and_batch_change():
    # Conflicting versions share an ID; a delete must remove only the chosen version.
    original = pd.DataFrame([row("a" * 32), row("a" * 32, Bub="no", _IntakeRow=2),
                             row("b" * 32, Trial=2, _IntakeRow=3)])
    at = review(original)
    click(at, "Delete row")
    click(at, "Keep row")
    pd.testing.assert_frame_equal(at.session_state["reviewed"], original)
    click(at, "Delete row")
    click(at, "Confirm row deletion")
    remaining = at.session_state["reviewed"]
    assert remaining.ExperimentID.tolist() == ["a" * 32, "b" * 32]
    assert remaining.Bub.tolist() == ["no", "yes"]
    assert conflicting_experiments(remaining).empty
    at.run()  # Download/navigation reruns cannot bring deleted rows back.
    assert len(at.session_state["reviewed"]) == 2
    click(at, "Restore deleted rows")
    pd.testing.assert_frame_equal(at.session_state["reviewed"], original)
    click(at, "Delete row")
    click(at, "Confirm row deletion")
    changed = original.copy()
    changed.loc[0, "ObservationNotes"] = "Corrected submission"
    at.session_state["rows"] = changed
    at.run()
    pd.testing.assert_frame_equal(at.session_state["reviewed"], changed)
    assert at.session_state["intake_review"]["deleted"] == set()
    click(at, "Delete row")
    click(at, "Confirm row deletion")
    # Even adding a duplicate file (same combined rows) starts a new batch review.
    at.session_state["batch_key"] = "different-upload-set"
    at.run()
    pd.testing.assert_frame_equal(at.session_state["reviewed"], changed)


def test_bad_row_can_be_removed_without_discarding_valid_file_rows():
    original = pd.DataFrame([row("a" * 32, AN=-1, _IntakeRow=7), row("b" * 32, _IntakeRow=8),
                             row("", LabGroup="", _IntakeValidate=False, _IntakeFile="Current project")])
    atomic = load_atomic_table_from_bytes(None)
    issues = intake_validation_issues(original, atomic)
    assert not issues.empty
    assert set(issues.File) == {"demo.csv"}
    assert set(issues.Row) == {7}
    at = review(original)
    click(at, "Delete row")
    click(at, "Confirm row deletion")
    assert intake_validation_issues(at.session_state["reviewed"], atomic).empty
    assert len(at.session_state["reviewed"]) == 2
    pd.testing.assert_frame_equal(at.session_state["rows"], original)


def test_remove_last_row_can_be_restored():
    original = pd.DataFrame([row("a" * 32)])
    at = review(original)
    click(at, "Delete row")
    click(at, "Confirm row deletion")
    assert at.session_state["reviewed"].empty
    assert not any(b.label == "Delete row" for b in at.button)
    click(at, "Restore deleted rows")
    pd.testing.assert_frame_equal(at.session_state["reviewed"], original)
