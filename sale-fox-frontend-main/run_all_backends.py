#!/usr/bin/env python3
"""Start the shared Flask scraper API used by Sale-Fox."""

import os
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = Path(
    os.environ.get(
        "UNIFIED_BACKEND_DIR",
        str(BASE_DIR.parent / "unified dashboard" / "backend"),
    )
).expanduser().resolve()


def main():
    app_file = BACKEND_DIR / "app.py"
    if not app_file.is_file():
        raise FileNotFoundError(f"Unified backend not found: {app_file}")

    venv_python = BACKEND_DIR / ".venv" / (
        "Scripts/python.exe" if os.name == "nt" else "bin/python"
    )
    python_executable = str(venv_python) if venv_python.is_file() else sys.executable
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    process = subprocess.Popen(
        [python_executable, str(app_file)],
        cwd=BACKEND_DIR,
        env=env,
    )
    print(f"Unified scraper API started (PID {process.pid}) on http://127.0.0.1:5050")
    print("Press Ctrl+C to stop the API.")

    try:
        return_code = process.wait()
    except KeyboardInterrupt:
        process.terminate()
        return_code = process.wait()

    if return_code:
        raise SystemExit(return_code)


if __name__ == "__main__":
    main()
