import copy
import json

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from access import authorized_instructor
from modeling import composition_groups, evaluate, predict_candidate
from pipeline import (add_chemical_descriptors, clean_and_encode_data, load_atomic_table_from_bytes,
                      load_en_table_from_bytes, load_radii_table_from_bytes, public_view,
                      summarize_by_element, element_outcome_summary, normalize_to_long_format,
                      read_table_from_bytes, validate_compound_rows)
from projects import (ProjectStore, new_project, bundle_bytes, read_bundle, encode_frame,
                      decode_frame, anonymous_data, add_candidate, analysis_manifest)
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def chemistry():
    return load_atomic_table_from_bytes(None), load_en_table_from_bytes(None), load_radii_table_from_bytes(None)


@pytest.fixture
def dataset(chemistry):
    raw = pd.DataFrame([dict(A="Ca", AN=1.0, B="Mn" if i % 2 else "Fe", BN=1.0,
             O="O", ON=2.0 + (i // 2)*.05, P="pure" if i % 3 else "impure",
             Bub="yes" if i % 2 else "no", Semester="Fall" if i < 30 else "Spring",
             SourceRow=i, Slot=1) for i in range(60)])
    return add_chemical_descriptors(clean_and_encode_data(raw, chemistry[0]), *chemistry)


def test_unknown_outcomes_are_not_failures(chemistry):
    raw = pd.DataFrame([dict(A="Ca", AN=1, B="Fe", BN=1, O="O", ON=3, Bub=b, P=p)
                        for b, p in [("yes", "pure"), ("no", "impure"), ("maybe", "not made"), ("", "")]])
    d = add_chemical_descriptors(clean_and_encode_data(raw, chemistry[0]), *chemistry)
    assert d.BubbleYes.tolist()[:2] == [1, 0]
    assert d.BubbleYes.iloc[2:].isna().all()
    assert d.PureYes.iloc[2:].isna().all()
    summary = summarize_by_element(d, "A").iloc[0]
    assert summary.bubble_yes_rate == 50
    assert summary.pure_rate == 50
    assert summary.bubble_observed == 2
    periodic = element_outcome_summary(d)
    assert (periodic.BubbleYesPct == 50).all()


def test_missing_descriptors_remain_unknown(chemistry):
    raw = pd.DataFrame([dict(A="He", AN=1, B="Fe", BN=1, O="O", ON=3),
                        dict(A="Ca", AN=1, B="Fe", BN=1, O="O", ON=3)])
    d = add_chemical_descriptors(clean_and_encode_data(raw, chemistry[0]), *chemistry)
    assert pd.isna(d.iloc[0].Tolerance_factor)
    assert d.iloc[0].MissingDescriptors > 0


def test_grouped_evaluation_has_no_composition_overlap(dataset):
    result = evaluate(pd.concat([dataset, dataset], ignore_index=True))
    assert result["ok"]
    assert not set(result["training_compositions"]) & set(result["test_compositions"])


def test_equivalent_compositions_group_together(dataset):
    d = dataset.iloc[:1].copy()
    scaled = d.copy()
    scaled[["AN", "BN", "ON"]] *= 2
    assert composition_groups(d).iloc[0] == composition_groups(scaled).iloc[0]


def test_imputation_learns_only_training_data(dataset):
    d = dataset.copy()
    d["A_avg_EN"] = np.arange(len(d), dtype=float)
    d.loc[::7, "A_avg_EN"] = np.nan
    result = evaluate(d, evaluation="semester", holdout_semester="Spring")
    assert result["ok"]
    index = result["feature_columns"].index("A_avg_EN")
    assert result["evaluated_imputer"][index] == d.iloc[result["train_indices"]].A_avg_EN.median()
    assert result["evaluated_imputer"][index] != d.A_avg_EN.median()
    assert set(d.iloc[result["test_indices"]].Semester) == {"Spring"}


def test_prediction_uses_training_imputer_and_flags_unfamiliar(dataset):
    result = evaluate(dataset)
    row = dataset.iloc[:1].copy()
    row["A"] = "Xe"
    row["A_avg_EN"] = np.nan
    pred = predict_candidate(result, row)
    assert 0 <= pred["score"] <= 1
    assert "Xe" in pred["unfamiliar_elements"]
    assert "A_avg_EN" in pred["missing_descriptors"]
    assert pred["support"] == "Limited"


def test_rare_class_returns_explanation(dataset):
    d = dataset.copy()
    d["Bub"] = "no"
    d.loc[0, "Bub"] = "yes"
    assert not evaluate(d)["ok"]


def test_invalid_optional_stoichiometry_is_flagged(chemistry):
    d = clean_and_encode_data(pd.DataFrame([dict(A="Ca", AN=1, AP="Sr", APN=None,
                           B="Fe", BN=1, O="O", ON=3, P="pure", Bub="yes")]), chemistry[0])
    issues = validate_compound_rows(d, chemistry[0])
    assert "APN" in issues.Field.tolist()


def test_public_exports_use_allowlist_and_remove_contact_diagnostics():
    d = pd.DataFrame([dict(Formula="CaFeO3", Email="private@example.org", Name="Private",
                         Members="Private", GroupNumber="Private group", SurpriseContact="secret")])
    assert list(public_view(d)) == ["Formula"]
    issues = pd.DataFrame([dict(Field="Email", Issue="private@example.org"), dict(Field="AN", Issue="Missing ratio")])
    assert "private@example.org" not in public_view(issues).to_csv()


def test_instructor_requires_verified_allowlisted_identity():
    config = {"instructor_emails": ["teacher@example.org"]}
    assert authorized_instructor({"email":"teacher@example.org", "email_verified":True}, config)
    assert not authorized_instructor({"email":"teacher@example.org"}, config)
    assert not authorized_instructor({"email":"student@example.org", "email_verified":True}, config)
    assert not authorized_instructor({"email":"teacher@example.org", "email_verified":"true"}, config)


def test_project_round_trip_privacy_and_hypothesis(dataset):
    p = new_project("Research")
    dataset["Email"] = "private@example.org"
    p["dataset"] = encode_frame(dataset)
    add_candidate(p, dataset.iloc[:1], "A falsifiable hypothesis", {"bubble":{"score":.5}},
                  analysis_manifest(dataset, {}, {}))
    restored = read_bundle(bundle_bytes(p))
    assert "private@example.org" not in bundle_bytes(restored).decode()
    assert len(decode_frame(restored["dataset"])) == len(dataset)
    assert restored["candidates"][0]["rationale"] == "A falsifiable hypothesis"


def test_storage_revisions_and_owner_isolation(tmp_path):
    a = ProjectStore("owner-a", tmp_path)
    b = ProjectStore("owner-b", tmp_path)
    p = new_project("Before")
    first = a.save(p)
    p["name"] = "After"
    second = a.save(p)
    assert first != second
    assert a.load(p["id"], first)["name"] == "Before"
    assert a.load(p["id"])["name"] == "After"
    assert b.list_projects() == []
    with pytest.raises(FileNotFoundError): b.load(p["id"])
    with pytest.raises(ValueError): a.load("../escape")
    with pytest.raises(ValueError): a.load(p["id"], "../escape")


def test_malformed_bundle_rejected():
    with pytest.raises(ValueError): read_bundle(b"not json")
    with pytest.raises(ValueError): read_bundle(b'{"schema_version":99}')


def test_invalid_saved_settings_and_observations_rejected(dataset):
    p = new_project()
    p["settings"] = {"evaluation_mode": "Not a supported split"}
    with pytest.raises(ValueError): read_bundle(json.dumps(p).encode())
    p["settings"] = {}
    add_candidate(p, dataset.iloc[:1], "Hypothesis", {}, {})
    p["candidates"][0]["observation"] = {"bubble": "unexpected"}
    with pytest.raises(ValueError): read_bundle(json.dumps(p).encode())


def test_model_excludes_uncertain_outcomes_and_bad_compositions(dataset):
    d = dataset.copy()
    d.loc[0, "Bub"] = "maybe"
    d.loc[1, "AN"] = -1
    result = evaluate(d)
    assert result["ok"]
    assert result["excluded_rows"] == 2


def test_partial_formula_mass_is_not_reported(chemistry):
    d = clean_and_encode_data(pd.DataFrame([dict(A="XX", AN=1, B="Fe", BN=1, O="O", ON=3)]), chemistry[0])
    described = add_chemical_descriptors(d, *chemistry)
    assert pd.isna(described.iloc[0].FormulaMass)


def start_sample():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=45).run()
    assert not at.exception
    next(b for b in at.button if b.label == "Try the sample investigation").click().run()
    assert not at.exception
    return at


