"""Reusable data preparation and investigation views.

The research workspace is orchestrated by workspace_ui.py. Scientific transforms
and charts live in pipeline.py; models, storage, access, and styling have their
own modules. Run with: streamlit run app.py.
"""
from __future__ import annotations

import re
import uuid

import numpy as np
import pandas as pd
import streamlit as st

from pipeline import (
    add_chemical_descriptors,
    bubble_relationships,
    clean_and_encode_data,
    combine_long_tables,
    compute_pca,
    dataframe_to_csv_bytes,
    dataframe_to_excel_bytes,
    display_label,
    element_outcome_summary,
    find_merge_duplicates,
    friendly_label,
    glossary_table,
    label_count_table,
    mixing_summary,
    normalize_bubble_label,
    normalize_phase_label,
    normalize_to_long_format,
    numeric_correlation_table,
    ordered_columns,
    plot_heatmap,
    plot_pca_scatter,
    plot_periodic_heat,
    public_view,
    read_table_from_bytes,
    remove_invalid_element_rows,
    summarize_by_element,
    valid_element_symbols,
    validate_compound_rows,
)

# Shared Plotly toolbar config: keep zoom/pan/hover, hide the noisy extras.
PLOTLY_CONFIG = {
    "displaylogo": False,
    "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d", "zoomIn2d", "zoomOut2d"],
}

# Display the numbers in a chemical formula as subscripts.
def formula_html(formula: str) -> str:
    """Render a formula string like La2NiO4 with real subscripts."""

    from html import escape
    safe = escape(str(formula or ""))
    return '<span class="formula">' + re.sub(r"(\d+(?:\.\d+)?)", r"<sub>\1</sub>", safe) + "</span>"


# Check Instructor authorization before showing restricted information.
def instructor_mode_on() -> bool:
    """True only for an authorized, verified instructor identity."""

    from access import is_instructor
    return is_instructor()


# Choose which table columns the current user is allowed to see.
def visible(df: pd.DataFrame) -> pd.DataFrame:
    """Contact/group columns stay hidden for students, shown in instructor mode."""

    return df if instructor_mode_on() else public_view(df)


# Let the user review suggested corrections for unrecognized element symbols.
def render_did_you_mean(fix_proposals: pd.DataFrame, all_symbols: list) -> None:
    """Pre-cleaning panel: a table of invalid elements, each with a fix dropdown."""

    n = len(fix_proposals)
    with st.expander(f"🛠️ Fix invalid elements ({n} to review)", expanded=True):
        st.caption("Each row is an entry that isn't a real element symbol. The **Fix to** dropdown "
                   "is pre-set to the best guess — change it or pick **Remove row**, then click Apply.")

        editor_df = pd.DataFrame({
            "Row": fix_proposals["SourceRow"],
            "Slot": fix_proposals["Slot"],
            "Field": fix_proposals["Field"],
            "Invalid value": fix_proposals["Original"],
            "Did you mean": fix_proposals["Suggestions"].apply(
                lambda s: ", ".join(s) if s else "(no close match)"),
            "Fix to": fix_proposals["Suggestions"].apply(lambda s: s[0] if s else "Remove row"),
        })

        edited = st.data_editor(
            editor_df,
            hide_index=True,
            width="stretch",
            key="fix_editor",
            column_config={
                "Row": st.column_config.Column("Row", disabled=True),
                "Slot": st.column_config.Column("Slot", disabled=True),
                "Field": st.column_config.Column("Field", disabled=True),
                "Invalid value": st.column_config.Column("⚠️ Invalid value", disabled=True),
                "Did you mean": st.column_config.Column("Did you mean", disabled=True),
                "Fix to": st.column_config.SelectboxColumn(
                    "Fix to", options=["Remove row"] + all_symbols, required=True),
            },
        )

        col_a, col_b = st.columns([1, 4])
        with col_a:
            if st.button("Apply", type="primary", key="apply_element_fixes"):
                fixes = dict(st.session_state.element_fixes)
                for _, r in edited.iterrows():
                    key = f"{r['Row']}|{r['Slot']}|{r['Field']}"
                    if r["Fix to"] == "Remove row":
                        fixes.pop(key, None)          # no correction -> row is removed
                    else:
                        fixes[key] = r["Fix to"]      # replace with chosen symbol
                st.session_state.element_fixes = fixes
                st.rerun()
        with col_b:
            if st.session_state.element_fixes and st.button("Reset all corrections", key="reset_element_fixes"):
                st.session_state.element_fixes = {}
                st.rerun()


