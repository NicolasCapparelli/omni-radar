"""Outbound payload schema served to the ESP32.

Field names are fully descriptive and carry their unit of measure where one
applies (e.g. ``altitude_feet``, ``speed_knots``) so the JSON is self-documenting
for the firmware author.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class AircraftPayload(BaseModel):
    """A single tracked vehicle."""

    callsign: str = Field(description="Aircraft alphanumeric callsign identifier.")
    vehicle_type: str = Field(
        description="Vehicle classification: Plane, Helicopter, Glider, "
        "Seaplane, Amphibian, Gyrocopter, Tiltrotor, Lighter-than-air, "
        "Ultralight, Skydiver, Drone, Spacecraft, Surface Vehicle, Obstacle."
    )
    model_code: str = Field(default="Unknown",
                            description="ICAO aircraft type designator (e.g. B772, A321).")
    model_name: str = Field(default="Unknown",
                            description="Friendly model name (e.g. Bell 429).")
    airline: str = Field(default="Unknown Airline",
                         description="Airline / commercial operator name.")
    origin: str = Field(default="N/A",
                        description="Three-letter origin airport code (IATA).")
    origin_name: str = Field(default="Unknown Route",
                             description="Full origin airport facility name.")
    origin_country: str = Field(default="",
                                description="Origin airport country (ISO alpha-2).")
    destination: str = Field(default="N/A",
                             description="Three-letter destination airport code (IATA).")
    destination_name: str = Field(default="Unknown Route",
                                  description="Full destination airport facility name.")
    destination_country: str = Field(default="",
                                     description="Destination airport country (ISO alpha-2).")
    altitude_feet: int = Field(default=0, description="Barometric altitude in feet.")
    speed_knots: int = Field(default=0, description="Ground speed in knots.")
    vertical_speed_fpm: int = Field(
        default=0,
        description="Vertical speed in feet per minute (+climb, -descent).",
    )
    heading_degrees: int = Field(default=0,
                                 description="True ground-track heading, 0-359 degrees.")
    latitude: float | None = Field(default=None, description="WGS-84 latitude (degrees).")
    longitude: float | None = Field(default=None, description="WGS-84 longitude (degrees).")
    squawk: str = Field(default="", description="Transponder squawk code.")
    emergency: str = Field(
        default="None",
        description="Emergency status (Hijack, Radio Failure, Emergency) from "
        "the squawk code, else None.",
    )
    on_ground: bool = Field(default=False, description="True if on the ground.")
    country: str = Field(default="Unknown",
                         description="Origin country (from the ICAO24 allocation).")
    registration: str = Field(default="Unknown",
                              description="Registration / tail number.")
    operator_class: str = Field(
        default="Unknown",
        description="Operator category: Commercial, Cargo, Private, Military, "
        "Government, Unknown.",
    )
    operator: str = Field(default="Unknown",
                          description="Operating airline / company name.")
    owner: str = Field(default="Unknown", description="Registered owner.")
    special_designation: str = Field(
        default="None",
        description="Special operator flag (Military, Police, News, Cargo, ...).",
    )


class VesselPayload(BaseModel):
    """A single tracked marine vessel (AIS).

    The marine counterpart to :class:`AircraftPayload`. Overlapping concepts
    (speed, heading, country, operator class) keep the same field names; the
    rest is domain-specific (draught, ETA, nav status, dimensions). There is no
    altitude/squawk here, and no draught/ETA on the aircraft side — the hard
    external cutoff between AIR and MARINE.
    """

    mmsi: str = Field(description="Maritime Mobile Service Identity (9 digits).")
    name: str = Field(default="Unknown", description="Vessel name.")
    callsign: str = Field(default="", description="Radio callsign.")
    imo_number: str = Field(default="Unknown",
                            description="IMO ship identification number.")
    vessel_type: str = Field(
        default="Unknown",
        description="Vessel category: Cargo, Tanker, Passenger, Fishing, Tug, "
        "Sailing, Pleasure Craft, High-Speed Craft, Pilot Vessel, "
        "Search and Rescue, Law Enforcement, Military, ...",
    )
    ship_type_code: int = Field(default=0,
                                description="Raw AIS ship type code (0-99).")
    nav_status: str = Field(default="Unknown",
                            description="Navigational status (e.g. Under way using engine).")
    destination: str = Field(default="N/A",
                             description="Reported destination (free-text from AIS).")
    eta: str = Field(default="", description="Reported ETA (MM-DD HH:MM UTC), if any.")
    speed_knots: int = Field(default=0, description="Speed over ground in knots.")
    course_degrees: int = Field(default=0,
                                description="Course over ground, 0-359 degrees.")
    heading_degrees: int = Field(default=0,
                                 description="True heading, 0-359 degrees.")
    latitude: float | None = Field(default=None, description="WGS-84 latitude (degrees).")
    longitude: float | None = Field(default=None, description="WGS-84 longitude (degrees).")
    length_meters: int = Field(default=0, description="Overall length in meters.")
    beam_meters: int = Field(default=0, description="Overall beam (width) in meters.")
    draught_meters: float = Field(default=0.0,
                                  description="Maximum static draught in meters.")
    country: str = Field(default="Unknown",
                         description="Flag state (from the MMSI MID).")
    country_iso: str = Field(default="",
                             description="Flag state ISO alpha-2 code (for flags).")
    operator_class: str = Field(
        default="Unknown",
        description="Operator category: Commercial, Fishing, Military, "
        "Government, Pleasure, Unknown.",
    )
    special_designation: str = Field(
        default="None",
        description="Special flag (Military, Law Enforcement, Search and "
        "Rescue, Pilot, Tug, Medical, ...).",
    )
