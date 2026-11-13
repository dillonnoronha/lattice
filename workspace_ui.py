"""Research workspaces: prepare, investigate, design, record, and share."""
from __future__ import annotations

import copy
import hashlib
import json
import uuid
from html import escape

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

import access
import projects as pr
from modeling import predict_candidate
from pipeline import (
    add_chemical_descriptors, apply_element_fixes, clean_and_encode_data,
    dataframe_to_csv_bytes, dataframe_to_excel_bytes, detect_numeric_outliers,
    load_atomic_table_from_bytes, load_en_table_from_bytes, load_radii_table_from_bytes,
    nearest_neighbors, normalize_to_long_format, public_view, read_table_from_bytes,
    remove_invalid_element_rows, propose_element_fixes, set_chart_theme,
    train_ml_model, train_purity_model, validate_compound_rows, valid_element_symbols,
    make_single_prediction_row,
)

PAGES = ["Overview", "Prepare data", "Investigate", "Experiment Designer", "Lab notebook", "Share findings"]


def activate(project: dict, raw: pd.DataFrame | None = None) -> None:
    # Widget state and staged entries must never leak into another dataset.
    keep = {"dark_mode", "_store_owner"}
    for key in list(st.session_state):
        if key not in keep:
            del st.session_state[key]
    st.session_state.project = project
    st.session_state.raw_long = raw if raw is not None else pr.decode_frame(project["dataset"])
    st.session_state.manual_entries = pr.decode_frame(project["manual_entries"])
    st.session_state.element_fixes = project["corrections"].copy()
    st.session_state.pending_manual_entry = pd.DataFrame()
    st.session_state.pending_manual_issues = pd.DataFrame()
    st.session_state.project_name = project["name"]
    for key, value in project.get("filters", {}).items():
        if key in {"scope_semesters", "scope_instructors", "scope_groups"}:
            st.session_state[key] = value
    for key, value in project.get("settings", {}).items():
        if key in {"model_mode", "include_mass", "evaluation_mode", "holdout_semester"}:
            st.session_state[key] = value


def sync_project(store: pr.ProjectStore | None) -> None:
    if "project" not in st.session_state:
        return
    p = st.session_state.project
    p["name"] = st.session_state.get("project_name", p["name"])
    corrections = st.session_state.get("element_fixes", {})
    entries = pr.encode_frame(pr.anonymous_data(st.session_state.get("manual_entries", pd.DataFrame())))
    if p["corrections"] != corrections:
        pr.append_event(p, "Corrections changed", f"{len(corrections)} active element corrections")
    if p["manual_entries"] != entries:
        pr.append_event(p, "Dataset entries changed", f"{len(entries['data'])} project entries")
    p["corrections"] = corrections.copy()
    p["manual_entries"] = entries
    p["filters"] = {k: st.session_state.get(k, []) for k in ["scope_semesters", "scope_instructors", "scope_groups"]}
    p["settings"].update({k: st.session_state[k] for k in
                         ["model_mode", "include_mass", "evaluation_mode", "holdout_semester"] if k in st.session_state})
    if store:
        try:
            signature = hashlib.sha256(json.dumps(p, sort_keys=True, allow_nan=False).encode()).hexdigest()
            if st.session_state.get("_saved_signature") == signature:
                return
            st.session_state.saved_revision = store.save(p)
            st.session_state._saved_signature = signature
            st.session_state.pop("save_error", None)
        except (OSError, ValueError) as exc:
            st.session_state.save_error = str(exc)