# Show data-entry problems, unusual values, and the available corrections.
def render_check_tab(described_df: pd.DataFrame, issues_df: pd.DataFrame,
                     outlier_df: pd.DataFrame, cleaning_log: pd.DataFrame,
                     fix_proposals: pd.DataFrame, corrections_log: pd.DataFrame,
                     all_symbols: list) -> None:
    """Tab 1 — surface data-entry problems before any analysis."""

    st.caption("Find and fix data-entry mistakes before using the data for graphs or ML.")

    if not fix_proposals.empty:
        render_did_you_mean(fix_proposals, all_symbols)

    # Privacy: email-match checks run in the background and are included in the
    # downloadable validation report, but are only shown in instructor mode.
    if not instructor_mode_on() and not issues_df.empty and "Field" in issues_df.columns:
        shown_issues = issues_df[issues_df["Field"] != "Email"].reset_index(drop=True)
        n_hidden = len(issues_df) - len(shown_issues)
    else:
        shown_issues, n_hidden = issues_df, 0

    check_cols = st.columns(2)
    with check_cols[0]:
        st.markdown("#### Validation issues")
        if shown_issues.empty:
            st.caption("No validation issues found. ✅")
        else:
            st.caption(f"{len(shown_issues):,} possible issues. Review before final analysis.")
        st.dataframe(visible(shown_issues), width="stretch", height=300)
        if n_hidden:
            st.caption(f"🔒 {n_hidden} email-match check(s) run in the background — see the "
                       "validation report in **Export** (instructor download).")
    with check_cols[1]:
        st.markdown("#### Possible numeric outliers")
        if outlier_df.empty:
            st.caption("No outliers at the current sensitivity. ✅")
        else:
            st.caption("Outliers aren't automatically wrong — just worth a second look.")
        st.dataframe(visible(outlier_df), width="stretch", height=300)

    st.markdown("#### Cleaned compound table")
    if described_df.empty:
        st.warning("No compound rows found. Check that the file uses columns like 1A, 1AN, 1B, 1BN, 1O, 1ON, 1P, 1Bub.")
    else:
        table = visible(described_df)
        st.dataframe(table[ordered_columns(table)], width="stretch", height=380)
        if instructor_mode_on():
            st.caption("🔓 Instructor mode — contact and group-member columns are visible.")
        else:
            st.caption("🔒 Contact and group-member info is collected but hidden in student views and exports.")

    n_removed = len(cleaning_log)
    n_fixed = len(corrections_log)
    with st.expander(f"What cleaning changed ({n_fixed} corrected, {n_removed} removed)"):
        if not corrections_log.empty:
            st.markdown("**Corrections applied (Did you mean?)**")
            st.dataframe(visible(corrections_log), width="stretch", hide_index=True)
        if not cleaning_log.empty:
            st.markdown("**Rows removed (invalid element)**")
            st.caption("Removed because they contained an element that isn't a real periodic-table symbol.")
            st.dataframe(visible(cleaning_log), width="stretch", hide_index=True)
        if corrections_log.empty and cleaning_log.empty:
            st.caption("No rows removed or corrected. Symbols, formatting, and placeholder text were standardized in place.")

    with st.expander("Data-entry rules"):
        st.markdown(
            "- Element **symbols**, not names: `La`, not `Lanthanum`.\n"
            "- **Numbers** for ratios: `2`, not `two`.\n"
            "- Oxygen is **O**. Phase is **pure** or **impure**. Bubble is **yes / no / maybe**."
        )


