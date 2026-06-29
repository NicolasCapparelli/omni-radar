"""Offline aircraft metadata, backed by the OpenSky aircraft database.

A free, no-quota source for: the ``mdl`` field (ICAO type designator like
``B429``), a friendly model name (``Bell 429``), and helicopter detection — all
keyed by the airframe's 24-bit ICAO address present in every state vector.

Helicopter detection uses the ICAO Doc 8643 description code (column
``icaoaircrafttype``, e.g. ``H2T``) whose leading ``H`` denotes a rotorcraft;
this is far more reliable than OpenSky's broadcast ``category``, which many
transponders leave unset.

Download the CSV once (see ``scripts/download_aircraft_db.py`` or the README),
or let the server auto-download it on startup when missing/stale. Point
``AIRCRAFT_DB_PATH`` at it. If the file is absent, lookups return ``None``/
``False`` and the rest of the pipeline degrades gracefully.

Dataset: https://opensky-network.org/datasets/metadata/aircraftDatabase.csv
"""

from __future__ import annotations

import csv
import logging
import time
from pathlib import Path
from typing import NamedTuple, Optional

import httpx

logger = logging.getLogger("traffic_radar.aircraft_db")

DEFAULT_DB_URL = "https://opensky-network.org/datasets/metadata/aircraftDatabase.csv"


def _clean(value: Optional[str]) -> str:
    """Normalize a CSV cell: strip whitespace and stray quote characters."""
    if value is None:
        return ""
    return value.strip().strip("'\"").strip()


def download_database(
    url: str = DEFAULT_DB_URL,
    out: str | Path = "data/aircraftDatabase.csv",
    progress: bool = False,
) -> Path:
    """Stream the aircraft database CSV to ``out`` (atomic via a temp file).

    Downloads to ``<out>.tmp`` first and only replaces the destination on
    success, so an interrupted download never corrupts an existing file.
    """
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")

    bytes_written = 0
    with httpx.stream("GET", url, follow_redirects=True, timeout=60.0) as resp:
        resp.raise_for_status()
        with tmp_path.open("wb") as fh:
            for chunk in resp.iter_bytes(chunk_size=1 << 16):
                fh.write(chunk)
                bytes_written += len(chunk)
                if progress:
                    print(f"\r  {bytes_written / 1_048_576:6.1f} MB", end="", flush=True)
    if progress:
        print()
    tmp_path.replace(out_path)
    logger.info("Downloaded aircraft DB: %.1f MB -> %s",
                bytes_written / 1_048_576, out_path)
    return out_path


def _is_stale(path: Path, max_age_days: float) -> bool:
    """True if ``path`` is missing or older than ``max_age_days``."""
    if not path.exists():
        return True
    if max_age_days <= 0:
        return False  # 0/negative disables the age check (never re-download)
    age_seconds = time.time() - path.stat().st_mtime
    return age_seconds > max_age_days * 86_400


def ensure_database(
    path: str | Path,
    url: str = DEFAULT_DB_URL,
    max_age_days: float = 30.0,
) -> bool:
    """Download the DB if it is missing or stale. Returns True if downloaded.

    Network/IO failures are logged and swallowed so startup never crashes — the
    middleware falls back to whatever local file exists (or no enrichment).
    """
    p = Path(path)
    if not _is_stale(p, max_age_days):
        return False

    reason = "missing" if not p.exists() else f"older than {max_age_days:g} days"
    logger.info("Aircraft DB %s; downloading from %s", reason, url)
    try:
        download_database(url, p)
        return True
    except Exception as exc:  # noqa: BLE001 - never let startup fail on this
        logger.warning("Aircraft DB download failed (%s); using existing file if present.", exc)
        return False


def _friendly_model(manufacturer: str, model: str) -> str:
    """Build a human-readable model name like 'Bell 429' from DB columns."""
    manufacturer = manufacturer.strip()
    model = model.strip()
    if manufacturer.isupper():
        manufacturer = manufacturer.title()
    if not model:
        return manufacturer
    if not manufacturer:
        return model
    if model.lower().startswith(manufacturer.lower()):
        return model
    return f"{manufacturer} {model}"


