"""FMI weather warnings: reading the CAP feed and deciding which warnings concern a place.

FMI publishes every warning in force, 0-5 days ahead, as a Common Alerting
Protocol (CAP) document listed in an Atom feed. The profile is documented at
https://alerts.fmi.fi/cap/profile/v1.1.0.

A warning's areas always carry polygons but only sometimes codes (sea area,
municipality or region), so warnings are matched to a place by geometry: a
warning concerns the place when one of its areas covers the configured point,
or comes within the configured radius of it. Sea area polygons include the
islands in them, so a point on an island is inside its sea area.
"""

import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from xml.etree import ElementTree

from .const import CONF_LANG, CONF_LOCATION, CONF_WARNING_TYPES, WARNING_LEVELS, WARNING_TYPES

ATOM_NAMESPACES = {"atom": "http://www.w3.org/2005/Atom"}
CAP_NAMESPACES = {"cap": "urn:oasis:names:tc:emergency:cap:1.2"}

# Every CAP document has its texts in Finnish, Swedish and English.
CAP_LANGUAGES = {"fin": "fi-FI", "eng": "en-GB"}
FALLBACK_CAP_LANGUAGE = "en-GB"

# The level of a warning is its "color" parameter; severity is the fallback if it is ever missing.
SEVERITY_LEVELS = {"Moderate": "yellow", "Severe": "orange", "Extreme": "red"}

# Parameters that become fields of their own instead of staying in `parameters`.
PROMOTED_PARAMETERS = {"color", "typicalImpacts", "probability", "probabilityUom"}

EVENT_ISSUED = "issued"
EVENT_UPDATED = "updated"
EVENT_CANCELLED = "cancelled"
EVENT_TYPES = [EVENT_ISSUED, EVENT_UPDATED, EVENT_CANCELLED]

METRES_PER_DEGREE_LATITUDE = 111_320

LatLon = tuple[float, float]


# ---------------- the feed and the documents ----------------


def parse_warning_feed(content: bytes) -> list[str]:
    """The CAP document addresses listed in FMI's Atom feed."""
    root = ElementTree.fromstring(content)
    return [
        link.get("href")
        for entry in root.findall("atom:entry", ATOM_NAMESPACES)
        for link in entry.findall("atom:link", ATOM_NAMESPACES)
        if link.get("type") == "application/cap+xml" and link.get("href")
    ]


@dataclass(frozen=True)
class CapArea:
    name: str
    geocodes: dict[str, str]
    polygons: list[list[LatLon]]


@dataclass(frozen=True)
class CapInfo:
    language: str
    event_code: str | None
    event: str
    severity: str
    onset: datetime | None
    expires: datetime | None
    headline: str
    description: str
    parameters: dict[str, str]
    areas: list[CapArea]


@dataclass(frozen=True)
class CapAlert:
    identifier: str
    msg_type: str
    # Identifiers of the earlier messages this one replaces (msgType Update or Cancel).
    references: list[str]
    infos: list[CapInfo]

    def info(self, language: str) -> CapInfo | None:
        """The texts in the entry's language, or in English, or whatever there is."""
        for wanted in (CAP_LANGUAGES.get(language, FALLBACK_CAP_LANGUAGE), FALLBACK_CAP_LANGUAGE):
            for info in self.infos:
                if info.language == wanted:
                    return info
        return self.infos[0] if self.infos else None


def parse_alert(content: bytes) -> CapAlert:
    root = ElementTree.fromstring(content)
    return CapAlert(
        identifier=_text(root, "identifier"),
        msg_type=_text(root, "msgType"),
        references=parse_references(_text(root, "references")),
        infos=[_parse_info(info) for info in root.findall("cap:info", CAP_NAMESPACES)],
    )


def parse_references(text: str) -> list[str]:
    """Identifiers from a CAP references element: space separated "sender,identifier,sent" triplets."""
    return [parts[1] for parts in (item.split(",") for item in text.split()) if len(parts) == 3]


def parse_polygon(text: str) -> list[LatLon]:
    """A CAP polygon: space separated "latitude,longitude" pairs."""
    points = []
    for pair in text.split():
        try:
            latitude, longitude = (float(value) for value in pair.split(","))
        except ValueError:
            continue
        points.append((latitude, longitude))
    return points


