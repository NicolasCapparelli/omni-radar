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
