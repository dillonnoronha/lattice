# Deployment

## Local workstation

Use run_app_windows.bat with Python 3.13. It installs pinned dependencies into .venv, sets
LATTICE_LOCAL_MODE=1, and binds to 127.0.0.1. Local projects are shared by people using that
OS account. Local mode enables storage, not instructor authorization. Do not expose it to a network.

## Hosted deployment

1. Install requirements.txt with Python 3.13.
2. Leave LATTICE_LOCAL_MODE and the legacy CATALYST_LOCAL_MODE unset; do not bundle real student spreadsheets.
3. Configure institutional OIDC in .streamlit/secrets.toml or your host's secret store.
4. Put .lattice on persistent, access-restricted storage with backups.
   Existing .catalyst owner stores remain supported; preserve those volumes during upgrades.
5. Run tests and verify actual instructor/student sign-in before distribution.

Copy .streamlit/secrets.toml.example to the ignored secrets.toml and supply actual provider
values. Register the exact callback URL with the identity provider.

The provider must return sub, email, and boolean email_verified=true for instructor access.
The server-side access.instructor_emails list grants instructor roles; missing/unverified claims
fail closed. OIDC credentials and real-account verification are environment-specific and are
not supplied by this repository.

## Privacy

Student exports omit contact/group fields and arbitrary spreadsheet columns. Full CSV/Excel
exports and combining student files require instructor authorization. Snapshots omit student
contact fields; instructor/semester labels remain as cohort metadata. Notes are retained as
written. Identifiable uploads can remain in server memory, so use trusted hosting.

Keep .lattice, secrets.toml, original class datasets, logs, and QA screenshots out of Git.
Anonymous hosted sessions should download portable bundles before closing. Ephemeral server
storage can be lost on restart.

## Operations

CI runs unit and Streamlit workflow tests on Python 3.13. tests/browser_smoke.py checks a running
preview in Chrome and saves screenshots under ignored qa-artifacts. Native Streamlit appearance
settings control theme; custom styles inherit that theme.

The file store provides separate owner namespaces and historical snapshots, not collaborative
record locking, roster provisioning, or managed backups. Supply those operational services
before using the app as a campus-wide system of record.
