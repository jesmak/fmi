"""The areas with a weather warning as a map feed for map-feed-card.

A feed item is an area, not a warning: FMI warns the same municipality, region or sea area of several things over
several days, and warnings drawn one by one would lie on top of each other. Each area is drawn once, in the colour of
its highest level, with its warnings listed in its details.
"""

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, tzinfo
from functools import lru_cache
from typing import Any
from xml.etree.ElementTree import ParseError

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .cap import CapAlert, CapArea, CapInfo, LatLon, current_infos, info_level
from .const import CONF_HOURS_AHEAD, CONF_LANG, CONF_WARNING_TYPES, DOMAIN, WARNING_LEVELS, WARNINGS_SCAN_INTERVAL
from .session import FMIException
from .warning_coordinator import WarningFeed

_LOGGER = logging.getLogger(__name__)

KIND = "weather.warning"
COLORS = {"yellow": "#f2c200", "orange": "#ef6c00", "red": "#d32f2f"}
# An area whose warnings are all still ahead stands back.
LATER_OPACITY = 0.45
# FMI's outlines follow every bend of a border, some 43 000 points on an ordinary day. A map of the country needs few.
TOLERANCE_M = 1000
COORDINATE_DECIMALS = 4
METRES_PER_DEGREE = 111_320

TEXTS: dict[str, dict[str, str]] = {
    "eng": {
        "yellow": "Yellow",
        "orange": "Orange",
        "red": "Red",
        "until": "in force until {when}",
        "starts": "starts {when}",
        "by_level": "Warning level",
        "by_name": "Area",
        "areas": "areas",
        "area": "area",
        "link": "Warnings on ilmatieteenlaitos.fi",
    },
    "fin": {
        "yellow": "Keltainen",
        "orange": "Oranssi",
        "red": "Punainen",
        "until": "voimassa {when} asti",
        "starts": "alkaa {when}",
        "by_level": "Varoitustaso",
        "by_name": "Alue",
        "areas": "aluetta",
        "area": "alue",
        "link": "Varoitukset ilmatieteenlaitos.fi:ssä",
    },
}
WEEKDAYS = {"eng": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"], "fin": ["ma", "ti", "ke", "to", "pe", "la", "su"]}


def feed_attributes(language: str) -> dict[str, Any]:
    texts = TEXTS[language]
    return {
        "legend": [{"color": color, "label": texts[level]} for level, color in COLORS.items()],
        "list": {
            "sort": [
                {"key": "level", "label": texts["by_level"], "property": "level_rank", "order": "desc"},
                {"key": "name", "label": texts["by_name"], "property": "name"},
            ],
            "default": "level",
            "count": texts["areas"],
            "count_one": texts["area"],
        },
    }


def area_features(
    alerts: list[CapAlert], types: frozenset[str], language: str, hours_ahead: float, now: datetime, zone: tzinfo
) -> list[dict[str, Any]]:
    """The areas with a warning of the given types in force, or starting within the hours ahead, as features.

    The largest come first, so a municipality is drawn over its region and a tap lands on it.
    """
    horizon = now + timedelta(hours=hours_ahead)
    areas: dict[str, tuple[CapArea, list[CapInfo]]] = {}
    for _alert, info in current_infos(alerts, language, types, now):
        if info.onset is not None and info.onset > horizon:
            continue
        for area in info.areas:
            if area.polygons:
                areas.setdefault(_area_id(area), (area, []))[1].append(info)
    largest_first = sorted(areas.items(), key=lambda item: -_extent(item[1][0]))
    features = (_feature(area_id, area, infos, language, now, zone) for area_id, (area, infos) in largest_first)
    return [feature for feature in features if feature["geometry"]["coordinates"]]


def next_change(alerts: list[CapAlert], types: frozenset[str], language: str, hours_ahead: float, now: datetime) -> datetime | None:
    """When the feed next changes by itself: a warning comes within the hours ahead, starts or runs out."""
    ahead = timedelta(hours=hours_ahead)
    moments = [
        moment
        for _alert, info in current_infos(alerts, language, types, now)
        for moment in (info.onset - ahead if info.onset else None, info.onset, info.expires)
        if moment is not None and moment > now
    ]
    return min(moments, default=None)


def _area_id(area: CapArea) -> str:
    # FMI's code for the area, a municipality's number, a region's ISO code or a sea area's, which stays when the
    # warnings change. An area without one is known by its name.
    return f"area:{next(iter(area.geocodes.values()), area.name)}"


def _extent(area: CapArea) -> float:
    points = [point for polygon in area.polygons for point in polygon]
    latitudes, longitudes = [lat for lat, _ in points], [lon for _, lon in points]
    return (max(latitudes) - min(latitudes)) * (max(longitudes) - min(longitudes))


def _feature(area_id: str, area: CapArea, infos: list[CapInfo], language: str, now: datetime, zone: tzinfo) -> dict[str, Any]:
    texts = TEXTS[language]
    # A ring needs three corners and its closing point. A sliver that the tolerance flattens is left out.
    rings = [[list(point) for point in ring] for polygon in area.polygons if len(ring := simplified_ring(tuple(polygon))) >= 4]
    in_force = [info for info in infos if info.onset is None or info.onset <= now]
    # The area takes its colour from what is in force now, and from what is coming only when nothing is.
    by_level = sorted(in_force or infos, key=lambda info: (-WARNING_LEVELS.index(info_level(info)), info.onset or now))
    top = by_level[0]
    level = info_level(top)
    ordered = sorted(infos, key=lambda info: (info.onset or now, -WARNING_LEVELS.index(info_level(info))))
    if top.onset is None or top.onset <= now:
        status = texts["until"].format(when=_moment(top.expires, language, zone)) if top.expires else ""
    else:
        status = texts["starts"].format(when=_moment(top.onset, language, zone))
    properties = {
        "name": area.name,
        "kind": KIND,
        "subtitle": ", ".join(dict.fromkeys(info.event for info in by_level + ordered)),
        "color": COLORS[level],
        "list": {"text": " · ".join(filter(None, [top.event, status])), "value": texts[level]},
        "details": [
            {
                "label": info.event,
                "value": _period(info, language, zone),
                # The warning the area's colour comes from carries it.
                "tag": {"text": texts[info_level(info)], "tone": "item" if info is top else "neutral"},
            }
            for info in ordered
        ],
        "notices": list(dict.fromkeys(info.description for info in ordered if info.description)),
        "level": level,
        "level_rank": WARNING_LEVELS.index(level),
        "active": bool(in_force),
    }
    if not in_force:
        properties["opacity"] = LATER_OPACITY
    if top.web.startswith("https://"):
        properties["link"] = {"url": top.web, "label": texts["link"]}
    return {
        "type": "Feature",
        "id": area_id,
        "geometry": {"type": "MultiPolygon", "coordinates": [[ring] for ring in rings]},
        "properties": properties,
    }


def _moment(value: datetime, language: str, zone: tzinfo) -> str:
    """ "pe 9.00" in Finnish, "Fri 09:00" in English. Warnings reach five days ahead, so the weekday says which day."""
    local = value.astimezone(zone)
    clock = f"{local.hour}.{local.minute:02d}" if language == "fin" else f"{local.hour:02d}:{local.minute:02d}"
    return f"{WEEKDAYS[language][local.weekday()]} {clock}"


def _period(info: CapInfo, language: str, zone: tzinfo) -> str:
    start, end = (_moment(value, language, zone) if value else "" for value in (info.onset, info.expires))
    if info.onset and info.expires and info.onset.astimezone(zone).date() == info.expires.astimezone(zone).date():
        return f"{start}–{end.split(' ', 1)[1]}"
    return f"{start} – {end}".strip()


@lru_cache(maxsize=1024)
def simplified_ring(polygon: tuple[LatLon, ...]) -> tuple[tuple[float, float], ...]:
    """The polygon as a GeoJSON ring of [longitude, latitude], with the points that bend it less than the tolerance
    left out (Douglas-Peucker). The same areas come in warning after warning, so each is worked out once.
    """
    scale = METRES_PER_DEGREE * math.cos(math.radians(polygon[0][0]))
    points = [(longitude * scale, latitude * METRES_PER_DEGREE) for latitude, longitude in polygon]
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        start, end = stack.pop()
        farthest, distance = -1, float(TOLERANCE_M)
        for index in range(start + 1, end):
            offset = _distance_to_segment(points[index], points[start], points[end])
            if offset > distance:
                farthest, distance = index, offset
        if farthest >= 0:
            keep[farthest] = True
            stack += [(start, farthest), (farthest, end)]
    return tuple(
        (round(longitude, COORDINATE_DECIMALS), round(latitude, COORDINATE_DECIMALS))
        for (latitude, longitude), kept in zip(polygon, keep, strict=True)
        if kept
    )


def _distance_to_segment(point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]) -> float:
    (x, y), (x1, y1), (x2, y2) = point, start, end
    dx, dy = x2 - x1, y2 - y1
    length_squared = dx * dx + dy * dy
    # A ring starts and ends at the same point, so its first span has no length.
    along = 0.0 if length_squared == 0 else max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / length_squared))
    return math.hypot(x - x1 - along * dx, y - y1 - along * dy)