def sidebar_projects(store: pr.ProjectStore | None) -> None:
    with st.sidebar.expander("Open or create a project", expanded="project" not in st.session_state):
        if st.button("Start a blank results sheet", type="primary", width="stretch"):
            project = pr.new_project("My lab results")
            project["source"] = "Student results"
            project["dataset"] = pr.encode_frame(pd.DataFrame(columns=pr.DATA_COLUMNS))
            activate(project)
            st.session_state.workspace_page = "Prepare data"
            st.session_state.prepare_task = "Add an observation"
            st.rerun()
        if st.button("Try the sample investigation", width="stretch"):
            from pathlib import Path
            sample = Path(__file__).parent / "data" / "Sample_Class_Data.csv"
            raw = read_table_from_bytes(sample.read_bytes(), sample.name)
            long, warnings = normalize_to_long_format(raw)
            p = pr.new_project("Sample catalyst investigation")
            p["dataset"] = pr.encode_frame(pr.anonymous_data(long))
            p["source"] = "Bundled sample data"
            pr.append_event(p, "Dataset imported", f"{len(long)} sample compounds")
            activate(p, long)
            st.rerun()
        upload = st.file_uploader("Import a spreadsheet or project", type=["csv", "xlsx", "xls", "json"], key="open_file")
        if upload:
            if st.button("Open as a new project", type="primary"):
                try:
                    if upload.name.lower().endswith(".json"):
                        p = pr.read_bundle(upload.getvalue())
                        p["id"] = uuid.uuid4().hex  # An imported bundle cannot overwrite another local project.
                        pr.append_event(p, "Project imported", "Restored from portable bundle")
                        activate(p)
                    else:
                        raw = read_table_from_bytes(upload.getvalue(), upload.name)
                        long, warnings = normalize_to_long_format(raw)
                        if long.empty:
                            raise ValueError("No compound records found. Use the supplied entry template or map the spreadsheet columns below.")
                        p = pr.new_project(upload.name.rsplit(".", 1)[0][:200])
                        p["dataset"] = pr.encode_frame(pr.anonymous_data(long))
                        p["source"] = "Uploaded spreadsheet"
                        pr.append_event(p, "Dataset imported", f"{len(long)} compounds; {len(warnings)} mapping warnings")
                        activate(p, long)
                        st.session_state.mapping_warnings = warnings
                    st.rerun()
                except (ValueError, OSError, KeyError) as exc:
                    st.error(str(exc))
            if not upload.name.lower().endswith(".json"):
                with st.expander("Map a custom one-compound-per-row sheet"):
                    try:
                        raw = read_table_from_bytes(upload.getvalue(), upload.name)
                        mapping = {}
                        for field in ["A", "AN", "B", "BN", "O", "ON", "P", "Bub", "Semester"]:
                            options = [""] + list(raw.columns)
                            mapping[field] = st.selectbox(field, options, index=options.index(field) if field in options else 0,
                                                         key=f"map_{field}")
                        if st.button("Import mapped data"):
                            required = ["A", "AN", "B", "BN", "ON"]
                            mapped = [v for v in mapping.values() if v]
                            if any(not mapping[f] for f in required) or len(mapped) != len(set(mapped)):
                                st.error("Map each required composition field to a different column.")
                            else:
                                frame = pd.DataFrame({k: raw[v] for k, v in mapping.items() if v})
                                if "O" not in frame:
                                    frame["O"] = "O"
                                long, warnings = normalize_to_long_format(frame)
                                p = pr.new_project("Mapped investigation")
                                p["dataset"] = pr.encode_frame(pr.anonymous_data(long))
                                p["source"] = "Mapped spreadsheet"
                                pr.append_event(p, "Column mapping applied", json.dumps(mapping))
                                activate(p, long)
                                st.rerun()
                    except Exception as exc:
                        st.error(f"Could not read spreadsheet: {exc}")
        if store:
            saved = store.list_projects()
            if saved:
                choices = {p["id"]: p["name"] for p in saved}
                selected = st.selectbox("Saved projects", list(choices), format_func=lambda x: choices[x])
                if st.button("Open saved project"):
                    try:
                        activate(store.load(selected))
                        st.rerun()
                    except (OSError, ValueError) as exc:
                        st.error(str(exc))


def choose_scope(df: pd.DataFrame) -> pd.DataFrame:
    with st.sidebar.expander("Analysis scope", expanded=True):
        st.caption("These filters apply to every research workspace and analysis export. Empty = all.")
        result = df.copy()
        for column, key in [("Semester", "scope_semesters"), ("Instructor", "scope_instructors"), ("LabGroup", "scope_groups")]:
            options = sorted(df.get(column, pd.Series(dtype=str)).fillna("").astype(str).unique())
            options = [x for x in options if x.strip()]
            if options:
                if key in st.session_state:
                    st.session_state[key] = [x for x in st.session_state[key] if x in options]
                selected = st.multiselect(column, options, key=key)
                if selected:
                    result = result[result[column].astype(str).isin(selected)]
            else:
                st.session_state[key] = []
        st.caption(f"{len(result):,} of {len(df):,} compounds selected")
    return result.copy()


def model_settings(df: pd.DataFrame) -> dict:
    for key, value in st.session_state.project.get("settings", {}).items():
        if key not in st.session_state and key in {"model_mode", "include_mass", "evaluation_mode", "holdout_semester"}:
            st.session_state[key] = value
    with st.expander("Model purpose & evaluation", expanded=False):
        mode = st.radio("Purpose", ["Plan a future experiment", "Analyze known phase"], key="model_mode",
                        help="Future experiments use composition only. Known-phase analysis can also use measured phase.")
        mass = st.checkbox("Include mass descriptors", key="include_mass")
        options = ["Unseen compositions", "Held-out semester", "Stratified rows"]
        selection = st.selectbox("Evaluation", options, key="evaluation_mode")
        semester = ""
        if selection == "Held-out semester":
            semesters = sorted(df.get("Semester", pd.Series(dtype=str)).dropna().astype(str).unique())
            semesters = [x for x in semesters if x.strip()]
            if semesters:
                if st.session_state.get("holdout_semester") not in semesters:
                    st.session_state.pop("holdout_semester", None)
                semester = st.selectbox("Semester to hold out", semesters, key="holdout_semester")
            else:
                st.warning("No semester labels available in this scope.")
        st.caption("Unknown/maybe outcomes are excluded. Scores are uncalibrated; similarity is not a guarantee.")
    return {"use_phase": mode == "Analyze known phase", "use_mass": mass,
            "evaluation": dict(zip(options, ["composition", "semester", "rows"]))[selection],
            "holdout_semester": semester, "random_state": 42}


