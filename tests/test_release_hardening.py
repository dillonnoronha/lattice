"""Regression checks for persistence, scientific edge cases, and submission integrity."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from datetime import date
import io
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from openpyxl import load_workbook
from streamlit.testing.v1 import AppTest

import projects as pr
from pipeline import (nearest_neighbors, compute_pca, plot_bar_chart, set_chart_theme,
                      dataframe_to_excel_bytes, clean_and_encode_data, add_chemical_descriptors,
                      load_atomic_table_from_bytes, load_en_table_from_bytes,
                      read_table_from_bytes, validate_compound_rows)
from submissions import submission_table, conflicting_experiments, duplicate_keys, submission_summary

ROOT = Path(__file__).resolve().parents[1]


def test_unchanged_save_does_not_write_and_catalog_does_not_load_datasets(tmp_path, monkeypatch):
    store = pr.ProjectStore("test", tmp_path)
    project = pr.new_project("Before")
    revision = store.save(project)
    writes = []
    monkeypatch.setattr(store, "_write_atomic", lambda *args: writes.append(args))
    assert store.save(project) == revision
    assert not writes
    monkeypatch.setattr(store, "load", lambda *args: pytest.fail("Catalog loaded full project"))
    assert store.list_projects() == [{"id": project["id"], "name": "Before"}]


def test_old_and_stale_catalogs_recover(tmp_path):
    store = pr.ProjectStore("test", tmp_path)
    project = pr.new_project("Before")
    store.save(project)
    summary = store.root / project["id"] / "summary"
    old = summary.read_bytes()
    summary.unlink()
    assert store.list_projects()[0]["name"] == "Before"
    project["name"] = "After"
    store.save(project)
    summary.write_bytes(old)
    assert store.list_projects()[0]["name"] == "After"
    assert len(store.revisions(project["id"])) == 2


def test_atomic_failure_leaves_previous_revision_and_no_temporary_files(tmp_path, monkeypatch):
    store = pr.ProjectStore("test", tmp_path)
    project = pr.new_project("Before")
    store.save(project)
    project["name"] = "After"
    def fail(*args):
        raise OSError("Disk unavailable")
    monkeypatch.setattr(pr.os, "replace", fail)
    with pytest.raises(OSError):
        store.save(project)
    assert store.load(project["id"])["name"] == "Before"
    assert not list(store.root.rglob("*.tmp"))


@pytest.mark.parametrize("table", [
    {"columns": [["A"]], "data": [["La"]]},
    {"columns": ["A"], "data": [[{"symbol": "La"}]]},
    {"columns": ["A"], "data": [["La", "Ni"]]},
    {"columns": ["A"], "data": [{"A": "La"}]},
])
def test_malformed_project_tables_are_rejected(table):
    project = pr.new_project()
    project["dataset"] = table
    with pytest.raises(ValueError):
        pr.read_bundle(json.dumps(project).encode())


def test_export_cannot_create_a_bundle_that_import_would_reject(monkeypatch):
    monkeypatch.setattr(pr, "MAX_BUNDLE_BYTES", 10)
    with pytest.raises(ValueError, match="limit"):
        pr.bundle_bytes(pr.new_project())


def test_missing_measurements_cannot_be_perfect_neighbors():
    data = pd.DataFrame({"Formula": ["unknown", "close", "far"], "AN": [np.nan, 1, 3],
                         "BN": [np.nan, 2, 4]}, index=[7, 7, 7])
    target = pd.DataFrame({"AN": [1], "BN": [2]})
    result = nearest_neighbors(data, target)
    assert result.Formula.tolist() == ["close", "far"]
    assert result.iloc[0].Distance == 0
    assert nearest_neighbors(data, pd.DataFrame({"AN": [np.nan], "BN": [np.inf]})).empty


def test_pca_rejects_constant_data_and_handles_nonfinite_measurements():
    assert not compute_pca(pd.DataFrame({"AN": [1]*3, "BN": [2]*3}))["ok"]
    data = pd.DataFrame({"AN": [1, 2, 3, np.inf], "BN": [2, 3, 4, np.nan],
                         "Formula": ["a", "b", "c", "unknown"]}, index=[2]*4)
    result = compute_pca(data)
    assert result["ok"] and result["n_used"] == 3
    assert np.isfinite(result["explained"]).all()
    assert result["coords"].Formula.tolist() == ["a", "b", "c"]


def test_chart_themes_are_isolated_between_concurrent_users():
    barrier = Barrier(2)
    def chart(mode):
        set_chart_theme(mode)
        barrier.wait(timeout=10)
        return plot_bar_chart(pd.DataFrame({"x": ["A"], "y": [1]}), "x", "y", "", "").layout.font.color
    with ThreadPoolExecutor(max_workers=2) as pool:
        colors = list(pool.map(chart, ["light", "dark"]))
    assert colors == ["#24324a", "#dbe4f3"]


def test_excel_exports_preserve_formula_like_text_as_literal_cells():
    book = load_workbook(io.BytesIO(dataframe_to_excel_bytes(pd.DataFrame({"Notes": ["=1+1", "ordinary"]}))))
    assert book.active["A2"].value == "=1+1"
    assert book.active["A2"].data_type == "s"


def test_import_preserves_text_codes_and_literal_na_notes():
    frame = read_table_from_bytes(b"LabGroup,Instructor,Semester,ObservationNotes\n007,001,2026,NA\n", "text.csv")
    assert frame.iloc[0].tolist() == ["007", "001", "2026", "NA"]


def test_missing_optional_ratio_stays_unknown_in_descriptors():
    atomic = load_atomic_table_from_bytes(None)
    raw = pd.DataFrame([dict(A="La", AN=2, AP="Sr", APN=None, B="Ni", BN=1, O="O", ON=4, P="pure", Bub="yes")])
    described = add_chemical_descriptors(clean_and_encode_data(raw, atomic), atomic, load_en_table_from_bytes(None))
    assert pd.isna(described.iloc[0].A_avg_mass)
    assert pd.isna(described.iloc[0].FormulaMass)
    assert pd.isna(described.iloc[0].A_mix_fraction)
    assert "Sr?" in described.iloc[0].Formula
    raw["AP"] = ""; raw["APN"] = -1
    assert "AP" in validate_compound_rows(clean_and_encode_data(raw, atomic), atomic).Field.tolist()


def test_submission_reports_missing_ids_and_repeated_ids_without_crashing():
    raw = pd.DataFrame([dict(A="La", AN=2, B="Ni", BN=1, O="O", ON=4)], index=["custom"])
    _, issues = submission_table(raw, load_atomic_table_from_bytes(None))
    assert "ExperimentID" in issues.Field.tolist()
    raw["ExperimentID"] = "a"*32
    _, issues = submission_table(pd.concat([raw, raw]), load_atomic_table_from_bytes(None))
    assert issues.Issue.str.contains("unique experiment ID").sum() == 2


def test_small_stoichiometry_changes_are_conflicts_not_duplicates():
    frame = pd.DataFrame({"ExperimentID": ["a"*32]*2, "AN": [1, 1.0000000000001]}, index=[1, 1])
    assert duplicate_keys(frame).iloc[0] != duplicate_keys(frame).iloc[1]
    assert len(conflicting_experiments(frame)) == 2


def test_coverage_separates_sections_and_counts_only_confirmed_results():
    frame = pd.DataFrame({"LabGroup": ["01"]*3, "Instructor": ["A", "A", "B"],
                          "Semester": ["Fall"]*3, "Bub": ["yes", "not tested", "maybe"],
                          "P": ["pure", "not made", "impure"]})
    summary = submission_summary(frame)
    assert summary.Experiments.tolist() == [2, 1]
    assert summary["Confirmed bubble tests"].tolist() == [1, 0]


def test_autosave_skips_navigation_but_captures_renames(tmp_path, monkeypatch):
    monkeypatch.setenv("CATALYST_LOCAL_MODE", "1")
    monkeypatch.setattr(pr, "ROOT", tmp_path)
    saved = []
    save = pr.ProjectStore.save
    def track(store, project):
        saved.append(project["name"])
        return save(store, project)
    monkeypatch.setattr(pr.ProjectStore, "save", track)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=45).run()
    next(b for b in at.button if b.label == "Start a blank results sheet").click().run()
    assert not any("Autosave failed" in error.value for error in at.error), str(at.session_state)
    initial = len(saved)
    at.radio(key="workspace_page").set_value("Overview").run()
    at.run()
    assert len(saved) == initial
    at.text_input(key="project_name").set_value("Renamed").run()
    assert len(saved) == initial + 1
    assert pr.ProjectStore("local-workstation").list_projects()[0]["name"] == "Renamed"
    assert not at.exception


def test_cancel_edit_keeps_original_and_new_entry_gets_new_id():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=45).run()
    next(b for b in at.button if b.label == "Start a blank results sheet").click().run()
    at.text_input(key="add_group").set_value("G07")
    at.text_input(key="add_semester").set_value("Fall")
    at.text_input(key="add_instructor").set_value("L02")
    at.date_input(key="add_date").set_value(date(2026, 11, 12))
    at.selectbox(key="add_phase").set_value("pure")
    at.selectbox(key="add_bub").set_value("yes")
    next(b for b in at.button if b.label == "Build and check compound").click().run()
    at.button(key="confirm_add_manual_entry").click().run()
    next(b for b in at.button if b.label == "Edit selected observation").click().run()
    next(b for b in at.button if b.label == "Cancel edit and start a new observation").click().run()
    assert at.selectbox(key="add_bub").value == ""
    at.selectbox(key="add_phase").set_value("impure")
    at.selectbox(key="add_bub").set_value("no")
    next(b for b in at.button if b.label == "Build and check compound").click().run()
    at.button(key="confirm_add_manual_entry").click().run()
    rows = at.session_state["manual_entries"]
    assert len(rows) == 2 and rows.ExperimentID.nunique() == 2
    assert rows.Bub.tolist() == ["yes", "no"]
    assert not at.exception
    # Portable bundles deliberately store raw observations, not derived Formula columns.
    restored = pr.read_bundle(pr.bundle_bytes(at.session_state["project"]))
    at.session_state["manual_entries"] = pr.decode_frame(restored["manual_entries"])
    assert "Formula" not in at.session_state["manual_entries"]
    at.run()
    assert not at.exception
    assert any(b.label == "Download student submission CSV" for b in at.get("download_button"))
    next(b for b in at.button if b.label == "Edit selected observation").click().run()
    assert not at.exception


def test_model_preferences_survive_navigation_and_widget_cleanup():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=45).run()
    next(b for b in at.button if b.label == "Try the sample investigation").click().run()
    at.radio(key="workspace_page").set_value("Experiment Designer").run()
    at.checkbox(key="include_mass").check().run()
    at.selectbox(key="evaluation_mode").set_value("Stratified rows").run()
    at.radio(key="workspace_page").set_value("Overview").run()
    at.run()
    at.radio(key="workspace_page").set_value("Experiment Designer").run()
    assert at.checkbox(key="include_mass").value is True
    assert at.selectbox(key="evaluation_mode").value == "Stratified rows"
    assert not at.exception