@dataclass(frozen=True)
class WarningMapData:
    features: list[dict[str, Any]]
    updated: datetime


class FMIWarningMapCoordinator(DataUpdateCoordinator[WarningMapData]):
    """The warning areas of the whole country, for one map."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, subentry: ConfigSubentry, feed: WarningFeed):
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {subentry.title}",
            update_interval=timedelta(minutes=WARNINGS_SCAN_INTERVAL),
        )
        self.subentry = subentry
        self.unique_id = subentry.subentry_id
        self.language: str = entry.data[CONF_LANG]
        self._types = frozenset(subentry.data[CONF_WARNING_TYPES])
        self._hours_ahead = float(subentry.data[CONF_HOURS_AHEAD])
        self._feed = feed

    async def _async_update_data(self) -> WarningMapData:
        now = dt_util.utcnow()
        try:
            alerts = await self._feed.async_alerts()
        except (FMIException, ParseError) as exception:
            raise UpdateFailed(f"Could not read FMI's warning feed: {exception}") from exception
        selection = (alerts, self._types, self.language, self._hours_ahead, now)
        features = await self.hass.async_add_executor_job(area_features, *selection, dt_util.get_default_time_zone())
        # A warning that starts or runs out between two reads of the feed changes the map then, not minutes later.
        change = next_change(*selection)
        scan = timedelta(minutes=WARNINGS_SCAN_INTERVAL)
        self.update_interval = min(scan, change - now + timedelta(seconds=1)) if change else scan
        return WarningMapData(features, now)