def test_all_research_workspaces_render_without_exceptions():
    at = start_sample()
    for page in ["Prepare data", "Investigate", "Experiment Designer", "Lab notebook", "Share findings", "Overview"]:
        at.radio(key="workspace_page").set_value(page).run()
        assert not at.exception, (page, [x.message for x in at.exception])


def test_all_investigation_views_and_manual_entry_render():
    at = start_sample()
    at.radio(key="workspace_page").set_value("Investigate").run()
    for view in ["Relationships", "Structure", "Compound details", "Outcomes"]:
        at.session_state["investigation_view"] = view
        at.run()
        assert not at.exception, view
    at.radio(key="workspace_page").set_value("Prepare data").run()
    next(x for x in at.selectbox if x.label == "Task").set_value("Add an observation").run()
    assert not at.exception
    next(b for b in at.button if b.label == "Build and check compound").click().run()
    assert not at.exception


def test_report_invalidates_after_hypothesis_change():
    at = start_sample()
    at.radio(key="workspace_page").set_value("Share findings").run()
    next(b for b in at.button if b.label == "Build report with model evaluation").click().run()
    assert any("Download printable report" in x.label for x in at.get("download_button"))
    at.text_input(key="project_name").set_value("Renamed investigation").run()
    assert not any("Download printable report" in x.label for x in at.get("download_button"))