def _parse_info(info: ElementTree.Element) -> CapInfo:
    return CapInfo(
        language=_text(info, "language"),
        event_code=next((_text(code, "value") for code in info.findall("cap:eventCode", CAP_NAMESPACES)), None),
        event=_text(info, "event"),
        severity=_text(info, "severity"),
        onset=_time(_text(info, "onset")),
        expires=_time(_text(info, "expires")),
        headline=_text(info, "headline"),
        description=_text(info, "description"),
        parameters={
            _text(parameter, "valueName"): _text(parameter, "value") for parameter in info.findall("cap:parameter", CAP_NAMESPACES)
        },
        areas=[_parse_area(area) for area in info.findall("cap:area", CAP_NAMESPACES)],
    )


def _parse_area(area: ElementTree.Element) -> CapArea:
    polygons = [parse_polygon(polygon.text or "") for polygon in area.findall("cap:polygon", CAP_NAMESPACES)]
    return CapArea(
        name=_text(area, "areaDesc"),
        geocodes={_text(code, "valueName"): _text(code, "value") for code in area.findall("cap:geocode", CAP_NAMESPACES)},
        polygons=[polygon for polygon in polygons if len(polygon) >= 3],
    )


def _text(element: ElementTree.Element, name: str) -> str:
    return (element.findtext(f"cap:{name}", default="", namespaces=CAP_NAMESPACES) or "").strip()


def _time(text: str) -> datetime | None:
    try:
        return datetime.fromisoformat(text) if text else None
    except ValueError:
        return None


# ---------------- geometry ----------------


def area_concerns(area: CapArea, latitude: float, longitude: float, radius_m: float) -> bool:
    """Whether the area covers the point, or comes within radius_m of it."""
    return any(
        point_in_polygon(latitude, longitude, polygon) or (radius_m > 0 and distance_to_outline_m(latitude, longitude, polygon) <= radius_m)
        for polygon in area.polygons
    )


def point_in_polygon(latitude: float, longitude: float, polygon: list[LatLon]) -> bool:
    """Ray casting: count how many edges a ray from the point crosses."""
    inside = False
    for (lat1, lon1), (lat2, lon2) in zip(polygon, polygon[1:] + polygon[:1], strict=True):
        if (lat1 > latitude) != (lat2 > latitude):
            crossing = lon1 + (latitude - lat1) * (lon2 - lon1) / (lat2 - lat1)
            if longitude < crossing:
                inside = not inside
    return inside


def distance_to_outline_m(latitude: float, longitude: float, polygon: list[LatLon]) -> float:
    """Shortest distance from the point to the polygon's outline in metres.

    Uses a flat projection around the point, which is accurate to well under a
    percent over the few kilometres a radius is meant for.
    """
    metres_per_degree_longitude = METRES_PER_DEGREE_LATITUDE * math.cos(math.radians(latitude))
    points = [((lon - longitude) * metres_per_degree_longitude, (lat - latitude) * METRES_PER_DEGREE_LATITUDE) for lat, lon in polygon]
    edges = zip(points, points[1:] + points[:1], strict=True)
    return min(_distance_from_origin_to_segment(start, end) for start, end in edges)


def _distance_from_origin_to_segment(start: tuple[float, float], end: tuple[float, float]) -> float:
    (x1, y1), (x2, y2) = start, end
    dx, dy = x2 - x1, y2 - y1
    length_squared = dx * dx + dy * dy
    along = 0.0 if length_squared == 0 else max(0.0, min(1.0, -(x1 * dx + y1 * dy) / length_squared))
    return math.hypot(x1 + along * dx, y1 + along * dy)


# ---------------- the warnings of a place ----------------


@dataclass(frozen=True)
class WarningsFilter:
    """What a warnings entry follows: a place, a radius around it, and warning types."""

    latitude: float
    longitude: float
    radius_m: float
    types: frozenset[str]
    language: str

    @classmethod
    def from_entry_data(cls, data: dict[str, Any]) -> "WarningsFilter":
        location = data[CONF_LOCATION]
        return cls(
            latitude=float(location["latitude"]),
            longitude=float(location["longitude"]),
            radius_m=float(location.get("radius") or 0),
            types=frozenset(data.get(CONF_WARNING_TYPES) or WARNING_TYPES),
            language=data[CONF_LANG],
        )