# Show outcome counts and compare results across elements and mixed compositions.
def render_explore_tab(described_df: pd.DataFrame) -> None:
    """Tab 2 — response counts, per-element summaries, and cation-mixing views."""

    st.caption("Descriptive tables only — patterns to discuss, not proof of cause.")

    hide_rare = st.checkbox("Hide elements with fewer than 3 compounds", value=True)
    min_rows = 3 if hide_rare else 1
    filtered = described_df.copy()

    if filtered.empty:
        st.warning("No rows match the selected filters.")
        return

    st.caption(f"Showing **{len(filtered):,}** of {len(described_df):,} compounds.")

    plot_df = filtered.copy()
    phase_src = "P_raw" if "P_raw" in plot_df.columns else "P"
    bub_src = "Bub_raw" if "Bub_raw" in plot_df.columns else "Bub"
    plot_df["PhasePlotLabel"] = plot_df[phase_src].apply(lambda v: display_label(normalize_phase_label(v)))
    plot_df["BubblePlotLabel"] = plot_df[bub_src].apply(lambda v: display_label(normalize_bubble_label(v)))

    st.markdown("#### Response counts")
    count_cols = st.columns(2)
    with count_cols[0]:
        st.markdown("**Bubble response**")
        st.dataframe(
            label_count_table(plot_df, "BubblePlotLabel", kind="bubble",
                              preferred_order=["Yes", "No", "Maybe", "Other / needs review", "Missing"]),
            width="stretch", hide_index=True,
        )
    with count_cols[1]:
        st.markdown("**Phase result**")
        st.dataframe(
            label_count_table(plot_df, "PhasePlotLabel", kind="phase",
                              preferred_order=["Pure", "Impure", "Not made", "Other / needs review", "Missing"]),
            width="stretch", hide_index=True,
        )

    # --- Periodic-table outcome view ---
    st.markdown("#### Periodic view — where the class has explored")
    scope_choice = st.radio("Show elements used on", ["Any site", "A-site (A/A′)", "B-site (B/B′/B″)"],
                            horizontal=True, key="periodic_scope")
    scope = {"Any site": "any", "A-site (A/A′)": "A", "B-site (B/B′/B″)": "B"}[scope_choice]
    element_stats = element_outcome_summary(filtered, scope=scope)
    if element_stats.empty:
        st.info("Not enough element data for this filter.")
    else:
        st.plotly_chart(plot_periodic_heat(element_stats), width="stretch", config=PLOTLY_CONFIG)
        st.caption("Color = bubble-yes rate for compounds using that element (red 0% → green 100%). "
                   "Gray elements haven't been tried yet — hover a tile for its numbers. "
                   "Use the confirmed-outcome counts below to assess support.")

    st.markdown("#### Elements vs. bubbling and purity")
    st.caption("Bubble yes % and Pure % for each element. Rates use confirmed outcomes only; unknowns are excluded from denominators.")

    a_summary = summarize_by_element(filtered, "A", min_rows=int(min_rows))
    b_summary = summarize_by_element(filtered, "B", min_rows=int(min_rows))
    view_cols = ["compounds", "bubble_observed", "bubble_yes_rate", "phase_observed", "pure_rate", "avg_formula_mass"]
    rename = {"compounds": "Compounds", "bubble_yes_rate": "Bubble yes %",
              "pure_rate": "Pure %", "avg_formula_mass": "Avg formula mass"}

    elem_cols = st.columns(2)
    with elem_cols[0]:
        st.markdown("**A-site elements**")
        if a_summary.empty:
            st.info("Not enough A-site data for this filter.")
        else:
            st.dataframe(a_summary[["A"] + view_cols].rename(columns=rename).round(1),
                         width="stretch", hide_index=True, height=300)
    with elem_cols[1]:
        st.markdown("**B-site elements**")
        if b_summary.empty:
            st.info("Not enough B-site data for this filter.")
        else:
            st.dataframe(b_summary[["B"] + view_cols].rename(columns=rename).round(1),
                         width="stretch", hide_index=True, height=300)

    # --- Cation mixing (instructor question #1: "is A/A' mixing reflected anywhere?") ---
    st.markdown("#### Cation mixing — A/A′ and B/B′")
    st.caption("Compounds where a site holds TWO OR MORE elements in differing amounts. "
               "The share columns show how much of the site the secondary cation takes "
               "(50% = a perfect 50/50 mix). The same information feeds the heatmap and the "
               "models as **A mixing frac** and **B mixing frac**.")
    mix_table = mixing_summary(filtered)
    if mix_table.empty:
        st.info("Not enough data to summarize cation mixing yet.")
    else:
        st.dataframe(mix_table, width="stretch", hide_index=True)

    with st.expander("Descriptor preview"):
        descriptor_cols = [c for c in [
            "Formula", "A_avg_Z", "B_avg_Z", "A_mix_fraction", "B_mix_fraction",
            "FormulaMass", "O_to_cation_ratio", "B_to_A_ratio", "BubbleLabel", "PhaseLabel",
        ] if c in filtered.columns]
        st.dataframe(filtered[descriptor_cols].round(4), width="stretch", height=300)


