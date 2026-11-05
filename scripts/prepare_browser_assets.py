"""Cache checksum-pinned copies of the app's CDN assets for offline browser tests."""

import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "browser/assets.json"
DESTINATION = ROOT / ".browser-cache/assets"
DOWNLOAD_TIMEOUT = 30


def main():
    DESTINATION.mkdir(parents=True, exist_ok=True)
    for asset in json.loads(MANIFEST.read_text()):
        target = DESTINATION / asset["file"]
        if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == asset["sha256"]:
            continue
        with urlopen(asset["url"], timeout=DOWNLOAD_TIMEOUT) as response:
            body = response.read()
        if hashlib.sha256(body).hexdigest() != asset["sha256"]:
            raise ValueError("Browser asset checksum mismatch: " + asset["url"])
        target.write_bytes(body)
        print("Cached " + asset["file"])


if __name__ == "__main__":
    main()
