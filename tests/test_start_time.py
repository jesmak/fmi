"""How far back each kind of query reaches."""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.fmi_open_data.const import CONF_FORECAST_PAST_HOURS
from custom_components.fmi_open_data.query_coordinator import get_start_time

NOW = datetime(2026, 3, 15, 10, 30, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("query_id", "now", "expected"),
    [
        ("fmi::forecast::harmonie::surface::point::simple", NOW, datetime(2026, 3, 15, 7, 30, tzinfo=UTC)),
        ("fmi::observations::weather::hourly::simple", NOW, datetime(2026, 3, 15, 9, 0, tzinfo=UTC)),
        ("fmi::observations::weather::daily::simple", NOW, datetime(2026, 3, 13, 0, 0, tzinfo=UTC)),
        ("fmi::observations::weather::monthly::simple", NOW, datetime(2026, 1, 1, 0, 0, tzinfo=UTC)),
        ("fmi::observations::weather::monthly::simple", datetime(2026, 2, 28, tzinfo=UTC), datetime(2025, 12, 1, tzinfo=UTC)),
        ("fmi::observations::weather::monthly::simple", datetime(2026, 1, 31, tzinfo=UTC), datetime(2025, 11, 1, tzinfo=UTC)),
        ("fmi::observations::weather::yearly::simple", NOW, datetime(2024, 1, 1, 0, 0, tzinfo=UTC)),
        ("fmi::observations::weather::simple", NOW, datetime(2026, 3, 14, 22, 30, tzinfo=UTC)),
        ("stuk::observations::air::radionuclide-activity-concentration::latest::simple", NOW, NOW - timedelta(days=42)),
        ("stuk::observations::external-radiation::latest::simple", NOW, None),
    ],
)
def test_start_time(query_id: str, now: datetime, expected: datetime | None) -> None:
    assert get_start_time(query_id, now, {CONF_FORECAST_PAST_HOURS: 3}) == expected
