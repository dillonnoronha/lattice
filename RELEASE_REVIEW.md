# Catalyst 2.2 release review

Reviewed November 13, 2026. Changes were implemented in the local workspace.

## Changes

- Unchanged navigation no longer validates and writes the whole project repeatedly. Project
  selection reads small revision-checked summaries instead of loading every dataset. Existing
  snapshots remain compatible. Atomic-write failures clean up temporary files; long Windows
  paths work without changing system policy.
- Notebook results now include submission metadata and receive the same validation as direct
  student entries. Reopened portable backups rebuild display fields and remain editable.
- Editing is explicitly labeled and can be cancelled without replacing a saved observation.
  Semester merges include manual entries, and every merge path blocks conflicting experiment IDs.
- Intake identifies the file, row, and field for invalid submissions. Coverage tables and a lab-group
  filter help instructors inspect received results. Distinct trials remain separate.
- Missing measurements cannot become zero-distance matches. PCA handles nonfinite input and
  constant datasets. Missing stoichiometry remains unknown in calculated descriptors.
- Model preferences survive navigation. Chart themes are isolated between sessions, and caches
  have entry limits. Excel formula-looking text is written as literal text.
- Malformed project tables are rejected before activation. Exports enforce the same 25 MB project
  bundle limit as imports. Numeric-looking section/group codes and literal NA notes survive CSV import.
- The Windows launcher avoids reinstalling an already correct runtime. Browser checks run on an
  isolated server, and CI now includes the browser workflow and QA artifacts.

## Performance check

A local synthetic benchmark with eight projects of 1,000 rows each measured a median saved-project
listing time of 43.84 ms when loading all snapshots versus 4.66 ms using summaries (five runs each,
approximately 9.4× faster). This measures project listing, not overall app speed or hosting capacity.

## Verification and deployment boundary

Local verification completed: **104 tests passed in 19.10 seconds**; both live Chrome browser
checks passed; `pip check` found no broken requirements; `git diff --check` found no whitespace
errors. Screenshots were inspected for desktop, mobile, dark mode, and submission intake. The
updated CI workflow has been added locally and has not been run on GitHub.

The regression suite covers scientific calculations, model evaluation, data privacy, identity gates,
storage/recovery, entry/edit/backup behavior, and submission integrity. Live Chrome checks cover
desktop, mobile, native dark mode, and entry → CSV → multi-file merge → class analysis.

Production hosting, real institutional OIDC sign-in, and multi-user load testing remain deployment
checks. Local snapshots and CSV intake are implemented; there is no shared submission inbox,
automatic LMS transfer, or remote database synchronization. Keep portable backups, and use a single
instructor writer for each master project. The changes have not been published or pushed.
