"""Install runtime requirements only when the local environment needs them."""
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import subprocess
import sys

try:
    from packaging.requirements import Requirement
except ModuleNotFoundError:
    # A fresh venv has pip before it has the app's packaging dependency.
    from pip._vendor.packaging.requirements import Requirement


def main() -> None:
    requirements = Path(__file__).resolve().parent / "requirements.txt"
    missing = []
    for line in requirements.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        requirement = Requirement(line)
        if requirement.marker and not requirement.marker.evaluate():
            continue
        try:
            installed = version(requirement.name)
        except PackageNotFoundError:
            installed = None
        if installed is None or not requirement.specifier.contains(installed):
            missing.append(line)
    if missing:
        print("Updating runtime: " + ", ".join(missing), flush=True)
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(requirements)], check=True)
    else:
        print("Runtime is ready; starting Lattice.")


if __name__ == "__main__":
    main()
