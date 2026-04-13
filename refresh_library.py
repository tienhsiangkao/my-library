import subprocess
import sys

scripts = [
    "pretext_renderer.py",
    "build_library.py",
]

for script in scripts:
    print(f"Running {script}...")
    result = subprocess.run([sys.executable, script])
    if result.returncode != 0:
        raise SystemExit(f"Failed: {script}")

print("Library refreshed successfully.")