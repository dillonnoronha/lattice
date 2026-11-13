# Catalyst Insight Studio

A chemistry research workspace for preparing class observations, investigating patterns,
designing experiments, and comparing hypotheses with measured outcomes.

See [the 2.2 release review](RELEASE_REVIEW.md) for reliability improvements, validation results,
and deployment boundaries, and [the student results workflow](STUDENT_RESULTS_WORKFLOW.md)
for entry, CSV submission, and instructor collection instructions.

## Run locally

On Windows, double-click `run_app_windows.bat`. It creates an isolated Python environment,
binds the app to 127.0.0.1, and enables local autosave. Python 3.13 is the tested runtime.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:CATALYST_LOCAL_MODE = '1'
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1
```

## Research workflow

For class collection, students now choose **Start a blank results sheet**, enter and validate each
experiment, and download **student submission CSV** for the LMS. Instructors use **Prepare data →
Combine submission CSVs** to review the batch and open/download the combined class dataset.
See [STUDENT_RESULTS_WORKFLOW.md](STUDENT_RESULTS_WORKFLOW.md) for the handout and partner reply.
This is a file-based handoff, not an automatic shared-database submission service.

1. **Overview**: confirmed outcome rates, denominators, intervals, and data quality.
2. **Prepare data**: correct elements, validate entries, add observations, merge semesters.
3. **Investigate**: element outcomes, relationships, PCA, and searchable compound details.
4. **Experiment Designer**: composition-only or known-phase analysis, model evaluation,
   similarity evidence, missing-property warnings, oxygen sweeps, and saved hypotheses.
5. **Lab notebook**: compare candidates, record results, undo observation edits, and explicitly
   add observed experiments to the dataset.
6. **Share findings**: anonymous analysis exports, printable reports, provenance, portable
   project bundles, and restoration of saved revisions.

Use the sample investigation without uploading a file. Its four compounds intentionally do
not qualify for modeling. Models need at least ten confirmed labels, both outcomes, and
sufficient independent compositions.

Semester/instructor scope applies across research views and analysis exports. Dataset
maintenance and the complete notebook are labeled as whole-project views.

## Scientific interpretation

- Bubble rates use confirmed yes/no; maybe, missing, and unknown are not failures.
- Purity rates use pure/impure; not-made and unknown outcomes are excluded.
- Properties stay missing when necessary inputs are unknown.
- Models fit imputation independently inside each split/fold. Predictions reuse fitted values.
- Default evaluation holds out whole compositions; row and explicit semester holdouts are available.
- Cross-validation spread is standard deviation, not a confidence interval.
- Scores are uncalibrated exploratory outputs. Feature importance is not causation.
- Ionic radii use reference oxidation/coordination assumptions. Tolerance factor alone does not
  establish a crystal structure or chemical feasibility.

## Saving and access

Local mode saves immutable snapshots under ignored `.catalyst/`. On a hosted server, local mode
must be off; authenticated users receive separate storage namespaces. Anonymous users can
download/reopen portable JSON bundles. Hosted storage needs a persistent volume and backups.

Snapshots omit student contact/group columns. Free-text hypotheses and notes remain: review them
before sharing. Original contact fields remain only in the uploaded session and require instructor
authorization to view/export. Anonymous bundles cannot restore those fields.

Instructor access requires OIDC and a verified email on the allowlist. There is no shared password.
See [DEPLOYMENT.md](DEPLOYMENT.md).

## Verification

`requirements.txt` pins runtime dependencies. `requirements.lock` records the complete tested
Python 3.13 environment, including pytest and optional browser QA tooling.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pytest -q
# With Chrome installed and the preview running on port 8501:
.\.venv\Scripts\python.exe tests/browser_smoke.py
```

See [ARCHITECTURE.md](ARCHITECTURE.md), [STUDENT_GUIDE.md](STUDENT_GUIDE.md), and
[INSTRUCTOR_HANDOFF.md](INSTRUCTOR_HANDOFF.md).
