"""Portable project snapshots, scoped storage, and research provenance (no pickle)."""
from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

SCHEMA_VERSION = 1
APP_VERSION = "2.2.0"
ROOT = Path(__file__).resolve().parent
MAX_BUNDLE_BYTES = 25 * 1024 * 1024
# Explicit allowlist: imported spreadsheets may contain unexpected contact fields.
DATA_COLUMNS = ["SourceRow", "Slot", "ExperimentID", "LabGroup", "ExperimentDate", "Trial", "ObservationNotes", "Semester", "Instructor", "A", "AN", "AP", "APN", "B", "BN",
                "BP", "BPN", "BDP", "BDPN", "O", "ON", "P", "Bub"]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def encode_frame(df: pd.DataFrame) -> dict:
    return json.loads(df.to_json(orient="split", date_format="iso"))


def decode_frame(value: dict) -> pd.DataFrame:
    if not isinstance(value, dict) or not isinstance(value.get("columns"), list) or not isinstance(value.get("data"), list):
        raise ValueError("Invalid project table.")
    if not all(isinstance(c, str) for c in value["columns"]):
        raise ValueError("Project column names must be text.")
    if len(set(value["columns"])) != len(value["columns"]) or len(value["data"]) > 100000:
        raise ValueError("Project table has duplicate columns or too many rows.")
    if any(not isinstance(row, list) or len(row) != len(value["columns"]) or
           any(isinstance(cell, (dict, list)) for cell in row) for row in value["data"]):
        raise ValueError("Project rows must contain one scalar value per column.")
    return pd.DataFrame(value["data"], columns=value["columns"])


def anonymous_data(df: pd.DataFrame) -> pd.DataFrame:
    return df[[c for c in DATA_COLUMNS if c in df]].copy()


def fingerprint(df: pd.DataFrame) -> str:
    return hashlib.sha256(df.to_json(orient="split", date_format="iso").encode()).hexdigest()


def reference_versions() -> dict:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT / "data").glob("*.csv"))
            if p.name in {"AtomicMass.csv", "PaulingEN.csv", "ShannonRadii.csv"}}


def analysis_manifest(df: pd.DataFrame, filters: dict, settings: dict) -> dict:
    return {"app_version": APP_VERSION, "dataset_sha256": fingerprint(anonymous_data(df)),
            "rows": len(df), "filters": filters, "settings": settings, "references": reference_versions(),
            "outcomes": "Bubble: confirmed yes/no; purity: confirmed pure/impure; unknowns excluded.",
            "score_interpretation": "Uncalibrated exploratory model scores, not measured probabilities."}


def new_project(name: str = "Untitled investigation") -> dict:
    return {"schema_version": SCHEMA_VERSION, "id": uuid.uuid4().hex, "name": name,
            "created": now(), "source": "", "dataset": encode_frame(pd.DataFrame()),
            "manual_entries": encode_frame(pd.DataFrame()), "corrections": {},
            "candidates": [], "history": [], "filters": {}, "settings": {}}