def current_manifest(df: pd.DataFrame, settings: dict | None = None) -> dict:
    p = st.session_state.project
    return pr.analysis_manifest(df, p.get("filters", {}), settings or p.get("settings", {}))


def rate_text(series: pd.Series) -> str:
    return f"{series.mean():.0%}" if series.notna().any() else "—"


def wilson(series: pd.Series) -> str:
    values = series.dropna()
    n = len(values)
    if not n:
        return "No confirmed outcomes"
    p = float(values.mean()); z = 1.96
    center = (p + z*z/(2*n))/(1+z*z/n)
    margin = z*np.sqrt(p*(1-p)/n+z*z/(4*n*n))/(1+z*z/n)
    return f"{int(values.sum())}/{n} confirmed · 95% interval {center-margin:.0%}–{center+margin:.0%}"


def overview(df: pd.DataFrame, issues: pd.DataFrame, atomic, en, radii) -> None:
    from submissions import submission_summary
    st.subheader("Your investigation at a glance")
    st.write("Build an evidence trail from class observations to your next experiment.")
    cols = st.columns(3)
    cols[0].metric("Compounds in scope", len(df))
    bubble = df.get("BubbleYes", pd.Series(dtype=float))
    pure = df.get("PureYes", pd.Series(dtype=float))
    cols[1].metric("Confirmed bubbling", rate_text(bubble)); cols[1].caption(wilson(bubble))
    cols[2].metric("Confirmed purity", rate_text(pure)); cols[2].caption(wilson(pure))
    st.caption("Intervals describe observed proportions under an independent-trial assumption; repeated compounds can reduce effective evidence.")
    coverage = submission_summary(df)
    if not coverage.empty:
        with st.expander("Submission coverage by lab group"):
            st.dataframe(coverage, hide_index=True, width="stretch")
            st.caption("Received observations in the active scope. Compare these group codes with your roster for missing submissions.")
            st.download_button("Download submission coverage", dataframe_to_csv_bytes(coverage),
                               "submission_coverage.csv", "text/csv")
    left, right = st.columns([1.4, 1])
    with left:
        with st.container(border=True):
            st.markdown("#### Next useful step")
            if len(issues):
                st.write(f"Review **{len(issues)} data issues** in Prepare data before interpreting the results.")
            elif not st.session_state.project["candidates"]:
                st.write("Explore the class results, then save your first hypothesis in Experiment Designer.")
            else:
                st.write("Review planned experiments in Lab notebook and record what actually happened.")
            st.write(f"**{len(st.session_state.project['candidates'])}** saved candidates · **{len(st.session_state.project['history'])}** history events")
    with right:
        with st.container(border=True):
            st.markdown("#### Evidence quality")
            st.write(f"{int(bubble.isna().sum())} uncertain or missing bubble outcomes")
            st.write(f"{int(pure.isna().sum())} unconfirmed phase outcomes")
            missing = df.get("MissingDescriptors", pd.Series(dtype=float))
            st.write(f"{int((missing > 0).sum())} compounds with missing physics descriptors")
            st.caption("Missing properties stay unknown in tables. Model imputation is learned from training data only.")


def compound_details(df: pd.DataFrame) -> None:
    st.markdown("#### Compound explorer")
    query = st.text_input("Search formulas", placeholder="e.g. La, Ni, CaMnO3")
    matches = df[df["Formula"].str.contains(query, case=False, regex=False, na=False)] if query else df
    if matches.empty:
        st.info("No matching compounds in this scope."); return
    matches = matches.reset_index(drop=True)
    selected = st.selectbox("Compound record", list(range(len(matches))),
                            format_func=lambda i: f"{matches.iloc[i]['Formula']} · {matches.iloc[i].get('Semester', '')} · record {i+1}")
    row = matches.iloc[[selected]]
    columns = st.columns(2)
    with columns[0]:
        st.markdown("**Observed outcomes**")
        st.dataframe(public_view(row[[c for c in ["Formula", "Semester", "P", "Bub"] if c in row]]), hide_index=True)
    with columns[1]:
        st.markdown("**Calculated properties**")
        names = [c for c in ["FormulaMass", "A_avg_EN", "B_avg_EN", "Tolerance_factor", "MissingDescriptors"] if c in row]
        st.dataframe(row[names].T.rename(columns={row.index[0]: "Value"}), width="stretch")
        st.caption("Blank = unavailable, not zero. Ionic radii use reference-table oxidation/coordination assumptions; tolerance factor is not a structure determination.")