# Show which measured or calculated values tend to change together.
def render_heatmap_tab(described_df: pd.DataFrame) -> None:
    """Tab 3 — interactive correlation heatmap with matching links table + glossary."""

    st.caption("Each cell compares two numeric features — hover any cell for the exact value. "
               "Read the bubble and confirmed-purity rows for links to outcomes. "
               "Each correlation requires at least three paired observations; blank cells lack sufficient variation or evidence.")

    corr = numeric_correlation_table(described_df)
    if corr.empty:
        st.warning("Not enough numeric columns to build a relationship map.")
        return

    all_features = list(corr.columns)
    default_features = [c for c in [
        "BubbleYes", "PureYes", "A_avg_Z", "B_avg_Z", "FormulaMass",
        "O_to_cation_ratio", "B_to_A_ratio", "Avg_cation_Z",
        "A_mix_fraction", "B_mix_fraction", "Tolerance_factor",
    ] if c in all_features] or all_features

    selected = st.multiselect(
        "Features to compare",
        options=all_features,
        default=default_features,
        format_func=friendly_label,
        help="Keep confirmed bubbling and purity selected to compare outcome associations.",
    )
    if len(selected) < 2:
        st.info("Select at least two features. Showing defaults for now.")
        selected = default_features
    corr_view = corr.loc[selected, selected]

    map_cols = st.columns([1.25, 1])
    with map_cols[0]:
        st.plotly_chart(plot_heatmap(corr_view), width="stretch", config=PLOTLY_CONFIG)
    with map_cols[1]:
        st.markdown("#### Reading it")
        st.markdown("**+1** rise together · **0** no link · **−1** move in opposite directions. "
                    "Correlation is not causation.")

        st.markdown("#### Strongest links to bubbling")
        search_all = st.toggle(
            "Rank across all features", value=False,
            help="Off: this table ranks only the features shown on the map, so the two always match. "
                 "On: it searches every feature — items may then not appear on your map.",
        )
        rel = bubble_relationships(corr, restrict_to=None if search_all else selected)
        if search_all:
            st.caption("Ranking **all** features — add one to the map selection to see it in context.")
        else:
            st.caption("Ranking only the features shown on the map, so the table and map always match.")
        if rel.empty:
            st.info("Not available yet.")
        else:
            st.dataframe(rel.round(3), width="stretch", hide_index=True, height=280)

    # Glossary (instructor request: define the heat-map terms).
    with st.expander("📖 Glossary — what every term on this map means", expanded=False):
        glossary = glossary_table(selected)
        st.dataframe(
            glossary, width="stretch", hide_index=True,
            height=min(430, 38 * len(glossary) + 40),
            column_config={
                "Term": st.column_config.Column("Term", width="small"),
                "Meaning": st.column_config.Column("Meaning", width="large"),
            },
        )


# Display compounds on a two-dimensional similarity map, with optional grouping.
def render_pca_tab(described_df: pd.DataFrame) -> None:
    """Tab 4 — PCA structure map with optional KMeans clusters."""

    st.caption("Squeezes all numeric descriptors into a 2-D map. Nearby compounds have similar "
               "composition — hover any point to see its formula. Exploration only.")

    k = st.slider("KMeans clusters (0 = off)", min_value=0, max_value=8, value=0,
                  help="Group compounds into clusters by composition. Raise above 1 to see clusters.")

    result = compute_pca(described_df, n_clusters=k)
    if not result.get("ok"):
        st.info(result.get("message", "PCA not available."))
        return

    if result["has_clusters"]:
        color_by = st.radio("Color points by", ["Cluster", "Bubble", "Phase"], horizontal=True)
    else:
        color_by = st.radio("Color points by", ["Bubble", "Phase"], horizontal=True)

    ev = result["explained"]
    map_cols = st.columns([1.45, 1])
    with map_cols[0]:
        st.plotly_chart(plot_pca_scatter(result["coords"], color_by=color_by),
                        width="stretch", config=PLOTLY_CONFIG)
    with map_cols[1]:
        st.metric("PC1 variance", f"{ev[0]:.0%}")
        st.metric("PC2 variance", f"{ev[1]:.0%}")
        st.metric("Compounds plotted", f"{result['n_used']:,}")
        st.caption(f"PC1 + PC2 together explain {sum(ev):.0%} of the variation across "
                   f"{len(result['features'])} descriptors.")

    with st.expander("What drives each axis (loadings)", expanded=False):
        sort_pc = st.radio("Sort by biggest weight on", ["PC1", "PC2"], horizontal=True,
                           key="pca_loading_sort")
        st.caption(f"Sorted by influence on {sort_pc} (biggest absolute weight first). "
                   "Bigger absolute values = the descriptor pushes a compound further along that axis.")
        loadings = result["loadings"].copy()
        loadings = loadings.reindex(loadings[sort_pc].abs().sort_values(ascending=False).index)
        loadings.index = [friendly_label(i) for i in loadings.index]
        loadings.index.name = "Descriptor"
        st.dataframe(loadings.round(2), width="stretch")