def test_save_hypothesis_record_observation_and_add_to_data():
    at = start_sample()
    at.radio(key="workspace_page").set_value("Experiment Designer").run()
    next(x for x in at.text_area if x.label == "Why test this compound?").set_value("Compare this oxide with nearby compositions.")
    next(b for b in at.button if b.label == "Evaluate candidate").click().run()
    assert not at.exception
    next(b for b in at.button if b.label == "Save hypothesis to notebook").click().run()
    assert len(at.session_state["project"]["candidates"]) == 1
    at.radio(key="workspace_page").set_value("Lab notebook").run()
    next(x for x in at.selectbox if x.label == "Observed bubble response").set_value("yes")
    next(x for x in at.selectbox if x.label == "Observed phase").set_value("pure")
    next(x for x in at.text_input if x.label == "Experiment semester").set_value("Fall 2026")
    next(x for x in at.text_input if x.label == "Lab group code (no names)").set_value("G07")
    next(x for x in at.text_input if x.label == "Instructor / Section").set_value("CHEM120-L02")
    from datetime import date
    next(x for x in at.date_input if x.label == "Experiment date").set_value(date(2026, 11, 12))
    next(b for b in at.button if b.label == "Save observed result").click().run()
    assert not at.exception
    next(b for b in at.button if b.label == "Add observed experiment to project data").click().run()
    assert not at.exception
    assert len(at.session_state["manual_entries"]) == 1
    assert at.session_state["project"]["candidates"][0]["added_to_dataset"]
    from submissions import submission_table
    table, issues = submission_table(at.session_state["manual_entries"], load_atomic_table_from_bytes(None))
    assert issues.empty
    assert table.iloc[0].LabGroup == "G07"
    at.radio(key="workspace_page").set_value("Share findings").run()
    assert not at.exception
    assert any(b.label == "Download student submission CSV" for b in at.get("download_button"))


def test_dataset_switch_clears_staged_records_and_corrections():
    at = start_sample()
    at.session_state["manual_entries"] = pd.DataFrame([dict(A="Ca", AN=1, B="Fe", BN=1, O="O", ON=3)])
    at.session_state["element_fixes"] = {"1|1|A":"La"}
    next(b for b in at.button if b.label == "Try the sample investigation").click().run()
    assert not at.exception
    assert at.session_state["manual_entries"].empty
    assert at.session_state["element_fixes"] == {}


def test_filters_persist_across_views_and_student_downloads_exclude_contacts():
    at = start_sample()
    if any(x.key == "scope_semesters" for x in at.multiselect):
        widget = at.multiselect(key="scope_semesters")
        widget.set_value([widget.options[0]]).run()
        selection = at.session_state["scope_semesters"]
        at.radio(key="workspace_page").set_value("Share findings").run()
        assert at.session_state["scope_semesters"] == selection
    assert not at.exception
    assert not any("Full scoped dataset" in x.label for x in at.get("download_button"))


def test_report_generation_without_models_is_supported():
    at = start_sample()
    at.radio(key="workspace_page").set_value("Share findings").run()
    next(b for b in at.button if b.label == "Build report with model evaluation").click().run()
    assert not at.exception
    assert "Reproducibility manifest" in at.session_state["research_report"][1]
