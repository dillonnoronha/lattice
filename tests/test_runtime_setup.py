"""Desktop setup handles pinned versions and version ranges without needless installs."""
import pytest

import ensure_runtime


@pytest.mark.parametrize("installed, needs_install", [
    ({"streamlit": "1.64.0", "httpx": "0.28.1"}, False),
    ({"streamlit": "1.64.0", "httpx": "0.29.0"}, False),
    ({"streamlit": "1.64.0", "httpx": "0.27.2"}, True),
    ({"streamlit": "1.63.0", "httpx": "0.28.1"}, True),
    ({"streamlit": "1.64.0"}, True),
])
def test_runtime_installs_only_for_unsatisfied_requirements(tmp_path, monkeypatch, installed, needs_install):
    requirements = tmp_path / "requirements.txt"
    requirements.write_text(
        "# Runtime\n\nstreamlit==1.64.0\nhttpx>=0.28 # Accept compatible newer versions\n"
        'not-needed>=1; python_version < "3.0"\n', encoding="utf-8")
    monkeypatch.setattr(ensure_runtime, "__file__", str(tmp_path / "ensure_runtime.py"))

    def installed_version(name):
        if name not in installed:
            raise ensure_runtime.PackageNotFoundError(name)
        return installed[name]

    monkeypatch.setattr(ensure_runtime, "version", installed_version)
    calls = []
    monkeypatch.setattr(ensure_runtime.subprocess, "run", lambda command, **kwargs: calls.append((command, kwargs)))
    ensure_runtime.main()
    expected = [([ensure_runtime.sys.executable, "-m", "pip", "install", "-r", str(requirements)], {"check": True})]
    assert calls == (expected if needs_install else [])
