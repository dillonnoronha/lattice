"""Student result files and conservative, repeat-safe class intake."""
from __future__ import annotations

from datetime import date
import hashlib
import json
import math
import re

import pandas as pd

SUBMISSION_COLUMNS = ["ExperimentID", "LabGroup", "Instructor", "Semester", "ExperimentDate", "Trial",
                      "A", "AN", "AP", "APN", "B", "BN", "BP", "BPN", "BDP", "BDPN",
                      "O", "ON", "P", "Bub", "ObservationNotes"]


# Prepare the Student submission fields and report every invalid recorded observation.
def submission_table(entries: pd.DataFrame, atomic: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Validate every recorded row; never silently drop a student's observations."""
    from pipeline import clean_and_encode_data, validate_compound_rows
    if entries.empty:
        return pd.DataFrame(columns=SUBMISSION_COLUMNS), pd.DataFrame()
    clean = clean_and_encode_data(entries.reset_index(drop=True), atomic)
    issues = validate_compound_rows(clean, atomic).to_dict("records")
    for index, row in clean.iterrows():
        # Record a problem with a specific field in the current observation.
        def issue(field, message):
            issues.append({"Row": index + 1, "Field": field, "Issue": message})
        for field in ["LabGroup", "Instructor", "Semester"]:
            value = row.get(field)
            if pd.isna(value) or not str(value).strip():
                issue(field, "Required for a class submission.")
        if not re.fullmatch(r"[a-f0-9]{32}", str(row.get("ExperimentID", ""))):
            issue("ExperimentID", "Missing/invalid experiment ID; use the student entry form.")
        try:
            date.fromisoformat(str(row.get("ExperimentDate", "")))
        except ValueError:
            issue("ExperimentDate", "Choose the date this experiment was performed.")
        trial = pd.to_numeric(row.get("Trial"), errors="coerce")
        if pd.isna(trial) or not math.isfinite(trial) or trial < 1 or trial != int(trial):
            issue("Trial", "Trial number must be a positive whole number.")
        if row.get("P") == "not made" and row.get("Bub") != "not tested":
            issue("Bub", "For a compound that was not made, record not tested rather than a bubble result.")
    ids = clean.get("ExperimentID", pd.Series("", index=clean.index)).fillna("").astype(str)
    duplicate_ids = ids.ne("") & ids.duplicated(keep=False)
    for index in clean.index[duplicate_ids]:
        issues.append({"Row": index + 1, "Field": "ExperimentID",
                       "Issue": "Each observation must have a unique experiment ID within a submission."})
    return clean.reindex(columns=SUBMISSION_COLUMNS), pd.DataFrame(issues)


# Convert a notebook's measured result into an observation suitable for Student submission.
def observation_record(candidate: dict) -> pd.DataFrame:
    """Turn a saved notebook observation into the same record as the entry form."""
    from projects import decode_frame
    raw = decode_frame(candidate["row"])
    observation = candidate.get("observation", {})
    for column, key in {"Bub": "bubble", "P": "phase", "Semester": "semester",
                        "LabGroup": "group", "Instructor": "instructor", "ExperimentDate": "date",
                        "ObservationNotes": "notes"}.items():
        raw[column] = observation.get(key, "")
    raw["Trial"] = observation.get("trial", 1)
    raw["SourceRow"] = raw["ExperimentID"] = candidate["id"]
    raw["Slot"] = 1
    return raw


# Count received experiments and confirmed outcomes by section, semester, and lab group.
def submission_summary(frame: pd.DataFrame) -> pd.DataFrame:
    """Counts by section, semester and anonymous group, without inferring missing students."""
    if frame.empty or "LabGroup" not in frame:
        return pd.DataFrame()
    data = frame.reindex(columns=["Instructor", "Semester", "LabGroup", "Bub", "P"]).fillna("")
    data = data[data.LabGroup.astype(str).str.strip().ne("")].copy()
    data["Confirmed bubble tests"] = data.Bub.isin(["yes", "no"]).astype(int)
    data["Confirmed phases"] = data.P.isin(["pure", "impure"]).astype(int)
    return data.groupby(["Instructor", "Semester", "LabGroup"], dropna=False, sort=True).agg(
        Experiments=("Bub", "size"), **{"Confirmed bubble tests": ("Confirmed bubble tests", "sum"),
                                    "Confirmed phases": ("Confirmed phases", "sum")}).reset_index()


# Build comparison labels that distinguish unchanged resubmissions from separate trials.
def duplicate_keys(frame: pd.DataFrame) -> pd.Series:
    """Only explicit experiment IDs plus identical recorded content establish a duplicate.

    Identical chemistry does not identify an experiment. Legacy rows without IDs are
    deliberately preserved, even if they look identical. Conflicting versions are retained.
    """
    numeric = {"AN", "APN", "BN", "BPN", "BDPN", "ON", "Trial"}
    # Combine one experiment's ID and standardized contents for duplicate checking.
    def key(row):
        identity = row.get("ExperimentID", "")
        if pd.isna(identity) or not str(identity).strip():
            return None
        values = []
        for column in SUBMISSION_COLUMNS + ["GroupNumber"]:
            value = row.get(column, "")
            if pd.isna(value):
                value = ""
            if column in numeric and str(value).strip():
                parsed = pd.to_numeric(value, errors="coerce")
                value = f"{float(parsed):.17g}" if pd.notna(parsed) else str(value).strip()
            values.append(str(value).strip())
        return tuple(values)
    return frame.apply(key, axis=1) if not frame.empty else pd.Series(dtype=object)


# Find different recorded versions of the same experiment for human review.
def conflicting_experiments(frame: pd.DataFrame) -> pd.DataFrame:
    """Identify repeated IDs with different contents; no automatic winner is selected."""
    if frame.empty or "ExperimentID" not in frame:
        return frame.iloc[:0].copy()
    frame = frame.reset_index(drop=True)
    keys = duplicate_keys(frame)
    ids = frame["ExperimentID"].fillna("").astype(str).str.strip()
    conflicts = {identifier for identifier, positions in ids.groupby(ids).groups.items()
                 if identifier and len(set(keys.loc[positions])) > 1}
    return frame[ids.isin(conflicts)].copy()


# Offer the Student CSV download only when all recorded observations pass validation.
def render_submission_download(entries: pd.DataFrame, atomic: pd.DataFrame) -> None:
    import streamlit as st
    from pipeline import dataframe_to_csv_bytes
    table, issues = submission_table(entries, atomic)
    st.markdown("#### Submit your recorded results")
    st.caption("One CSV contains all observations you added to this project, regardless of analysis filters. "
               "It excludes sample/class imports and unperformed predictions. Submit the file through your course LMS.")
    if table.empty:
        st.info("Add a validated observation first. Sample data and predictions are not submissions.")
        return
    if not issues.empty:
        st.warning("Complete these fields before downloading a class submission.")
        st.dataframe(issues, hide_index=True, width="stretch")
        return
    st.dataframe(table, hide_index=True, width="stretch")
    st.download_button("Download student submission CSV", dataframe_to_csv_bytes(table),
                       file_name="lattice_student_results.csv", mime="text/csv", type="primary",
                       key="download_student_submission")
    st.caption(f"{len(table)} experiment(s). Keep the experiment IDs unchanged when resubmitting the same file. "
               "Use a new entry for a real repeat trial. Do not enter student names or emails in notes or group codes.")


# Show uploaded observations with delete, confirmation, and restore controls for this batch.
def render_intake_review(combined: pd.DataFrame, batch_key: str = "") -> pd.DataFrame:
    """Keep explicit row exclusions for this exact batch across Streamlit reruns."""
    import streamlit as st
    from pipeline import reconstruct_formula

    signature = hashlib.sha256((batch_key + combined.to_json(orient="split")).encode()).hexdigest()
    review = st.session_state.get("intake_review")
    if not review or review["signature"] != signature:
        review = {"signature": signature, "deleted": set(), "pending": None}
        st.session_state.intake_review = review

    # Select the exact uploaded row whose deletion needs confirmation.
    def request_delete(index):
        review["pending"] = index

    # Exclude the confirmed row from this batch's combined results.
    def confirm_delete(index):
        review["deleted"].add(index)
        review["pending"] = None

    # Cancel the pending deletion and keep the uploaded row.
    def cancel_delete():
        review["pending"] = None

    # Bring back all rows deleted during the current batch review.
    def restore():
        review["deleted"].clear()
        review["pending"] = None

    kept = combined.drop(index=list(review["deleted"]))
    st.markdown("#### Review uploaded observations")
    st.caption("Delete a row to exclude it from the combined class CSV and new class project. "
               "Original files and the current project stay unchanged. Changing the uploaded batch "
               "or included project data resets this review.")
    if review["deleted"]:
        st.info(f"{len(review['deleted'])} observation(s) deleted from this batch · {len(kept)} remaining")
        st.button("Restore deleted rows", key="restore_intake_rows", on_click=restore)
    for index, row in kept.iterrows():
        summary, action = st.columns([5, 1])
        formula = reconstruct_formula(row)
        summary.write(f"Row {index + 1} · {formula} · trial {row.get('Trial', '')} · "
                      f"{row.get('P', '')} · bubbles: {row.get('Bub', '')}")
        summary.caption(f"{row.get('LabGroup', '')} · {row.get('Instructor', '')} · "
                        f"{row.get('Semester', '')} · {row['_IntakeFile']} · "
                        f"source row {row['_IntakeRow']} · ID {row.get('ExperimentID', '')}")
        action.button("Delete row", key=f"intake_delete_{signature}_{index}",
                      on_click=request_delete, args=(index,))
        if review["pending"] == index:
            st.warning(f"Remove row {index + 1} ({formula}) from this combined batch?")
            confirm, cancel = st.columns(2)
            confirm.button("Confirm row deletion", key=f"intake_confirm_{signature}_{index}",
                           on_click=confirm_delete, args=(index,))
            cancel.button("Keep row", key=f"intake_cancel_{signature}_{index}", on_click=cancel_delete)
    with st.expander("View full combined table"):
        st.dataframe(kept.reindex(columns=SUBMISSION_COLUMNS), hide_index=True, width="stretch")
    return kept


# Check remaining uploaded rows and link each problem to its original file and row.
def intake_validation_issues(reviewed: pd.DataFrame, atomic: pd.DataFrame) -> pd.DataFrame:
    """Validate remaining uploaded rows, preserving file and source-row attribution."""
    uploaded = reviewed.loc[reviewed["_IntakeValidate"]].reset_index(drop=True)
    uploaded["SourceRow"] = range(1, len(uploaded) + 1)
    _, issues = submission_table(uploaded, atomic)
    if not issues.empty:
        sources = uploaded.iloc[issues.Row.to_numpy(dtype=int) - 1]
        issues.insert(0, "File", sources["_IntakeFile"].to_numpy())
        issues["Row"] = sources["_IntakeRow"].to_numpy()
    return issues


# Combine and review Student CSVs, then export or open the accepted class results.
def render_submission_intake(existing: pd.DataFrame, atomic: pd.DataFrame) -> None:
    """Anonymous submission intake; the separate full-contact combine tool stays gated."""
    import streamlit as st
    from pipeline import read_table_from_bytes, normalize_to_long_format, combine_long_tables, dataframe_to_csv_bytes
    st.caption("Upload the CSVs downloaded with 'Download student submission CSV'. "
               "This tool combines allowlisted result fields only; it does not import student contact columns.")
    uploads = st.file_uploader("Student submission CSVs", type=["csv"], accept_multiple_files=True, key="student_intake")
    include = st.checkbox("Include the whole current project dataset", value=not existing.empty)
    if not uploads:
        st.session_state.pop("intake_review", None)
        return
    frames, problems = [], []
    for upload in uploads:
        try:
            source = read_table_from_bytes(upload.getvalue(), upload.name)
            if not set(SUBMISSION_COLUMNS).issubset(source.columns):
                raise ValueError("Use the student submission download, not an analysis export or the old survey file.")
            rows, _ = normalize_to_long_format(source[SUBMISSION_COLUMNS])
            table, _ = submission_table(rows, atomic)
            if table.empty:
                raise ValueError("No experiments found in this submission.")
            table["_IntakeFile"] = upload.name
            table["_IntakeRow"] = range(1, len(table) + 1)
            table["_IntakeValidate"] = True
            frames.append(table)
        except (ValueError, KeyError) as exc:
            problems.append({"File": upload.name, "Issue": str(exc)})
    if problems:
        st.session_state.pop("intake_review", None)
        st.error("No files have been applied. Resolve these submissions before combining the batch.")
        st.dataframe(pd.DataFrame(problems), hide_index=True)
        return
    if include and not existing.empty:
        current = existing.reindex(columns=SUBMISSION_COLUMNS).copy()
        current["_IntakeFile"] = "Current project"
        current["_IntakeRow"] = range(1, len(current) + 1)
        current["_IntakeValidate"] = False  # Legacy imports need not have submission metadata.
        frames.insert(0, current)
    combined, removed = combine_long_tables(frames)
    batch_key = json.dumps({"uploads": [(u.name, hashlib.sha256(u.getvalue()).hexdigest()) for u in uploads],
                            "include_project": include})
    reviewed = render_intake_review(combined, batch_key)
    combined = reviewed.reindex(columns=SUBMISSION_COLUMNS).reset_index(drop=True)
    conflicts = conflicting_experiments(combined)
    st.write(f"{len(combined)} experiments · {removed} unchanged resubmitted rows removed")
    if combined.empty:
        st.info("No observations remain. Restore deleted rows or upload another batch to continue.")
        return
    issues = intake_validation_issues(reviewed, atomic)
    if not conflicts.empty:
        st.error("An experiment ID has different versions. Delete the incorrect row above or correct the source files before importing.")
        st.dataframe(conflicts, hide_index=True, width="stretch")
    if not issues.empty:
        st.error("Some uploaded observations have validation issues. Delete the incorrect rows above "
                 "or correct the source files before downloading or importing this batch.")
        st.dataframe(issues, hide_index=True, width="stretch")
    if not conflicts.empty or not issues.empty:
        return
    st.markdown("#### Submission coverage")
    st.dataframe(submission_summary(combined), hide_index=True, width="stretch")
    st.caption("Counts show received experiments by section and lab group. Compare with your roster to identify missing submissions.")
    st.download_button("Download combined class CSV", dataframe_to_csv_bytes(combined),
                       "lattice_class_results.csv", "text/csv")
    if st.button("Open combined class results as a new project", type="primary"):
        import projects as pr
        from workspace_ui import activate
        normalized, _ = normalize_to_long_format(combined)
        project = pr.new_project("Class results")
        project["source"] = "Student submission collection"
        project["dataset"] = pr.encode_frame(pr.anonymous_data(normalized))
        pr.append_event(project, "Student submissions combined", f"{len(uploads)} files; {len(combined)} experiments")
        deleted = len(st.session_state.intake_review["deleted"])
        if deleted:
            pr.append_event(project, "Uploaded observations excluded", f"{deleted} rows deleted during submission review.")
        activate(project, normalized)
        st.rerun()