def model_evidence(result: dict, title: str) -> None:
    st.markdown(f"#### {title}")
    if not result.get("ok"):
        st.info(result["message"]); return
    cols = st.columns(3)
    cols[0].metric("Held-out accuracy", f"{result['accuracy']:.0%}")
    cols[1].metric("Always-guess baseline", f"{result['baseline_accuracy']:.0%}")
    cols[2].metric("Held-out observations", result["testing_rows"])
    st.caption(f"{result['evaluation']} · {result['labeled_rows']} confirmed labels · {result['excluded_rows']} excluded records")
    st.warning(result["overfit_warning"])
    with st.expander(f"Evaluation details · {title}"):
        st.write(f"Precision {result['rf_precision']:.0%} · Recall {result['rf_recall']:.0%} · F1 {result['rf_f1']:.0%}")
        if result["balanced_accuracy"] is not None:
            st.write(f"Balanced accuracy {result['balanced_accuracy']:.0%} · Brier score {result['brier_score']:.3f}")
        st.write(f"Logistic regression accuracy: {result['lr_accuracy']:.0%}")
        if result["cv_mean"] is not None:
            st.write(f"Cross-validation: {result['cv_mean']:.0%} ± {result['cv_std']*100:.1f} percentage points across {result['cv_folds']} valid folds (standard deviation, not a confidence interval).")
        else:
            st.caption("Insufficient independent folds for cross-validation.")
        from pipeline import plot_confusion
        st.plotly_chart(plot_confusion(result["confusion"]), width="stretch")
        st.dataframe(result["importance"], hide_index=True, width="stretch")
        st.caption("Feature importance describes model behavior, not chemical causes. Prediction uses a separate refit on all eligible records in scope.")


