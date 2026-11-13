# Architecture

| Module | Responsibility |
|---|---|
| app.py | Entry point and reusable preparation/investigation views |
| workspace_ui.py | Navigation, shared scope, Designer, notebook, reports |
| pipeline.py | Parsing, cleaning, validation, descriptors, charts, exports |
| modeling.py | Composition grouping, fitted preprocessing, evaluation, support |
| projects.py | JSON schema, provenance, anonymous snapshots, scoped storage |
| access.py | OIDC identity and verified-email instructor authorization |
| submissions.py | Student result schema, validation, CSV handoff, conservative duplicate detection |
| design.py | Native-theme styling, responsive layout, focus/motion support |

Only the active workspace executes. Inactive pages do not train models, construct reports, or run PCA.

## Data flow

Spreadsheet â†’ normalize long records â†’ apply reviewed corrections â†’ clean labels â†’
calculate descriptors â†’ append project observations â†’ exclude invalid elements â†’
shared scope â†’ validation, charts, modeling, scoped exports.

Snapshots retain normalized source data and corrections separately. Source-row/slot identifiers
link corrections to records. Opening another dataset clears staged entries and candidate previews.

## Models

Bubble: yes=1/no=0. Purity: pure=1/impure=0. Unknown labels and invalid stoichiometry are excluded.
Grouping normalizes ratios and sorts mixed-site elements so repeated/scaled compositions cannot
cross the default holdout. Each sklearn Pipeline learns its own imputation; Logistic Regression
also scales inside its pipeline. Holdout metrics describe the held-out estimator. Predictions
use a separate refit on all eligible scoped records. Semester CV uses training semesters only.
Folds without both outcomes are omitted with an explicit count.

## Persistence and access

JSON only; no imported model pickle. Snapshots use SHA-256 filenames and atomic latest pointers.
IDs/revisions are validated before path resolution. Storage namespaces hash authenticated
issuer/subject, or use a shared namespace only in explicit local mode on a trusted workstation.

Bundles preserve anonymous normalized data, corrections, manual observations, hypotheses,
original prediction context, filters/settings, and history. Imported bundles receive new IDs.
Student exports use allowlisted columns; contact diagnostics are removed. Instructor authorization
is checked against verified OIDC identity on each render, never a user-controlled role flag.

The file store is not a collaboration database. Concurrent browser edits can create independent
revisions; the last save becomes the default, while older revisions remain recoverable.
Configure persistent storage, backups, and retention for production.

Version 2.1 adds optional ExperimentID, LabGroup, ExperimentDate, Trial, and ObservationNotes to
schema-1 records without removing older fields. Existing bundles still open. Contact/group roster
fields remain excluded; LabGroup is an explicitly entered non-identifying group code. Submission
CSV exports contain only recorded manual entries, not imported datasets or candidate predictions.
Only equal IDs with unchanged content are deduplicated. Conflicting versions stop submission intake;
legacy rows without IDs are retained. Student submissions require a human-controlled LMS/file handoff.
