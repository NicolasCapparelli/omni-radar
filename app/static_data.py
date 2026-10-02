"""Static lookup tables used for free, offline enrichment.

The spec allows the middleware to lean on "local flight schedule dictionaries,
registration lookups" to avoid burning downstream API credits. These tables map
ICAO three-letter airline designators (which, for airline traffic, are also the
alphabetic prefix of the callsign — e.g. ``AAL123`` -> ``AAL``) to a friendly
operator name.

Designators sourced from the ICAO/IATA airline code lists
(https://en.wikipedia.org/wiki/List_of_airline_codes) and FAA telephony
designator tables. Extend freely; treat this as seed data.
"""

from __future__ import annotations

import re

# ICAO three-letter designator -> friendly operator name.
AIRLINE_BY_ICAO: dict[str, str] = {
    # ── United States ────────────────────────────────────────────────
    "AAL": "American Airlines",
    "DAL": "Delta Air Lines",
    "UAL": "United Airlines",
    "SWA": "Southwest Airlines",
    "JBU": "JetBlue Airways",
    "FFT": "Frontier Airlines",
    "NKS": "Spirit Airlines",
    "ASA": "Alaska Airlines",
    "HAL": "Hawaiian Airlines",
    "AAY": "Allegiant Air",
    "SCX": "Sun Country Airlines",
    "ENY": "Envoy Air",
    "SKW": "SkyWest Airlines",
    "RPA": "Republic Airways",
    "EDV": "Endeavor Air",
    "ASH": "Mesa Airlines",
    "QXE": "Horizon Air",
    "PDT": "Piedmont Airlines",
    "JIA": "PSA Airlines",
    # ── Canada ───────────────────────────────────────────────────────
    "ACA": "Air Canada",
    "WJA": "WestJet",
    "JZA": "Jazz Aviation",
    "TSC": "Air Transat",
    "POE": "Porter Airlines",
    # ── Europe ───────────────────────────────────────────────────────
    "BAW": "British Airways",
    "DLH": "Lufthansa",
    "AFR": "Air France",
    "KLM": "KLM Royal Dutch Airlines",
    "IBE": "Iberia",
    "RYR": "Ryanair",
    "EZY": "easyJet",
    "VLG": "Vueling",
    "EWG": "Eurowings",
    "SAS": "Scandinavian Airlines",
    "SWR": "Swiss International Air Lines",
    "AUA": "Austrian Airlines",
    "TAP": "TAP Air Portugal",
    "ITY": "ITA Airways",
    "FIN": "Finnair",
    "LOT": "LOT Polish Airlines",
    "THY": "Turkish Airlines",
    "AEE": "Aegean Airlines",
    "NAX": "Norwegian Air Shuttle",
    "WZZ": "Wizz Air",
    "BEL": "Brussels Airlines",
    "VIR": "Virgin Atlantic",
    # ── Middle East ──────────────────────────────────────────────────
    "UAE": "Emirates",
    "QTR": "Qatar Airways",
    "ETD": "Etihad Airways",
    "SVA": "Saudia",
    "ELY": "El Al",
    "MEA": "Middle East Airlines",
    "RJA": "Royal Jordanian",
    "GFA": "Gulf Air",
    "OMA": "Oman Air",
    "KAC": "Kuwait Airways",
    # ── Asia / Pacific ───────────────────────────────────────────────
    "SIA": "Singapore Airlines",
    "CPA": "Cathay Pacific",
    "ANA": "All Nippon Airways",
    "JAL": "Japan Airlines",
    "KAL": "Korean Air",
    "AAR": "Asiana Airlines",
    "CCA": "Air China",
    "CES": "China Eastern Airlines",
    "CSN": "China Southern Airlines",
    "CAL": "China Airlines",
    "EVA": "EVA Air",
    "THA": "Thai Airways",
    "MAS": "Malaysia Airlines",
    "GIA": "Garuda Indonesia",
    "PAL": "Philippine Airlines",
    "QFA": "Qantas",
    "ANZ": "Air New Zealand",
    "VOZ": "Virgin Australia",
    "JST": "Jetstar",
    "AIC": "Air India",
    "IGO": "IndiGo",
    "HVN": "Vietnam Airlines",
    "AXM": "AirAsia",
    "CEB": "Cebu Pacific",
    "TGW": "Scoot",
    # ── Latin America ────────────────────────────────────────────────
    "LAN": "LATAM Airlines",
    "TAM": "LATAM Brasil",
    "GLO": "GOL Linhas Aereas",
    "AZU": "Azul Brazilian Airlines",
    "AVA": "Avianca",
    "AMX": "Aeromexico",
    "VOI": "Volaris",
    "CMP": "Copa Airlines",
    # ── Africa ───────────────────────────────────────────────────────
    "ETH": "Ethiopian Airlines",
    "SAA": "South African Airways",
    "MSR": "EgyptAir",
    "RAM": "Royal Air Maroc",
    "KQA": "Kenya Airways",
    # ── Cargo ────────────────────────────────────────────────────────
    "FDX": "FedEx Express",
    "UPS": "UPS Airlines",
    "GTI": "Atlas Air",
    "GEC": "Lufthansa Cargo",
    "CLX": "Cargolux",
    "BOX": "AeroLogic",
    "CKS": "Kalitta Air",
    "ABX": "ABX Air",
    "PAC": "Polar Air Cargo",
    "NCA": "Nippon Cargo Airlines",
    "DHK": "DHL Air",
    "BCS": "DHL (European Air Transport)",
}