def designer(df: pd.DataFrame, atomic, en, radii) -> None:
    st.subheader("Experiment Designer")
    st.write("Compare a proposed composition with class evidence, then save a testable hypothesis.")
    settings = model_settings(df)
    with st.spinner("Evaluating models on independent data…"):
        bubble = train_ml_model(df, **settings)
        purity = train_purity_model(df, **{k:v for k,v in settings.items() if k != "use_phase"})
    with st.expander("How strong is the model evidence?", expanded=False):
        model_evidence(bubble, "Bubble response")
        model_evidence(purity, "Phase purity")
    symbols = valid_element_symbols(atomic)
    with st.form("candidate_form"):
        cols = st.columns(3)
        values = {}
        with cols[0]:
            st.markdown("**A site**")
            values["a"] = st.selectbox("A element", symbols, index=symbols.index("La") if "La" in symbols else 0)
            values["an"] = st.number_input("A ratio", min_value=.01, value=2.0, step=.1)
            values["ap"] = st.selectbox("A′ element", [""]+symbols, format_func=lambda s:s or "None")
            values["apn"] = st.number_input("A′ ratio", min_value=0.0, value=0.0, step=.1)
        with cols[1]:
            st.markdown("**B site**")
            values["b"] = st.selectbox("B element", symbols, index=symbols.index("Ni") if "Ni" in symbols else 0)
            values["bn"] = st.number_input("B ratio", min_value=.01, value=1.0, step=.1)
            values["bp"] = st.selectbox("B′ element", [""]+symbols, format_func=lambda s:s or "None")
            values["bpn"] = st.number_input("B′ ratio", min_value=0.0, value=0.0, step=.1)
        with cols[2]:
            st.markdown("**Oxygen & hypothesis**")
            values["on"] = st.number_input("Oxygen ratio", min_value=.01, value=4.0, step=.1)
            phase = st.selectbox("Measured phase", ["pure", "impure"]) if settings["use_phase"] else ""
            rationale = st.text_area("Why test this compound?", placeholder="Predict how changing the composition could affect the result.")
        with st.expander("Third B-site element"):
            values["bdp"] = st.selectbox("B″ element", [""]+symbols, format_func=lambda s:s or "None")
            values["bdpn"] = st.number_input("B″ ratio", min_value=0.0, value=0.0, step=.1)
        submitted = st.form_submit_button("Evaluate candidate", type="primary")
    manifest = current_manifest(df, settings)
    context = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    if submitted:
        row = make_single_prediction_row(atomic, en, phase, radii_table=radii, **values)
        issues = validate_compound_rows(row, atomic)
        if not issues.empty:
            issues = issues[~issues["Field"].isin(["P", "Bub", "Email"])]
        if not issues.empty:
            st.error("Correct the composition before evaluating.")
            st.dataframe(public_view(issues), hide_index=True)
            st.session_state.pop("candidate_preview", None)
        else:
            prediction = {}
            for name, result in [("bubble", bubble), ("purity", purity)]:
                prediction[name] = predict_candidate(result, row) if result.get("ok") else {"unavailable": result["message"]}
            st.session_state.candidate_preview = dict(row=row, rationale=rationale, prediction=prediction,
                                                      manifest=manifest, context=context, values=values, phase=phase)
    preview = st.session_state.get("candidate_preview")
    if preview and preview["context"] != context:
        st.info("The dataset, scope, or model settings changed. Evaluate the candidate again.")
        return
    if preview:
        st.markdown(f"### {preview['row'].iloc[0]['Formula']}")
        cols = st.columns(2)
        for column, name in zip(cols, ["bubble", "purity"]):
            prediction = preview["prediction"][name]
            with column:
                if "score" in prediction:
                    st.metric(f"{name.title()} model score", f"{prediction['score']:.0%}")
                    st.caption(prediction["support"])
                    if prediction["unfamiliar_elements"]:
                        st.warning("Elements absent from training: " + ", ".join(prediction["unfamiliar_elements"]))
                    if prediction["outside_range"]:
                        st.caption("Outside observed ranges: " + ", ".join(prediction["outside_range"]))
                    if prediction["missing_descriptors"]:
                        st.caption("Training-median imputation needed: " + ", ".join(prediction["missing_descriptors"]))
                else:
                    st.info(prediction["unavailable"])
        st.caption("Model scores express model preference; they are not calibrated probabilities. You can save a hypothesis even when data are insufficient for modeling.")
        if st.button("Save hypothesis to notebook", type="primary"):
            if not preview["rationale"].strip():
                st.error("Add a rationale and evaluate again before saving.")
            else:
                pr.add_candidate(st.session_state.project, preview["row"], preview["rationale"],
                                 preview["prediction"], preview["manifest"])
                st.success("Hypothesis saved. Compare candidates and record outcomes in Lab notebook.")
        st.markdown("#### Similar class experiments")
        neighbors = nearest_neighbors(df, preview["row"], 5)
        st.dataframe(neighbors, hide_index=True, width="stretch")
        st.caption("Distance compares measured, varying descriptors shared with the candidate. Rows missing any compared descriptor are excluded. Similarity does not establish identical chemistry.")
        if neighbors.empty:
            st.info("No comparable experiments have enough measured, varying descriptors in this scope.")
        with st.expander("What-if: vary oxygen stoichiometry"):
            limits = st.slider("Oxygen ratio range", .1, 12.0, (1.0, 6.0), .1)
            if st.button("Calculate sweep", disabled=not bubble.get("ok")):
                points = []
                for value in np.linspace(*limits, 21):
                    inputs = dict(preview["values"], on=float(value))
                    row = make_single_prediction_row(atomic, en, preview["phase"], radii_table=radii, **inputs)
                    predicted = predict_candidate(bubble, row)
                    points.append({"Oxygen ratio": value, "Model score": predicted["score"], "Support": predicted["support"]})
                st.plotly_chart(px.line(pd.DataFrame(points), x="Oxygen ratio", y="Model score", markers=True,
                                       hover_data=["Support"]), width="stretch")
                st.caption("A model sensitivity exercise, not a causal or chemical feasibility claim.")


