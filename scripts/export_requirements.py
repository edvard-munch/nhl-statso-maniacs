"""Generate or check the pip compatibility export from the uv lockfile."""

import argparse
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS = ROOT / "requirements.txt"
EXPORT_COMMAND = ("uv", "export", "--locked", "--no-emit-project")
DRIFT_EXIT = 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    options = parser.parse_args(argv)
    result = subprocess.run(EXPORT_COMMAND, cwd=ROOT, capture_output=True, text=True)
    if result.returncode:
        print(result.stderr, file=sys.stderr, end="")
        return result.returncode
    if options.check:
        if not REQUIREMENTS.exists() or REQUIREMENTS.read_text() != result.stdout:
            print("requirements.txt is stale. Run make requirements.", file=sys.stderr)
            return DRIFT_EXIT
    else:
        # Never truncate the existing export if uv rejects the lockfile.
        REQUIREMENTS.write_text(result.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
