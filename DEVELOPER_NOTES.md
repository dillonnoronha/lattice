# Developer notes

- Workflow: workspace_ui.py; reusable data views: app.py.
- Survey aliases: pipeline.py::infer_slot_column / normalize_to_long_format.
  The import interface also maps custom one-compound-per-row sheets.
- Chemistry: pipeline.py::add_chemical_descriptors; preserve unknown properties.
- Outcomes: pipeline.py::clean_and_encode_data; unknowns must not become failures.
- Features: pipeline.py::feature_columns; fitting: modeling.py::evaluate.
- Prediction: modeling.py::predict_candidate; always use the saved fitted transformation.
  The legacy build_feature_matrix helper is not the production prediction path.
- Access: access.py. Public fields: pipeline.py::public_view and projects.py::DATA_COLUMNS.
- Persistence/schema: projects.py. Presentation: design.py.

Install requirements.lock in Python 3.13 and run python -m pytest -q.
The workflow suite covers denominators, missing properties, composition separation,
training-only imputation, privacy, identity checks, project revisions, owner isolation,
dataset switching, and the hypothesis-to-observation journey.

Run `python tests/run_browser_checks.py` with Chrome installed for browser QA. It starts and stops
an isolated server with local persistence disabled, exercises desktop/mobile/dark layouts and
student CSV intake, and writes screenshots/logs to `qa-artifacts/`. `PLAYWRIGHT_CHANNEL` selects
another installed browser channel. CI installs Chromium and runs these checks after pytest.
Restart the preview after editing imported modules if it retains earlier module objects.

Autosave fingerprints the current project before validating/writing a changed snapshot. The
saved-project picker reads small revision-checked summaries; old or stale summaries rebuild
from the snapshot. Writes are atomic, unchanged revisions do not rewrite pointers, and Windows
storage uses extended paths. Storage remains a single-writer workflow; it is not a collaborative database.

Pipeline caches have bounded entry counts (32 transformations, 8 model evaluations per function).
Chart colors use execution-local context so users with different themes cannot overwrite each other.
Similarity requires measured shared descriptors; PCA excludes wholly missing rows and constant
features. Unknown stoichiometry propagates into descriptor gaps instead of assuming a ratio of one.

Excel exports explicitly write formula-looking input as literal text. CSV remains the lossless
interchange format for the app. Use the Excel export for spreadsheet inspection.

The Windows launcher checks installed package versions and installs only when requirements differ.
Use `python -m pip check` to diagnose a manually modified environment.

Upgrade dependencies intentionally; regenerate the lock from a clean environment and run
automated/visual checks. Project schema versions are independent of app versions. Add explicit
migrations when stored semantics change. Never deserialize model pickle files from uploads.