# Let Students enter, validate, edit, delete, and download their recorded experiments.
def render_add_compound_tab(atomic: pd.DataFrame, en_table: pd.DataFrame, radii: pd.DataFrame) -> None:
    """Tab 6 — build and stage a new compound by hand for this session."""

    st.caption("Record one performed experiment per entry. Use a new entry for each repeat trial. "
               "Enter measured outcomes, not predictions; no student names or emails.")
    if st.session_state.get("editing_entry_id"):
        st.info(f"Editing recorded experiment {st.session_state.editing_entry_id[:8]}. Saving replaces that observation.")
        if st.button("Cancel edit and start a new observation"):
            st.session_state.pop("editing_entry_id", None)
            st.session_state.pending_manual_entry = pd.DataFrame()
            st.session_state.pending_manual_issues = pd.DataFrame()
            for key in ["add_phase", "add_bub", "add_notes"]:
                st.session_state.pop(key, None)
            st.rerun()

    symbols = valid_element_symbols(atomic)
    optional_symbols = [""] + symbols

    # Build an element dropdown, including a blank choice for unused sites.
    def element_select(label: str, key: str, default: str = "", optional: bool = True):
        options = optional_symbols
        index = options.index(default) if default in options else 0
        return st.selectbox(label, options, index=index, key=key,
                            format_func=lambda s: s if s else "— none —")

    with st.form("add_compound_form"):
        m1, m2, m3 = st.columns(3)
        with m1:
            new_group = st.text_input("Lab group code (no names)", value="", key="add_group")
            new_semester = st.text_input("Semester / Year", value="", placeholder="e.g. Fall 2026", key="add_semester")
            new_date = st.date_input("Experiment date", value=None, key="add_date")
        with m2:
            new_instructor = st.text_input("Instructor / Section", value="", key="add_instructor")
            new_phase = st.selectbox("Phase", ["", "pure", "impure", "not made"], key="add_phase",
                                     format_func=lambda s: s or "Choose observed phase…")
            new_trial = st.number_input("Trial number", min_value=1, value=1, step=1, key="add_trial")
        with m3:
            new_bub = st.selectbox("Bubble response", ["", "yes", "no", "maybe", "not tested"], key="add_bub",
                                   format_func=lambda s: s or "Choose observed response…")
            new_notes = st.text_area("Observation notes (no names/emails)", key="add_notes", max_chars=2000)
            st.caption("Maybe = tested but ambiguous. Not tested = the test was not performed.")

        st.markdown("#### Formula parts")
        a_col, b_col, o_col = st.columns(3)
        with a_col:
            new_a = element_select("A-site element", "add_a", default="La", optional=False)
            new_an = st.number_input("A-site ratio", value=2.0, min_value=0.0, step=0.5, key="add_an")
            new_ap = element_select("A′-site element", "add_ap")
            new_apn = st.number_input("A′ ratio", value=0.0, min_value=0.0, step=0.5, key="add_apn")
        with b_col:
            new_b = element_select("B-site element", "add_b", default="Ni", optional=False)
            new_bn = st.number_input("B-site ratio", value=1.0, min_value=0.0, step=0.5, key="add_bn")
            new_bp = element_select("B′-site element", "add_bp")
            new_bpn = st.number_input("B′ ratio", value=0.0, min_value=0.0, step=0.5, key="add_bpn")
        with o_col:
            new_bdp = element_select("B″-site element", "add_bdp")
            new_bdpn = st.number_input("B″ ratio", value=0.0, min_value=0.0, step=0.5, key="add_bdpn")
            new_on = st.number_input("Oxygen ratio", value=4.0, min_value=0.0, step=0.5, key="add_on")

        submitted = st.form_submit_button("Build and check compound", type="primary")

    if submitted:
        new_raw = pd.DataFrame([{
            "ExperimentID": st.session_state.get("editing_entry_id") or uuid.uuid4().hex,
            "LabGroup": new_group.strip(), "ExperimentDate": new_date.isoformat() if new_date else "",
            "Trial": new_trial, "ObservationNotes": new_notes,
            "Instructor": new_instructor.strip(), "Semester": new_semester.strip(), "SourceRow": "manual",
            "Slot": 1, "FormulaRef": "",
            "A": new_a, "AN": new_an, "AP": new_ap, "APN": new_apn,
            "B": new_b, "BN": new_bn, "BP": new_bp, "BPN": new_bpn,
            "BDP": new_bdp, "BDPN": new_bdpn, "O": "O", "ON": new_on,
            "P": new_phase, "Bub": new_bub,
        }])
        new_raw["SourceRow"] = new_raw["ExperimentID"]
        new_clean = clean_and_encode_data(new_raw, atomic)
        new_desc = add_chemical_descriptors(new_clean, atomic, en_table, radii)
        st.session_state.pending_manual_entry = new_desc
        from submissions import submission_table
        _, st.session_state.pending_manual_issues = submission_table(new_desc, atomic)

    if not st.session_state.pending_manual_entry.empty:
        pending = st.session_state.pending_manual_entry
        pending_issues = st.session_state.pending_manual_issues
        formula = pending.iloc[0]["Formula"]

        st.markdown(f"#### Preview: {formula_html(formula)}", unsafe_allow_html=True)
        if pending_issues.empty:
            st.success("This entry passed validation.")
        else:
            st.warning("This entry has issues to review before adding.")
            st.dataframe(pending_issues, width="stretch")
        pending_show = visible(pending)
        st.dataframe(pending_show[ordered_columns(pending_show)], width="stretch")

        add_cols = st.columns([1, 1, 2])
        with add_cols[0]:
            label = "Save changes to observation" if st.session_state.get("editing_entry_id") else "Add to project dataset"
            if st.button(label, type="primary", key="confirm_add_manual_entry", disabled=not pending_issues.empty):
                if st.session_state.get("editing_entry_id"):
                    entries = st.session_state.manual_entries
                    st.session_state.manual_entries = entries[entries["ExperimentID"] != st.session_state.editing_entry_id]
                st.session_state.manual_entries = pd.concat(
                    [st.session_state.manual_entries, pending], ignore_index=True)
                st.session_state.pop("editing_entry_id", None)
                st.session_state.pending_manual_entry = pd.DataFrame()
                st.session_state.pending_manual_issues = pd.DataFrame()
                st.toast("Observation saved to this project.", icon="✅")
                st.rerun()
        with add_cols[1]:
            if st.button("Discard preview", key="discard_manual_preview"):
                st.session_state.pending_manual_entry = pd.DataFrame()
                st.session_state.pending_manual_issues = pd.DataFrame()
                st.rerun()
        with add_cols[2]:
            st.caption("Add the validated record, then download the submission CSV below.")

    from workspace_ui import delete_recorded_observation, start_fresh_observations
    heading, reset = st.columns([4, 1])
    heading.markdown("#### Added to this project")
    reset.button("Start fresh", key="request_start_fresh",
                 on_click=lambda: st.session_state.update(confirm_start_fresh=True))
    if st.session_state.get("confirm_start_fresh"):
        st.warning("Start fresh will remove all observations added through the entry form or notebook "
                   "from this project's dataset and submission CSV, and reset the entry form. "
                   "Imported data and notebook entries will remain. Notebook observations can be "
                   "explicitly added again. Other projects, saved revisions, and downloaded files are kept.")
        confirm, cancel = st.columns(2)
        confirm.button("Clear recorded observations", key="confirm_start_fresh_button",
                       type="primary", on_click=start_fresh_observations)
        cancel.button("Keep my data", key="cancel_start_fresh",
                      on_click=lambda: st.session_state.pop("confirm_start_fresh", None))
    if not st.session_state.manual_entries.empty:
        manual_show = visible(st.session_state.manual_entries)
        for _, row in st.session_state.manual_entries.iterrows():
            summary, action = st.columns([4, 1])
            summary.write(f"{row.get('Formula', 'Observation')} · {row.get('LabGroup', '')} · "
                          f"trial {row.get('Trial', '')} · {row.get('P', '')} · bubbles: {row.get('Bub', '')}")
            experiment_id = row.get("ExperimentID")
            if pd.notna(experiment_id) and experiment_id:
                action.button("Delete observation", key=f"delete_observation_{experiment_id}",
                              on_click=lambda identifier=experiment_id:
                              st.session_state.update(delete_observation_id=identifier))
                if st.session_state.get("delete_observation_id") == experiment_id:
                    st.warning(f"Delete {row.get('Formula', 'this observation')} · trial {row.get('Trial', '')} "
                               "from this project's dataset and submission CSV?")
                    confirm, cancel = st.columns(2)
                    confirm.button("Confirm delete", key=f"confirm_delete_{experiment_id}",
                                   on_click=delete_recorded_observation, args=(experiment_id,))
                    cancel.button("Keep observation", key=f"cancel_delete_{experiment_id}",
                                  on_click=lambda: st.session_state.pop("delete_observation_id", None))
        with st.expander("View all observation details"):
            st.dataframe(manual_show[ordered_columns(manual_show)], width="stretch")
        entries = st.session_state.manual_entries
        if "ExperimentID" in entries:
            choices = [i for i in entries.index if pd.notna(entries.loc[i, "ExperimentID"])]
            if choices:
                selected = st.selectbox("Recorded observation to edit", choices,
                    format_func=lambda i: f"{entries.loc[i, 'Formula']} · trial {entries.loc[i].get('Trial', '')} · {str(entries.loc[i, 'ExperimentID'])[:8]}")
                # Copy the selected observation into the form while retaining its experiment ID.
                def load_for_edit():
                    from datetime import date
                    row = entries.loc[selected]
                    mapping = {"LabGroup":"add_group", "Semester":"add_semester", "Instructor":"add_instructor",
                               "P":"add_phase", "Bub":"add_bub", "Trial":"add_trial", "ObservationNotes":"add_notes",
                               "A":"add_a", "AN":"add_an", "AP":"add_ap", "APN":"add_apn", "B":"add_b",
                               "BN":"add_bn", "BP":"add_bp", "BPN":"add_bpn", "BDP":"add_bdp", "BDPN":"add_bdpn", "ON":"add_on"}
                    for column, key in mapping.items():
                        value = row.get(column)
                        if column in {"AN", "APN", "BN", "BPN", "BDPN", "ON", "Trial"}:
                            value = pd.to_numeric(value, errors="coerce")
                            if pd.isna(value) or not np.isfinite(value):
                                value = 1 if column == "Trial" else 0.0
                            value = max(1, int(value)) if column == "Trial" else max(0.0, float(value))
                        else:
                            value = "" if pd.isna(value) else str(value)
                            if column in {"A", "B", "AP", "BP", "BDP"} and value not in symbols:
                                value = ""
                            if column == "P" and value not in {"pure", "impure", "not made"}:
                                value = ""
                            if column == "Bub" and value not in {"yes", "no", "maybe", "not tested"}:
                                value = ""
                        st.session_state[key] = value
                    try:
                        st.session_state.add_date = date.fromisoformat(str(row.get("ExperimentDate", "")))
                    except ValueError:
                        st.session_state.add_date = None
                    st.session_state.editing_entry_id = row["ExperimentID"]
                    st.session_state.pending_manual_entry = pd.DataFrame()
                st.button("Edit selected observation", on_click=load_for_edit)
                st.caption("Editing preserves its experiment ID. Build/check again and add to replace the earlier record in this project.")
    else:
        st.caption("No recorded observations yet.")
    from submissions import render_submission_download
    render_submission_download(st.session_state.manual_entries, atomic)