def notebook(atomic, en, radii) -> None:
    from datetime import date
    from submissions import observation_record, submission_table
    p = st.session_state.project
    st.subheader("Lab notebook")
    st.caption("Saved hypotheses retain their original analysis scope and model settings, regardless of current filters.")
    candidates = p["candidates"]
    if not candidates:
        st.info("Save a candidate in Experiment Designer to start your notebook."); return
    table = []
    for c in candidates:
        prediction = c.get("prediction", {})
        observed = c.get("observation", {})
        table.append({"Candidate": c["formula"], "Status": c.get("status", "Planned"),
            "Bubble score": prediction.get("bubble", {}).get("score"),
            "Purity score": prediction.get("purity", {}).get("score"),
            "Observed bubble": observed.get("bubble", ""), "Observed phase": observed.get("phase", ""),
            "Rationale": c["rationale"]})
    st.dataframe(pd.DataFrame(table), hide_index=True, width="stretch",
                 column_config={"Bubble score": st.column_config.NumberColumn(format="percent"),
                                "Purity score": st.column_config.NumberColumn(format="percent")})
    selected = st.selectbox("Open saved hypothesis", list(range(len(candidates))),
                            format_func=lambda i:f"{i+1}. {candidates[i]['formula']}")
    candidate = candidates[selected]
    st.write(candidate["rationale"])
    with st.expander("Original prediction & provenance"):
        st.json({"created": candidate["created"], "prediction": candidate.get("prediction", {}),
                 "analysis": candidate.get("manifest", {})})
    prior = candidate.get("observation", {})
    with st.form(f"observation_{candidate['id']}"):
        b_options = ["", "yes", "no", "maybe", "not tested"]
        p_options = ["", "pure", "impure", "not made"]
        b = st.selectbox("Observed bubble response", b_options, index=b_options.index(prior.get("bubble", "")))
        phase = st.selectbox("Observed phase", p_options, index=p_options.index(prior.get("phase", "")))
        notes = st.text_area("Observations and interpretation", value=prior.get("notes", ""), max_chars=2000)
        semester = st.text_input("Experiment semester", value=prior.get("semester", ""))
        group = st.text_input("Lab group code (no names)", value=prior.get("group", ""))
        instructor = st.text_input("Instructor / Section", value=prior.get("instructor", ""))
        try:
            prior_date = date.fromisoformat(prior.get("date", ""))
        except ValueError:
            prior_date = None
        performed = st.date_input("Experiment date", value=prior_date)
        trial = st.number_input("Trial number", min_value=1, value=prior.get("trial", 1), step=1)
        save = st.form_submit_button("Save observed result", type="primary")
    if save:
        candidate.setdefault("observation_history", []).append(copy.deepcopy(prior))
        candidate["observation"] = {"bubble": b, "phase": phase, "notes": notes, "semester": semester.strip(),
                                    "group": group.strip(), "instructor": instructor.strip(),
                                    "date": performed.isoformat() if performed else "", "trial": trial, "recorded": pr.now()}
        candidate["status"] = "Observed" if b or phase else "Planned"
        pr.append_event(p, "Observation recorded", candidate["formula"])
        st.success("Observed result saved alongside the original hypothesis.")
    if candidate.get("observation_history") and st.button("Undo last observation edit"):
        candidate["observation"] = candidate["observation_history"].pop()
        candidate["status"] = "Observed" if candidate["observation"] else "Planned"
        pr.append_event(p, "Observation restored", candidate["formula"])
        st.rerun()
    observation = candidate.get("observation", {})
    if observation.get("bubble") and observation.get("phase"):
        raw = observation_record(candidate)
        _, issues = submission_table(raw, atomic)
        if not issues.empty and not candidate.get("added_to_dataset"):
            st.info("Complete these details before adding this observation to your submission.")
            st.dataframe(issues, hide_index=True, width="stretch")
        if st.button("Add observed experiment to project data", disabled=bool(candidate.get("added_to_dataset")) or not issues.empty):
            described = add_chemical_descriptors(clean_and_encode_data(raw, atomic), atomic, en, radii)
            st.session_state.manual_entries = pd.concat([st.session_state.manual_entries, described], ignore_index=True)
            candidate["added_to_dataset"] = True
            pr.append_event(p, "Experiment added to dataset", candidate["formula"])
            st.rerun()
        if candidate.get("added_to_dataset"):
            st.caption("Added as a dataset snapshot. Later notebook edits do not silently change that record.")


