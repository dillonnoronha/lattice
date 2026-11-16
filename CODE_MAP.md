# Lattice code map

This guide shows where to look when explaining or maintaining Lattice. Each Python function has a short plain-English comment above it. In your editor, use **Ctrl+F** to search for a function name listed here.

## Start the app

- [`run_app_windows.bat`](run_app_windows.bat) prepares the desktop environment and starts Streamlit.
- [`app.py`](app.py) is the app's entry point. Its `main()` hands control to the workspace manager. It also contains reusable views for data checks, investigation charts, and the Student observation form.
- [`workspace_ui.py`](workspace_ui.py) runs the app after startup. Its `run()` loads the current project, prepares data and reference tables, applies analysis scope, and displays the selected workspace.

**Important:** Start the app using `run_app_windows.bat` or `python -m streamlit run app.py`. Do not run `workspace_ui.py` directly. Streamlit needs to start the app before its UI and caching features can run.

## Sign-in, access, and appearance

- [`access.py`](access.py) reads the signed-in identity, starts or ends sign-in, checks the verified-email Instructor allowlist, and chooses a project-storage owner. It does not contain the institution's credentials.
- [`design.py`](design.py) applies the Lattice theme, page spacing, responsive layout, and accessibility styling.
- [`workspace_ui.py`](workspace_ui.py) calls the access and design functions while building the shared screen.

Instructor sign-in requires OIDC and access settings configured by the host. Enabling local project storage does not itself grant Instructor privileges. See [`DEPLOYMENT.md`](DEPLOYMENT.md) for hosting configuration.

## Student entry and Instructor collection

- [`app.py`](app.py) → `render_add_compound_tab()` builds the form where a Student records one experiment, checks its preview, edits an existing result, deletes an added observation, or starts fresh.
- [`submissions.py`](submissions.py) defines the Student CSV fields. `submission_table()` checks a result before download; `render_submission_download()` offers the file once all entries pass.
- [`submissions.py`](submissions.py) → `render_submission_intake()` reads the Instructor's uploaded CSVs, combines rows, checks for conflicts, summarizes coverage, and produces the combined class CSV or project.
- [`submissions.py`](submissions.py) → `render_intake_review()` shows individual uploaded rows and supports deleting or restoring a row during batch review.
- [`workspace_ui.py`](workspace_ui.py) contains the project-level observation removal and **Start fresh** actions.

Student and Instructor CSV handoff is file-based: students submit their CSV through the course's collection process; the Instructor uploads the collected files. Lattice does not automatically receive submissions from an LMS. See [`STUDENT_RESULTS_WORKFLOW.md`](STUDENT_RESULTS_WORKFLOW.md) for the operational steps.

## Data import, quality checks, and chemistry

[`pipeline.py`](pipeline.py) contains the shared data-processing functions:

- `read_table_from_bytes()` reads uploaded CSV and Excel files.
- `normalize_to_long_format()` arranges older or wider spreadsheets into one row per experiment.
- `clean_and_encode_data()` standardizes formula fields and measured outcome labels.
- `validate_compound_rows()` finds missing fields, invalid elements or ratios, and uncertain labels.
- `propose_element_fixes()` and `apply_element_fixes()` support reviewed element-symbol corrections.
- `add_chemical_descriptors()` calculates properties from composition using reference tables in [`data/`](data/), such as atomic masses, electronegativity, and ionic radii.
- `summarize_by_element()`, `numeric_correlation_table()`, `plot_heatmap()`, and `compute_pca()` prepare analysis summaries and charts.
- `dataframe_to_csv_bytes()` and `dataframe_to_excel_bytes()` prepare spreadsheet downloads.

Calculated properties come from the formula and reference tables. They are not Student measurements. Missing outcomes and missing reference values are kept distinct from measured failures or zeroes.

## Experiment models

- [`modeling.py`](modeling.py) builds and evaluates the scikit-learn models. `new_estimator()` prepares a model; `evaluate()` trains and measures it using the selected data. `composition_groups()` keeps equivalent compositions together during the default evaluation split.
- [`modeling.py`](modeling.py) → `predict_candidate()` scores a proposed composition and reports limitations in the supporting data.
- [`pipeline.py`](pipeline.py) → `train_ml_model()` and `train_purity_model()` prepare cached results for bubbling and phase-purity evaluation.
- [`workspace_ui.py`](workspace_ui.py) → `model_settings()`, `designer()`, and `notebook()` show the model controls, experiment planning view, and saved hypotheses or observations.

Scores help compare and plan experiments. They are exploratory estimates, not guarantees of lab outcomes. The app declines to train when it lacks enough suitable data.

## Projects, saving, and reports

- [`projects.py`](projects.py) creates and checks project records, converts data tables to and from JSON, and builds portable project downloads.
- [`projects.py`](projects.py) → `ProjectStore` saves, lists, and reopens versioned project snapshots. Snapshots are saved as files in `.lattice/` for local storage or in a configured hosted storage location. Older revisions can be recovered.
- [`workspace_ui.py`](workspace_ui.py) → `activate()` opens a project; `sync_project()` copies current changes into it and saves when the contents change; `share()` builds downloads and reports.
- [`pipeline.py`](pipeline.py) → `build_html_report()` creates the printable analysis report.

Project snapshots are JSON files. The current app's project store is not a central shared SQL database. Hosted persistence depends on the hosting environment and its storage configuration.

## Tests and setup

- [`tests/`](tests/) contains automated checks for Student entry and exports, Instructor file intake, modeling, saved projects, and browser behavior.
- `tests/run_browser_checks.py` starts a separate local test server and runs the browser checks.
- [`requirements.txt`](requirements.txt) lists app packages. [`requirements.lock`](requirements.lock) also includes the test and browser-testing tools, including Playwright and pytest.
- [`ensure_runtime.py`](ensure_runtime.py) checks app runtime package versions for the desktop launcher.

To launch the app, follow [`README.md`](README.md). To run tests, follow its Verification section.