class AircraftRecord(NamedTuple):
    """Compact per-airframe metadata stored in the database."""

    typecode: str           # ICAO type designator, e.g. "B429"
    model_name: str         # friendly name, e.g. "Bell 429" (may be "")
    klass: str              # Doc 8643 descriptor first char L/S/A/H/G/T (may be "")
    registration: str       # tail number, e.g. "N919PD" (may be "")
    operator: str           # operating airline / company (may be "")
    owner: str              # registered owner (may be "")


class AircraftDatabase:
    """In-memory aircraft metadata keyed by ICAO24 hex address.

    Stores, per airframe: ICAO type designator (``B429``), friendly model name
    (``Bell 429``), airframe class char from the ICAO Doc 8643 descriptor (a
    leading ``H`` denotes a helicopter), and registration / tail number.
    """

    def __init__(self) -> None:
        self._by_icao24: dict[str, AircraftRecord] = {}
        self._loaded = False
        self._source: Optional[str] = None

    @property
    def loaded(self) -> bool:
        return self._loaded

    @property
    def size(self) -> int:
        return len(self._by_icao24)

    def load(self, path: str | Path) -> "AircraftDatabase":
        """Load the aircraft database CSV from ``path`` (blocking, run in a thread).

        Tolerant of the OpenSky column layout: needs ``icao24`` plus a type
        column (``typecode``, falling back to ``icaoaircrafttype``). Also reads
        ``manufacturericao``/``manufacturername`` + ``model`` for a friendly
        name, ``icaoaircrafttype`` (Doc 8643 descriptor) for airframe class, and
        ``registration``. Missing files and malformed rows are skipped silently.
        """
        p = Path(path)
        if not p.exists():
            logger.warning(
                "Aircraft DB not found at %s; offline model fallback disabled. "
                "Run scripts/download_aircraft_db.py to enable it.",
                p,
            )
            return self

        store = self._by_icao24
        with p.open("r", encoding="utf-8", errors="ignore", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                icao = _clean(row.get("icao24")).lower()
                if not icao:
                    continue

                descriptor = _clean(row.get("icaoaircrafttype"))  # e.g. "H2T"
                typecode = _clean(row.get("typecode")) or descriptor
                if not typecode:
                    continue

                manufacturer = _clean(row.get("manufacturericao")) or _clean(
                    row.get("manufacturername")
                )
                store[icao] = AircraftRecord(
                    typecode=typecode,
                    model_name=_friendly_model(manufacturer, _clean(row.get("model"))),
                    klass=descriptor[0].upper() if descriptor else "",
                    registration=_clean(row.get("registration")),
                    operator=_clean(row.get("operator")),
                    owner=_clean(row.get("owner")),
                )

        self._loaded = True
        self._source = str(p)
        rotorcraft = sum(1 for r in store.values() if r.klass == "H")
        logger.info(
            "Loaded aircraft DB: %d airframes (%d rotorcraft) from %s",
            len(store), rotorcraft, p,
        )
        return self

    def get(self, icao24: Optional[str]) -> Optional[AircraftRecord]:
        """Return the full record for an ICAO24 address, or ``None``."""
        if not icao24:
            return None
        return self._by_icao24.get(icao24.strip().lower())

    def lookup_type(self, icao24: Optional[str]) -> Optional[str]:
        """Return the ICAO type designator for an ICAO24 address, or ``None``."""
        rec = self.get(icao24)
        return rec.typecode if rec else None

    def lookup_model_name(self, icao24: Optional[str]) -> Optional[str]:
        """Return the friendly model name (e.g. 'Bell 429'), or ``None``."""
        rec = self.get(icao24)
        return (rec.model_name or None) if rec else None

    def lookup_registration(self, icao24: Optional[str]) -> Optional[str]:
        """Return the registration / tail number, or ``None``."""
        rec = self.get(icao24)
        return (rec.registration or None) if rec else None

    def is_rotorcraft(self, icao24: Optional[str]) -> bool:
        """True if the airframe is a helicopter per the Doc 8643 descriptor."""
        return self.descriptor_class(icao24) == "H"

    def descriptor_class(self, icao24: Optional[str]) -> Optional[str]:
        """Return the ICAO Doc 8643 descriptor first char (L/S/A/H/G/T) or None."""
        rec = self.get(icao24)
        return (rec.klass or None) if rec else None