def share(df: pd.DataFrame, issues: pd.DataFrame, outliers: pd.DataFrame, store) -> None:
    st.subheader("Share findings")
    p = st.session_state.project
    from submissions import render_submission_download
    render_submission_download(st.session_state.manual_entries, load_atomic_table_from_bytes(None))
    st.divider()
    manifest = current_manifest(df)
    public = public_view(df)
    st.caption("Analysis files use the active scope. Portable project bundles contain the whole project, without contact columns.")
    cols = st.columns(2)
    with cols[0]:
        st.download_button("Analysis data · CSV", dataframe_to_csv_bytes(public), "catalyst_analysis.csv", "text/csv")
        st.download_button("Analysis data · Excel", dataframe_to_excel_bytes(public), "catalyst_analysis.xlsx")
        st.download_button("Validation report", dataframe_to_csv_bytes(public_view(issues)), "validation.csv", "text/csv")
        st.download_button("Outlier report", dataframe_to_csv_bytes(public_view(outliers)), "outliers.csv", "text/csv")
    with cols[1]:
        st.download_button("Analysis provenance · JSON", json.dumps(manifest, indent=2), "analysis_manifest.json", "application/json")
        st.download_button("Portable project · JSON", pr.bundle_bytes(p), "catalyst_project.json", "application/json")
        st.caption("Project bundles include hypothesis text and notes. Review free-text notes before sharing.")
    if access.is_instructor():
        with st.expander("Instructor exports · includes identifiable records"):
            st.download_button("Full scoped dataset · CSV", dataframe_to_csv_bytes(df), "instructor_data.csv", "text/csv")
            st.download_button("Full scoped dataset · Excel", dataframe_to_excel_bytes(df), "instructor_data.xlsx")
    st.markdown("#### Research report")
    report_context = hashlib.sha256(json.dumps({"manifest": manifest, "candidates": p["candidates"],
                                               "name": p["name"]}, sort_keys=True).encode()).hexdigest()
    if st.button("Build report with model evaluation"):
        settings = dict(use_phase=st.session_state.get("model_mode") == "Analyze known phase",
                        use_mass=st.session_state.get("include_mass", False),
                        evaluation={"Unseen compositions": "composition", "Held-out semester": "semester", "Stratified rows": "rows"}.get(st.session_state.get("evaluation_mode"), "composition"),
                        holdout_semester=st.session_state.get("holdout_semester", ""))
        with st.spinner("Preparing the report…"):
            b = train_ml_model(df, **settings)
            q = train_purity_model(df, **{k:v for k,v in settings.items() if k != "use_phase"})
            sections = []
            for title, result in [("Bubble response", b), ("Purity", q)]:
                if result.get("ok"):
                    text = f"{result['evaluation']}: accuracy {result['accuracy']:.0%}, baseline {result['baseline_accuracy']:.0%}, n={result['testing_rows']}. {result['overfit_warning']}"
                else:
                    text = result["message"]
                sections.append(f"<h2>{title}</h2><p>{escape(text)}</p>")
            report = f"""<!doctype html><html lang="en"><meta charset="utf-8"><title>Catalyst research report</title>
            <style>body{{font:16px/1.6 system-ui;max-width:920px;margin:3rem auto;color:#182d40;padding:1rem}}h1,h2{{color:#126773}}table{{border-collapse:collapse;width:100%}}td,th{{padding:.4rem;border-bottom:1px solid #ddd;text-align:left}}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}@media print{{body{{margin:0}}}}</style>
            <h1>{escape(p['name'])}</h1><p>Generated {escape(pr.now())} · {len(df)} compounds in scope</p>
            <p>Bubble: {escape(wilson(df.get('BubbleYes', pd.Series(dtype=float))))}<br>Purity: {escape(wilson(df.get('PureYes', pd.Series(dtype=float))))}</p>
            <p>Unknown outcomes are excluded. Intervals assume independent observations. Predictions are exploratory scores, not calibrated probabilities.</p>
            {''.join(sections)}<h2>Saved hypotheses (whole project)</h2>
            {pd.DataFrame([{'Formula':c['formula'], 'Rationale':c['rationale'], 'Status':c.get('status','Planned')} for c in p['candidates']]).to_html(index=False, escape=True)}
            <h2>Reproducibility manifest</h2><pre>{escape(json.dumps(manifest, indent=2))}</pre></html>"""
            st.session_state.research_report = (report_context, report)
    cached = st.session_state.get("research_report")
    if cached and cached[0] == report_context:
        st.download_button("Download printable report · HTML", cached[1], "catalyst_report.html", "text/html")
    with st.expander("Project history & restore"):
        st.dataframe(pd.DataFrame(p["history"]), hide_index=True, width="stretch")
        if store:
            revisions = store.revisions(p["id"])
            if revisions:
                revision = st.selectbox("Saved revision", revisions, format_func=lambda r:r[:12])
                st.caption("Restore preserves the other saved revisions. Contact columns are not stored in project snapshots.")
                if st.button("Restore this revision"):
                    restored = store.load(p["id"], revision)
                    pr.append_event(restored, "Revision restored", revision)
                    activate(restored)
                    st.rerun()
        else:
            st.caption("Open a downloaded project bundle to restore work. Enable local storage or sign in for automatic disk snapshots.")