def validate_project(project: dict) -> dict:
    if not isinstance(project, dict) or project.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unsupported project format/version.")
    if not re.fullmatch(r"[a-f0-9]{32}", str(project.get("id", ""))):
        raise ValueError("Invalid project identifier.")
    for field in ["dataset", "manual_entries"]:
        project[field] = encode_frame(anonymous_data(decode_frame(project[field])))
    if not isinstance(project.get("name"), str) or len(project["name"]) > 200:
        raise ValueError("Project name must be 200 characters or fewer.")
    for field in ["corrections", "filters", "settings"]:
        if not isinstance(project.get(field), dict):
            raise ValueError(f"Invalid project {field}.")
    if not all(isinstance(k, str) and isinstance(v, str) for k, v in project["corrections"].items()):
        raise ValueError("Element corrections must map source keys to element symbols.")
    for key, value in project["filters"].items():
        if key not in {"scope_semesters", "scope_instructors", "scope_groups"} or not isinstance(value, list) or not all(isinstance(x, str) for x in value):
            raise ValueError("Invalid saved analysis filters.")
    choices = {"model_mode": ["Plan a future experiment", "Analyze known phase"],
               "evaluation_mode": ["Unseen compositions", "Held-out semester", "Stratified rows"]}
    for key, values in choices.items():
        if key in project["settings"] and project["settings"][key] not in values:
            raise ValueError(f"Invalid saved {key}.")
    if "include_mass" in project["settings"] and not isinstance(project["settings"]["include_mass"], bool):
        raise ValueError("Invalid mass-descriptor setting.")
    if not isinstance(project["settings"].get("holdout_semester", ""), str):
        raise ValueError("Invalid held-out semester.")
    for field in ["candidates", "history"]:
        if not isinstance(project.get(field), list) or not all(isinstance(x, dict) for x in project[field]):
            raise ValueError(f"Invalid project {field}.")
    for candidate in project["candidates"]:
        if not all(k in candidate for k in ["id", "formula", "row", "rationale", "created"]):
            raise ValueError("Incomplete saved candidate.")
        candidate["row"] = encode_frame(anonymous_data(decode_frame(candidate["row"])))
        if len(candidate["row"]["data"]) != 1:
            raise ValueError("A candidate must contain exactly one compound.")
        if not re.fullmatch(r"[a-f0-9]{32}", str(candidate["id"])):
            raise ValueError("Invalid candidate identifier.")
        if not all(isinstance(candidate[k], str) for k in ["formula", "rationale", "created"]):
            raise ValueError("Invalid candidate description.")
        if not isinstance(candidate.get("prediction", {}), dict) or not isinstance(candidate.get("manifest", {}), dict):
            raise ValueError("Invalid candidate provenance.")
        history = candidate.get("observation_history", [])
        if not isinstance(history, list):
            raise ValueError("Invalid observation history.")
        for outcome in ["bubble", "purity"]:
            prediction = candidate.get("prediction", {}).get(outcome, {})
            if not isinstance(prediction, dict):
                raise ValueError("Invalid candidate prediction.")
        observations = [candidate.get("observation", {})] + history
        for observation in observations:
            if not isinstance(observation, dict) or observation.get("bubble", "") not in ["", "yes", "no", "maybe", "not tested"] or observation.get("phase", "") not in ["", "pure", "impure", "not made"]:
                raise ValueError("Invalid saved experiment outcome.")
            if not all(isinstance(observation.get(k, ""), str) for k in
                       ["notes", "semester", "group", "instructor", "date", "recorded"]):
                raise ValueError("Invalid observation metadata.")
            trial = observation.get("trial", 1)
            if not isinstance(trial, int) or isinstance(trial, bool) or trial < 1:
                raise ValueError("Invalid observation trial number.")
    ids = [c["id"] for c in project["candidates"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Candidate identifiers must be unique.")
    return project


def bundle_bytes(project: dict) -> bytes:
    # Validate a copy so exports cannot mutate the live workspace.
    safe = validate_project(json.loads(json.dumps(project, allow_nan=False)))
    data = json.dumps(safe, indent=2, ensure_ascii=False, allow_nan=False).encode("utf-8")
    if len(data) > MAX_BUNDLE_BYTES:
        raise ValueError("Project exceeds the 25 MB bundle limit. Split it into smaller projects.")
    return data


def read_bundle(data: bytes) -> dict:
    if len(data) > MAX_BUNDLE_BYTES:
        raise ValueError("Project bundles must be smaller than 25 MB.")
    try:
        def reject_constant(value):
            raise ValueError("Non-finite JSON values are not supported.")
        return validate_project(json.loads(data, parse_constant=reject_constant))
    except (KeyError, TypeError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("This is not a valid Catalyst project bundle.") from exc


class ProjectStore:
    """Every owner has an isolated namespace. IDs are never used as arbitrary paths."""
    def __init__(self, owner: str, root: Path | None = None):
        if not owner:
            raise ValueError("An authenticated identity or explicit local mode is required.")
        self.root = (root or ROOT / ".catalyst") / hashlib.sha256(owner.encode()).hexdigest()
        if os.name == "nt":
            # Hash-based revision paths can exceed Windows' legacy 260-character limit.
            absolute = str(self.root.resolve())
            if not absolute.startswith("\\\\?\\"):
                absolute = "\\\\?\\UNC\\" + absolute[2:] if absolute.startswith("\\\\") else "\\\\?\\" + absolute
            self.root = Path(absolute)

    def _directory(self, project_id: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{32}", str(project_id)):
            raise ValueError("Invalid project identifier.")
        return self.root / project_id

    def save(self, project: dict) -> str:
        data = bundle_bytes(project)
        revision = hashlib.sha256(data).hexdigest()
        directory = self._directory(project["id"])
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{revision}.json"
        if not target.exists():
            self._write_atomic(target, data)
        latest = directory / "latest"
        if not latest.exists() or latest.read_text(encoding="ascii") != revision:
            self._write_atomic(latest, revision.encode("ascii"))
        summary = dict(id=project["id"], name=project["name"], revision=revision)
        summary_bytes = json.dumps(summary, ensure_ascii=False).encode("utf-8")
        catalog = directory / "summary"
        if not catalog.exists() or catalog.read_bytes() != summary_bytes:
            self._write_atomic(catalog, summary_bytes)
        return revision

    @staticmethod
    def _write_atomic(target: Path, data: bytes) -> None:
        temporary = target.parent / f"{uuid.uuid4().hex}.tmp"
        try:
            temporary.write_bytes(data)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)

    def load(self, project_id: str, revision: str | None = None) -> dict:
        directory = self._directory(project_id)
        revision = revision or (directory / "latest").read_text(encoding="ascii")
        if not re.fullmatch(r"[a-f0-9]{64}", revision):
            raise ValueError("Invalid revision.")
        return read_bundle((directory / f"{revision}.json").read_bytes())

    def list_projects(self) -> list[dict]:
        result = []
        for pointer in self.root.glob("*/latest"):
            try:
                revision = pointer.read_text(encoding="ascii")
                try:
                    p = json.loads((pointer.parent / "summary").read_bytes())
                    if not isinstance(p, dict) or p.get("revision") != revision or p.get("id") != pointer.parent.name or not isinstance(p.get("name"), str):
                        raise ValueError("Stale project summary")
                except (ValueError, OSError):
                    p = self.load(pointer.parent.name, revision)
                    summary = dict(id=p["id"], name=p["name"], revision=revision)
                    self._write_atomic(pointer.parent / "summary", json.dumps(summary).encode())
                result.append({"id": p["id"], "name": p["name"]})
            except (ValueError, OSError):
                continue
        return result

    def revisions(self, project_id: str) -> list[str]:
        return [p.stem for p in sorted(self._directory(project_id).glob("*.json"),
                                      key=lambda p: p.stat().st_mtime, reverse=True)]


def append_event(project: dict, action: str, detail: str) -> None:
    project["history"].append({"time": now(), "action": action, "detail": detail})


def add_candidate(project: dict, row: pd.DataFrame, rationale: str, prediction: dict,
                  manifest: dict) -> None:
    project["candidates"].append({"id": uuid.uuid4().hex, "created": now(),
        "formula": str(row.iloc[0]["Formula"]), "row": encode_frame(anonymous_data(row)),
        "rationale": rationale, "prediction": prediction, "manifest": manifest,
        "status": "Planned", "observation": {}})
    append_event(project, "Candidate saved", str(row.iloc[0]["Formula"]))
