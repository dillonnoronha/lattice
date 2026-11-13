"""Install pinned runtime requirements only when the local environment needs them."""
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import subprocess
import sys


def main() -> None:
    requirements = Path(__file__).resolve().parent / "requirements.txt"
    missing = []
    for line in requirements.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        name, expected = line.split("==", 1)
        try:
            installed = version(name)
        except PackageNotFoundError:
            installed = None
        if installed != expected:
            missing.append(line)
    if missing:
        print("Updating runtime: " + ", ".join(missing), flush=True)
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(requirements)], check=True)
    else:
        print("Runtime is ready; starting Catalyst.")


if __name__ == "__main__":
    main()