@dataclass(frozen=True)
class FMIWarning:
    """One warning that concerns the place, in the entry's language."""

    identifier: str
    references: tuple[str, ...]
    type: str
    level: str
    event: str
    severity: str
    onset: datetime | None
    expires: datetime | None
    headline: str
    description: str
    impacts: str
    probability: int | None
    # Only the warning's areas that concern the place.
    areas: tuple[str, ...]
    parameters: dict[str, Any]

    def is_active(self, now: datetime) -> bool:
        return (self.onset is None or self.onset <= now) and (self.expires is None or now < self.expires)

    def content(self) -> tuple:
        """Everything a person would notice changing. FMI's identifiers change on every reissue."""
        return (
            self.type,
            self.level,
            self.onset,
            self.expires,
            self.headline,
            self.description,
            self.impacts,
            self.probability,
            self.areas,
            tuple(sorted(self.parameters.items())),
        )

    def as_dict(self) -> dict[str, Any]:
        """For state attributes and event data."""
        return {
            "id": self.identifier,
            "type": self.type,
            "level": self.level,
            "event": self.event,
            "severity": self.severity,
            "onset": self.onset.isoformat() if self.onset else None,
            "expires": self.expires.isoformat() if self.expires else None,
            "headline": self.headline,
            "description": self.description,
            "impacts": self.impacts,
            "probability": self.probability,
            "areas": list(self.areas),
            "parameters": dict(self.parameters),
        }


def warnings_for(alerts: Iterable[CapAlert], warnings_filter: WarningsFilter, now: datetime) -> dict[str, FMIWarning]:
    """The warnings in force or coming up that concern the place, by identifier."""
    alerts = list(alerts)
    # If a replaced message is still listed next to its replacement, only the replacement counts.
    replaced = {reference for alert in alerts for reference in alert.references}
    result = {}

    for alert in alerts:
        if alert.msg_type == "Cancel" or alert.identifier in replaced:
            continue
        info = alert.info(warnings_filter.language)
        if info is None or info.event_code not in warnings_filter.types:
            continue
        if info.expires is not None and info.expires <= now:
            continue
        areas = [
            area.name
            for area in info.areas
            if area_concerns(area, warnings_filter.latitude, warnings_filter.longitude, warnings_filter.radius_m)
        ]
        if not areas:
            continue
        result[alert.identifier] = _warning(alert, info, areas)

    return result


def _warning(alert: CapAlert, info: CapInfo, areas: list[str]) -> FMIWarning:
    parameters = info.parameters
    return FMIWarning(
        identifier=alert.identifier,
        references=tuple(alert.references),
        type=info.event_code or "",
        level=parameters.get("color") or SEVERITY_LEVELS.get(info.severity, "yellow"),
        event=info.event,
        severity=info.severity,
        onset=info.onset,
        expires=info.expires,
        headline=info.headline,
        description=info.description,
        impacts=parameters.get("typicalImpacts", ""),
        probability=_number(parameters["probability"]) if "probability" in parameters else None,
        areas=tuple(areas),
        parameters={name: _number(value) for name, value in parameters.items() if name not in PROMOTED_PARAMETERS},
    )


def _number(value: str) -> Any:
    """Numbers as numbers, so automations can compare them; anything else as text."""
    for kind in (int, float):
        try:
            return kind(value)
        except ValueError:
            pass
    return value


def highest_level(warnings: dict[str, FMIWarning], now: datetime) -> str:
    """The highest level among the warnings in force now; "none" when there are none."""
    levels = [warning.level for warning in warnings.values() if warning.is_active(now) and warning.level in WARNING_LEVELS[1:]]
    return max(levels, key=WARNING_LEVELS.index, default=WARNING_LEVELS[0])


def warning_changes(previous: dict[str, FMIWarning], current: dict[str, FMIWarning], now: datetime) -> list[tuple[str, FMIWarning]]:
    """What happened between two refreshes, as (event type, warning).

    FMI reissues its warnings as new messages that reference the ones they
    replace, usually without changing anything, so a reissue is only reported
    when its content changed. A warning that disappears before it expires was
    cancelled. One that simply runs out ends quietly: the level sensor shows it.
    """
    changes = []
    matched: set[str] = set()

    for identifier, warning in current.items():
        if identifier in previous:
            matched.add(identifier)
            continue
        predecessor = _predecessor(warning, previous, matched)
        if predecessor is None:
            changes.append((EVENT_ISSUED, warning))
            continue
        matched.add(predecessor.identifier)
        if predecessor.content() != warning.content():
            changes.append((EVENT_UPDATED, warning))

    for identifier, warning in previous.items():
        if identifier not in matched and (warning.expires is None or warning.expires > now):
            changes.append((EVENT_CANCELLED, warning))

    return changes


def _predecessor(warning: FMIWarning, previous: dict[str, FMIWarning], matched: set[str]) -> FMIWarning | None:
    for reference in warning.references:
        if reference in previous and reference not in matched:
            return previous[reference]
    # A failed refresh can skip a version, breaking the chain of references;
    # the same type with the same validity is then the same warning.
    return next(
        (
            old
            for old in previous.values()
            if old.identifier not in matched and old.type == warning.type and old.onset == warning.onset and old.expires == warning.expires
        ),
        None,
    )
