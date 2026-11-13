# Instructor handoff

**Student collection is now supported through files:** students enter actual results in a blank
sheet and download a validated submission CSV. Use **Prepare data → Combine submission CSVs**
to upload the batch, review changed versions of experiment IDs, and create a combined class project.
This allowlisted submission intake does not require contact-data access. Genuine repeat trials retain
separate IDs; old survey rows without IDs are kept for manual overlap review.
See [STUDENT_RESULTS_WORKFLOW.md](STUDENT_RESULTS_WORKFLOW.md) for rollout and student instructions.

The research workflow now has Overview, Prepare data, Investigate, Experiment Designer,
Lab notebook, and Share findings. Read README.md for local setup.

Unknown outcomes are separated from failures. Preprocessing is fitted independently within
each evaluation split. Unseen-composition evaluation is the default, with explicit semester/row
alternatives. Students can save hypotheses, original model context, observations, and history.

The shared passcode has been removed. Configure OIDC and the verified-email instructor allowlist
using DEPLOYMENT.md and .streamlit/secrets.toml.example. Without this, the app stays in student mode.
Local storage does not grant instructor access.

Full identifiable exports and combining student files require instructor authorization.
Saved bundles omit contacts; reopen the original spreadsheet to recover those fields.

Ask students to record a rationale before an experiment and an interpretation afterward.
Use sample sizes and uncertainty alongside percentages. Reports include scope/reference fingerprints.

Local autosave is limited to the trusted workstation. Hosted use needs persistent storage,
backups, and real-account sign-in testing. The store is not a concurrent campus records database.