def run() -> None:
    import app as views
    st.set_page_config(page_title="Catalyst Insight Studio", page_icon="🧪", layout="wide")
    owner = access.storage_owner()
    if st.session_state.get("_store_owner", owner) != owner:
        st.session_state.clear()
    st.session_state._store_owner = owner
    store = pr.ProjectStore(owner) if owner else None
    sync_project(store)  # Capture edits made immediately before a rerun.
    st.sidebar.markdown("## Catalyst\nInsight Studio")
    from design import inject_styles
    inject_styles()
    set_chart_theme(st.context.theme.type or "light")
    access.render_account()
    sidebar_projects(store)
    if "project" not in st.session_state:
        st.markdown("# From observation to discovery")
        st.write("A research workspace for chemistry students and instructors. Prepare class data, investigate patterns, and design experiments with an evidence trail.")
        cols = st.columns(3)
        for col, title, text in zip(cols, ["01 · Prepare", "02 · Investigate", "03 · Test & reflect"],
                                   ["Clean spreadsheet records and review unknowns.", "Connect chemical descriptors with observed results.", "Save hypotheses, record outcomes, and share reproducible findings."]):
            with col:
                with st.container(border=True):
                    st.markdown(f"### {title}"); st.write(text)
        st.info("Students: choose Start a blank results sheet in the sidebar, record each experiment, "
                "then download your student submission CSV for the LMS. No sample data or login is required for entry.")
        return
    p = st.session_state.project
    st.sidebar.text_input("Project name", max_chars=200, key="project_name")
    page = st.sidebar.radio("Research workspace", PAGES, key="workspace_page")
    if st.session_state.get("save_error"):
        st.sidebar.error("Autosave failed. Download a project bundle to preserve work.")
    elif store:
        st.sidebar.caption("Autosave on · version " + st.session_state.get("saved_revision", "pending")[:10])
    else:
        st.sidebar.caption("Session workspace · download a project bundle to keep your work")
    atomic = load_atomic_table_from_bytes(None)
    en = load_en_table_from_bytes(None)
    radii = load_radii_table_from_bytes(None)
    raw = st.session_state.raw_long
    fixed, corrections = apply_element_fixes(raw, st.session_state.element_fixes)
    clean = clean_and_encode_data(fixed, atomic)
    described = add_chemical_descriptors(clean, atomic, en, radii)
    manual = st.session_state.manual_entries
    if not manual.empty:
        manual = add_chemical_descriptors(clean_and_encode_data(pr.anonymous_data(manual), atomic), atomic, en, radii)
        st.session_state.manual_entries = manual
        described = pd.concat([described, manual], ignore_index=True)
    described, cleaning_log = remove_invalid_element_rows(described, atomic)
    scoped = choose_scope(described)
    sync_project(store)
    st.title(st.session_state.project_name)
    st.caption(f"{page} · {len(scoped):,} / {len(described):,} compounds · dataset {pr.fingerprint(pr.anonymous_data(scoped))[:10]}")
    warnings = st.session_state.get("mapping_warnings", [])
    for warning in warnings:
        st.warning(warning)
    issues = validate_compound_rows(scoped, atomic)
    if not access.is_instructor():
        issues = public_view(issues)
    if page == "Overview":
        overview(scoped, issues, atomic, en, radii)
    elif page == "Prepare data":
        st.subheader("Prepare data")
        action = st.selectbox("Task", ["Review quality", "Add an observation", "Combine submission CSVs", "Import another semester"] +
                              (["Combine student files"] if access.is_instructor() else []), key="prepare_task")
        if action == "Review quality":
            z = st.slider("Outlier sensitivity", 2.0, 5.0, 3.0, .25)
            # Corrections concern source records, including excluded invalid elements.
            source_scope = fixed.copy()
            for col, key in [("Semester", "scope_semesters"), ("Instructor", "scope_instructors"), ("LabGroup", "scope_groups")]:
                selected = st.session_state.get(key, [])
                if selected and col in source_scope:
                    source_scope = source_scope[source_scope[col].astype(str).isin(selected)]
            proposals = propose_element_fixes(source_scope, atomic)
            def scoped_log(log):
                if log.empty or "SourceRow" not in source_scope:
                    return log
                keys = set(zip(source_scope["SourceRow"].astype(str), source_scope["Slot"].astype(str)))
                return log[[key in keys for key in zip(log["Row"].astype(str), log["Slot"].astype(str))]]
            views.render_check_tab(scoped, issues, detect_numeric_outliers(scoped, z), scoped_log(cleaning_log),
                                   proposals, scoped_log(corrections), valid_element_symbols(atomic))
        elif action == "Add an observation":
            views.render_add_compound_tab(atomic, en, radii)
        elif action == "Combine submission CSVs":
            from submissions import render_submission_intake
            render_submission_intake(described, atomic)
        elif action == "Import another semester":
            st.caption("Dataset maintenance uses the whole project. The merged download can be opened as a new versioned project.")
            whole = pd.concat([fixed, pr.anonymous_data(manual)], ignore_index=True)
            views.render_new_semester_tab(public_view(whole))
        else:
            views.render_combine_tab(fixed, atomic, en, radii)
    elif page == "Investigate":
        if scoped.empty:
            st.info("No compounds in scope. Adjust the sidebar filters.")
        else:
            view = st.segmented_control("Investigation view", ["Outcomes", "Relationships", "Structure", "Compound details"], default="Outcomes", key="investigation_view")
            if view == "Outcomes": views.render_explore_tab(scoped)
            elif view == "Relationships": views.render_heatmap_tab(scoped)
            elif view == "Structure": views.render_pca_tab(scoped)
            elif view == "Compound details": compound_details(scoped)
    elif page == "Experiment Designer":
        designer(scoped, atomic, en, radii)
    elif page == "Lab notebook":
        notebook(atomic, en, radii)
    elif page == "Share findings":
        share(scoped, issues, detect_numeric_outliers(scoped), store)
    sync_project(store)
