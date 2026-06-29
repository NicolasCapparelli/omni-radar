"""Download the OpenSky aircraft database CSV for offline `mdl` enrichment.

The server auto-downloads this on startup when missing/stale (see
AIRCRAFT_DB_* settings), so running this manually is optional — useful for
pre-fetching or forcing a refresh.

Usage:
    python scripts/download_aircraft_db.py
    python scripts/download_aircraft_db.py --url <custom_url> --out data/aircraftDatabase.csv

The file is large (~100+ MB) and is streamed to disk to keep memory flat.
If the default URL ever 404s, grab the current link from the OpenSky datasets
page (https://opensky-network.org/data/aircraft) and pass it via --url.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running as a plain script (python scripts/download_aircraft_db.py).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.aircraft_db import DEFAULT_DB_URL, download_database  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=DEFAULT_DB_URL, help="CSV source URL")
    parser.add_argument(
        "--out", default="data/aircraftDatabase.csv", help="Output file path"
    )
    args = parser.parse_args()

    print(f"Downloading {args.url}\n         -> {args.out}")
    out_path = download_database(args.url, args.out, progress=True)
    print(f"Done. Saved to {out_path}")


if __name__ == "__main__":
    main()