# Special-operator classification by ICAO/callsign prefix -> spec flag.
SPECIAL_BY_CALLSIGN_PREFIX: dict[str, str] = {
    # Cargo
    "FDX": "Cargo",
    "UPS": "Cargo",
    "GTI": "Cargo",
    "GEC": "Cargo",
    "CLX": "Cargo",
    "BOX": "Cargo",
    "CKS": "Cargo",
    "ABX": "Cargo",
    "PAC": "Cargo",
    "NCA": "Cargo",
    "DHK": "Cargo",
    "BCS": "Cargo",
    # Military / state
    "RCH": "Military",  # Reach (US Air Mobility Command)
    "CNV": "Military",  # US Navy
    "EVAC": "Military",
    "SAM": "Military",  # Special Air Mission (US government / VIP)
}

# Callsign regex patterns -> spec flag. Checked after prefix lookups.
SPECIAL_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^N\d+PD$", re.IGNORECASE), "Police"),   # e.g. N203PD (NYPD)
    (re.compile(r"^NYPD", re.IGNORECASE), "Police"),
    (re.compile(r"^(LIFE|MEDEVAC|MED|ANGEL)", re.IGNORECASE), "Medical"),
    (re.compile(r"(NEWS|CHOPPER|SKY\d+)", re.IGNORECASE), "News"),
]

# Known military ICAO24 address ranges (inclusive, as ints). Extend as needed.
# The US block is A00000-AFFFFF: civil N-numbers run A00001 (N1) through
# ADF7C7 (N99999), and everything above that is the US military allocation.
MILITARY_ICAO24_RANGES: tuple[tuple[int, int], ...] = (
    (0xADF7C8, 0xAFFFFF),  # US military
)


def _is_military_icao24(icao24: str) -> bool:
    try:
        addr = int(icao24, 16)
    except ValueError:
        return False
    return any(lo <= addr <= hi for lo, hi in MILITARY_ICAO24_RANGES)


def _callsign_prefix(callsign: str) -> str:
    """Return the leading alphabetic prefix of a callsign (e.g. 'AAL123' -> 'AAL')."""
    match = re.match(r"^([A-Za-z]+)", callsign.strip())
    return match.group(1).upper() if match else ""


def airline_from_icao(code: str | None) -> str | None:
    """Resolve a friendly airline name from an ICAO designator, if known."""
    if not code:
        return None
    return AIRLINE_BY_ICAO.get(code.strip().upper())


def airline_from_callsign(callsign: str) -> str | None:
    """Resolve a friendly airline name from a callsign prefix, if known."""
    return AIRLINE_BY_ICAO.get(_callsign_prefix(callsign))


def special_designation(callsign: str, icao24: str = "") -> str:
    """Classify a special operator ('Military', 'Police', 'Cargo', ...).

    Returns ``"None"`` when no special designation applies. Resolution order:
    callsign prefix -> callsign regex patterns -> ICAO24 military address range.
    """
    callsign = (callsign or "").strip()

    prefix_hit = SPECIAL_BY_CALLSIGN_PREFIX.get(_callsign_prefix(callsign))
    if prefix_hit:
        return prefix_hit

    for pattern, flag in SPECIAL_PATTERNS:
        if pattern.search(callsign):
            return flag

    icao = (icao24 or "").strip()
    if icao and _is_military_icao24(icao):
        return "Military"

    return "None"


# Callsign prefixes flagged as cargo operators (subset of SPECIAL_*).
_CARGO_PREFIXES = {k for k, v in SPECIAL_BY_CALLSIGN_PREFIX.items() if v == "Cargo"}

# Registration / tail-number shapes (used to infer private / GA traffic).
_REGISTRATION_PATTERNS = (
    re.compile(r"^N\d"),          # US N-number, e.g. N919PD
    re.compile(r"^[A-Z]{1,2}-"),  # hyphenated regs, e.g. G-ABCD, D-ABCD, C-FXYZ
)


def _looks_like_registration(callsign: str, registration: str | None = None) -> bool:
    """Heuristic: does the callsign look like an aircraft registration (tail #)?"""
    cs = (callsign or "").strip().upper()
    if not cs:
        return False
    if registration:
        norm = lambda s: s.upper().replace("-", "").replace(" ", "")
        if norm(cs) == norm(registration):
            return True
    return any(p.match(cs) for p in _REGISTRATION_PATTERNS)


def operator_class(
    callsign: str,
    icao24: str = "",
    registration: str | None = None,
    airline: str | None = None,
) -> str:
    """Classify the broad operator category of a flight.

    Returns one of: ``Commercial``, ``Cargo``, ``Private``, ``Military``,
    ``Government``, or ``Unknown``. Derived from offline signals (the callsign,
    static tables, optional DB registration) plus the resolved airline name.
    Resolution order puts a tail-number callsign ahead of the airline check, so
    GA/private traffic stays ``Private`` even when a route was found.
    """
    spec = special_designation(callsign, icao24)
    if spec == "Military":
        return "Military"
    if spec in ("Police", "Medical"):
        return "Government"
    if spec == "Cargo":
        return "Cargo"

    prefix = _callsign_prefix(callsign)
    if prefix in _CARGO_PREFIXES:
        return "Cargo"
    if prefix in AIRLINE_BY_ICAO:
        return "Commercial"
    if _looks_like_registration(callsign, registration):
        return "Private"
    # Charter / regional operators not in the static table: if a route provider
    # resolved a real airline name, treat as commercial.
    if airline and airline != "Unknown Airline":
        return "Commercial"
    return "Unknown"