# Preview and add another semester's spreadsheet to the current dataset.
def render_new_semester_tab(long_df: pd.DataFrame) -> None:
    """Tab 8 — merge a new semester's raw export into the current dataset."""

    st.caption("Upload a new semester's raw Excel; the app expands it to one row per compound and merges it.")

    new_sem_file = st.file_uploader(
        "New semester file", type=["csv", "xlsx", "xlsm", "xls"],
        help="Raw export where each row is one group and compounds are in columns like 1A, 1AN, 2A, 2AN…",
        key="new_semester_upload",
    )
    if new_sem_file is None:
        st.info("Upload the new semester file to get started.")
        return

    try:
        new_raw = read_table_from_bytes(new_sem_file.getvalue(), new_sem_file.name)
    except Exception as exc:
        st.error(f"Could not read file: {exc}")
        return

    new_long, new_warnings = normalize_to_long_format(new_raw)
    if new_warnings:
        with st.expander("⚠️ Column mapping problems in new file", expanded=True):
            st.warning("Some required columns could not be matched. Check column names (1A, 1AN, 1B, 1BN…). "
                       "See DEVELOPER_NOTES.md.")
            for w in new_warnings:
                st.markdown(f"- {w}")

    if new_long.empty:
        st.error("No compound rows could be extracted. Check the column names.")
        return

    stat_cols = st.columns(3)
    with stat_cols[0]:
        st.metric("Groups in new file", f"{len(new_raw):,}")
    with stat_cols[1]:
        st.metric("Compound rows extracted", f"{len(new_long):,}")
    with stat_cols[2]:
        st.metric("Existing compound rows", f"{len(long_df):,}")

    st.markdown("#### Preview — first 10 new rows")
    preview_cols = [c for c in ["GroupNumber", "Semester", "Slot", "A", "AN", "B", "BN", "O", "ON", "P", "Bub"] if c in new_long.columns]
    st.dataframe(visible(new_long[preview_cols].head(10)), width="stretch")

    existing_semesters = set(long_df["Semester"].dropna().astype(str).unique())
    new_semesters = set(new_long["Semester"].dropna().astype(str).unique())
    overlap = existing_semesters & new_semesters
    if overlap:
        st.warning(f"New file contains semester(s) already present: **{', '.join(sorted(overlap))}**. "
                   "Check for duplicate data.")
    else:
        st.success(f"No semester overlap. New semesters: **{', '.join(sorted(new_semesters)) or 'unknown'}**")

    # Row-level duplicate detection (same group + semester + composition + outcome).
    duplicates = find_merge_duplicates(long_df, new_long)
    exclude_dups = False
    if not duplicates.empty:
        st.warning(f"⚠️ **{len(duplicates)} row(s)** in the new file exactly match rows already "
                   "in the dataset (same experiment ID and unchanged recorded contents).")
        with st.expander("Show duplicate rows"):
            dup_cols = [c for c in ["GroupNumber", "Semester", "Slot", "A", "AN", "B", "BN", "ON", "P", "Bub"]
                        if c in duplicates.columns]
            st.dataframe(visible(duplicates[dup_cols]), width="stretch", hide_index=True)
        exclude_dups = st.checkbox("Exclude these duplicates from the merged download", value=True)
    else:
        st.caption("No unchanged experiment IDs repeat across these files. Legacy rows without IDs are kept; review overlaps manually.")

    new_to_merge = new_long.drop(index=duplicates.index) if (exclude_dups and not duplicates.empty) else new_long
    merged = pd.concat([long_df, new_to_merge], ignore_index=True)
    from submissions import conflicting_experiments
    conflicts = conflicting_experiments(merged)
    if not conflicts.empty:
        st.error("Conflicting versions of the same experiment ID need review before merging.")
        st.dataframe(visible(conflicts), hide_index=True, width="stretch")
        return
    st.markdown(f"#### Merged dataset — {len(merged):,} total rows")
    st.download_button("⬇️ Download merged Combined_Data.xlsx",
                       dataframe_to_excel_bytes(visible(merged), "Combined_Data"),
                       file_name="Combined_Data_merged.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       type="primary")
    st.caption("Open this merged file as a new project to preserve the current investigation.")


# Let authorized Instructors combine legacy Student files, including restricted fields.
def render_combine_tab(long_df: pd.DataFrame, atomic: pd.DataFrame, en_table: pd.DataFrame,
                       radii: pd.DataFrame) -> None:
    """Instructor-only tab — merge many student downloads into one master file."""

    if not instructor_mode_on():
        st.error("Instructor authorization is required.")
        return

    st.caption("🔓 Instructor-only. Each student downloads their own data from this app; "
               "drop all of those files here and get back ONE cleaned, de-duplicated master file.")

    files = st.file_uploader(
        "Student data files (CSV or Excel — add as many as you like)",
        type=["csv", "xlsx", "xlsm", "xls"], accept_multiple_files=True,
        key="combine_uploads",
    )
    if not files:
        st.info("Upload two or more student files to combine them. Raw survey exports and "
                "files downloaded from this app both work.")
        return

    opt_cols = st.columns(2)
    with opt_cols[0]:
        include_current = st.checkbox(
            "Also include the currently loaded dataset", value=True,
            help="Adds the data the app has open right now to the combined file.")
    with opt_cols[1]:
        drop_dupes = st.checkbox(
            "Remove unchanged resubmitted experiments", value=True,
            help="Only identical records with the same experiment ID are deduplicated. "
                 "Legacy records without IDs and independent repeat trials are preserved.")

    frames, report_rows = [], []
    for f in files:
        try:
            raw = read_table_from_bytes(f.getvalue(), f.name)
            f_long, f_warnings = normalize_to_long_format(raw)
            frames.append(f_long)
            report_rows.append({"File": f.name, "Compound rows": len(f_long),
                                "Notes": f"{len(f_warnings)} column warning(s)" if f_warnings else "OK"})
        except Exception as exc:
            report_rows.append({"File": f.name, "Compound rows": 0, "Notes": f"❌ could not read: {exc}"})
    st.dataframe(pd.DataFrame(report_rows), width="stretch", hide_index=True)

    frames = [fr for fr in frames if not fr.empty]
    n_sources = len(frames)
    if include_current and not long_df.empty:
        frames.insert(0, long_df)
        n_sources += 1
    if not frames:
        st.error("No compound rows could be read from these files. Check the column names (1A, 1AN, …).")
        return

    combined, n_dupes = combine_long_tables(frames, drop_exact_duplicates=drop_dupes)
    from submissions import conflicting_experiments
    conflicts = conflicting_experiments(combined)
    if not conflicts.empty:
        st.error("Conflicting versions of the same experiment ID need review before combining.")
        st.dataframe(conflicts, hide_index=True, width="stretch")
        return

    # Run the combined table through the full cleaning pipeline.
    clean = clean_and_encode_data(combined, atomic)
    described = add_chemical_descriptors(clean, atomic, en_table, radii)
    described, _removed_log = remove_invalid_element_rows(described, atomic)
    issues = validate_compound_rows(described, atomic)

    m = st.columns(4)
    m[0].metric("Sources combined", f"{n_sources:,}")
    m[1].metric("Compound rows", f"{len(combined):,}")
    m[2].metric("Duplicates removed", f"{n_dupes:,}")
    m[3].metric("Validation issues", f"{len(issues):,}")

    st.markdown("#### Preview — first 15 combined rows")
    st.dataframe(described[ordered_columns(described)].head(15), width="stretch")

    d1, d2, d3 = st.columns(3)
    with d1:
        st.download_button("⬇️ Combined_Data.xlsx (master)",
                           dataframe_to_excel_bytes(combined, "Combined_Data"),
                           file_name="Combined_Data.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           type="primary",
                           help="Open this master file as a new project after reviewing it.")
    with d2:
        st.download_button("Cleaned combined data (CSV)",
                           dataframe_to_csv_bytes(described[ordered_columns(described)]),
                           file_name="general_chemistry_ii_combined_cleaned.csv", mime="text/csv")
    with d3:
        st.download_button("Cleaned combined data (Excel)",
                           dataframe_to_excel_bytes(described[ordered_columns(described)], "Cleaned_Combined"),
                           file_name="general_chemistry_ii_combined_cleaned.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    st.caption("Open the combined file as a new project to use it in the app. "
               "This download does not publish or update a shared class database automatically.")


# Start Lattice by handing control to the workspace screen manager.
def main() -> None:
    from workspace_ui import run
    run()


if __name__ == "__main__":
    main()
