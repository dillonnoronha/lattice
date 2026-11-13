"""Student result files and conservative, repeat-safe class intake."""
from __future__ import annotations

from datetime import date
import math
import re

import pandas as pd

SUBMISSION_COLUMNS = ["ExperimentID", "LabGroup", "Instructor", "Semester", "ExperimentDate", "Trial",
                      "A", "AN", "AP", "APN", "B", "BN", "BP", "BPN", "BDP", "BDPN",
                      "O", "ON", "P", "Bub", "ObservationNotes"]


def submission_table(entries: pd.DataFrame, atomic: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Validate every recorded row; never silently drop a student's observations."""
    from pipeline import clean_and_encode_data, validate_compound_rows
    if entries.empty:
        return pd.DataFrame(columns=SUBMISSION_COLUMNS), pd.DataFrame()
    clean = clean_and_encode_data(entries.reset_index(drop=True), atomic)
    issues = validate_compound_rows(clean, atomic).to_dict("records")
    for index, row in clean.iterrows():
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


def duplicate_keys(frame: pd.DataFrame) -> pd.Series:
    """Only explicit experiment IDs plus identical recorded content establish a duplicate.

    Identical chemistry does not identify an experiment. Legacy rows without IDs are
    deliberately preserved, even if they look identical. Conflicting versions are retained.
    """
    numeric = {"AN", "APN", "BN", "BPN", "BDPN", "ON", "Trial"}
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
                       file_name="catalyst_student_results.csv", mime="text/csv", type="primary",
                       key="download_student_submission")
    st.caption(f"{len(table)} experiment(s). Keep the experiment IDs unchanged when resubmitting the same file. "
               "Use a new entry for a real repeat trial. Do not enter student names or emails in notes or group codes.")


def render_submission_intake(existing: pd.DataFrame, atomic: pd.DataFrame) -> None:
    """Anonymous submission intake; the separate full-contact combine tool stays gated."""
    import streamlit as st
    from pipeline import read_table_from_bytes, normalize_to_long_format, combine_long_tables, dataframe_to_csv_bytes
    st.caption("Upload the CSVs downloaded with 'Download student submission CSV'. "
               "This tool combines allowlisted result fields only; it does not import student contact columns.")
    uploads = st.file_uploader("Student submission CSVs", type=["csv"], accept_multiple_files=True, key="student_intake")
    include = st.checkbox("Include the whole current project dataset", value=not existing.empty)
    if not uploads:
        return
    frames, problems = [], []
    for upload in uploads:
        try:
            source = read_table_from_bytes(upload.getvalue(), upload.name)
            if not set(SUBMISSION_COLUMNS).issubset(source.columns):
                raise ValueError("Use the student submission download, not an analysis export or the old survey file.")
            rows, _ = normalize_to_long_format(source[SUBMISSION_COLUMNS])
            table, issues = submission_table(rows, atomic)
            if table.empty:
                raise ValueError("No experiments found in this submission.")
            if not issues.empty:
                problems.extend({"File": upload.name, **issue} for issue in issues.to_dict("records"))
                continue
            frames.append(table)
        except (ValueError, KeyError) as exc:
            problems.append({"File": upload.name, "Issue": str(exc)})
    if problems:
        st.error("No files have been applied. Resolve these submissions before combining the batch.")
        st.dataframe(pd.DataFrame(problems), hide_index=True)
        return
    if include and not existing.empty:
        frames.insert(0, existing.reindex(columns=SUBMISSION_COLUMNS))
    combined, removed = combine_long_tables(frames)
    conflicts = conflicting_experiments(combined)
    st.write(f"{len(combined)} experiments · {removed} unchanged resubmitted rows removed")
    if not conflicts.empty:
        st.error("An experiment ID has different versions. Resolve which observation is correct before importing; neither version was silently discarded.")
        st.dataframe(conflicts, hide_index=True, width="stretch")
        return
    st.dataframe(combined, hide_index=True, width="stretch")
    st.markdown("#### Submission coverage")
    st.dataframe(submission_summary(combined), hide_index=True, width="stretch")
    st.caption("Counts show received experiments by section and lab group. Compare with your roster to identify missing submissions.")
    st.download_button("Download combined class CSV", dataframe_to_csv_bytes(combined),
                       "catalyst_class_results.csv", "text/csv")
    if st.button("Open combined class results as a new project", type="primary"):
        import projects as pr
        from workspace_ui import activate
        normalized, _ = normalize_to_long_format(combined)
        project = pr.new_project("Class results")
        project["source"] = "Student submission collection"
        project["dataset"] = pr.encode_frame(pr.anonymous_data(normalized))
        pr.append_event(project, "Student submissions combined", f"{len(uploads)} files; {len(combined)} experiments")
        activate(project, normalized)
        st.rerun()
