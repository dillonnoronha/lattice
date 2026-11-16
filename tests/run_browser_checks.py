"""Run browser acceptance checks on an isolated server without creating saved projects."""
from pathlib import Path
import os
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


# Run browser checks on a separate local server without saving real projects.
def main():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    env = dict(os.environ, LATTICE_LOCAL_MODE="0", LATTICE_TEST_URL=f"http://127.0.0.1:{port}")
    artifacts = ROOT / "qa-artifacts"
    artifacts.mkdir(exist_ok=True)
    with (artifacts / "browser-server.log").open("w", encoding="utf-8") as log:
        server = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "app.py",
            "--server.address", "127.0.0.1", "--server.port", str(port), "--server.headless", "true"],
            cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        try:
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                if server.poll() is not None:
                    raise RuntimeError("Test server exited; see qa-artifacts/browser-server.log")
                try:
                    with urlopen(env["LATTICE_TEST_URL"] + "/_stcore/health", timeout=1) as response:
                        if response.status == 200:
                            break
                except (URLError, TimeoutError):
                    time.sleep(.25)
            else:
                raise TimeoutError("Test server did not become healthy")
            for name in ["browser_smoke.py", "browser_submissions.py"]:
                subprocess.run([sys.executable, str(ROOT / "tests" / name)],
                               cwd=ROOT, env=env, check=True, timeout=180)
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()


if __name__ == "__main__":
    main()
