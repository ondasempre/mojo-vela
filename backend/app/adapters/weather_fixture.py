"""Fixture weather provider — deterministic, offline, always available.

Used for tests, for demos, and as the automatic fallback when the real provider is
unreachable so that the app still starts and is explorable on a train.

**Everything it returns is invented.** The provenance is `SYNTHETIC`, every forecast
carries a note saying so, and the UI shows a permanent banner in demo mode. That
banner is not decoration: a synthetic forecast presented as real is the single worst
thing this application could do.
"""

from __future__ import annotations

import hashlib
import math
from datetime import UTC, date, datetime

from sailwise_ref.weather import HourlyWeather

from ..ports import Forecast, ProviderCapabilities

SYNTHETIC_NOTE = (
    "SYNTHETIC DATA — invented for demonstration. This is not a forecast and says "
    "nothing about real conditions at this place."
)


class FixtureWeatherProvider:
    id = "fixture"

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(waves=False, visibility=True, storm_probability=True)

    async def hourly(
        self, spot_id: str, lat: float, lon: float, day: date, timezone_name: str
    ) -> Forecast:
        return self.build(spot_id=spot_id, day=day)

    def build(
        self, *, spot_id: str, day: date, start_hour: int = 7, end_hour: int = 20
    ) -> Forecast:
        """A plausible lake thermal, varied deterministically per spot and day.

        The shape is the one Lake Como actually has on a summer day — light in the
        morning, building through midday, dying in the evening — because a demo that
        produces a flat 10 kn all day would not exercise the window search or the
        trend classifier, and would teach you nothing about the product.
        """
        seed = _seed(f"{spot_id}:{day.isoformat()}")
        peak_kn = 8.0 + (seed % 13)  # 8-20 kn peak
        peak_hour = 13 + (seed // 13) % 4  # 13:00-16:00
        gust_ratio = 1.15 + ((seed // 64) % 5) * 0.06  # 1.15-1.39
        storm_afternoon = (seed // 512) % 7 == 0  # roughly one spot in seven
        base_temp = 18.0 + (seed % 11)

        hours: list[HourlyWeather] = []
        for hour in range(start_hour, end_hour + 1):
            # A raised cosine peaking at peak_hour, floored at a light background breeze.
            phase = (hour - peak_hour) / 5.0
            shape = math.exp(-(phase**2))
            wind = 2.0 + (peak_kn - 2.0) * shape
            storm_prob = 0.0
            if storm_afternoon and hour >= peak_hour + 2:
                storm_prob = min(0.75, 0.15 * (hour - peak_hour - 1))

            hours.append(
                HourlyWeather(
                    hour=hour,
                    wind_kn=round(wind, 1),
                    gust_kn=round(wind * gust_ratio, 1),
                    wind_dir_deg=float((seed + hour * 7) % 360),
                    temp_c=round(base_temp + 6.0 * shape, 1),
                    precip_mm=round(0.6 * storm_prob, 2),
                    precip_prob=round(min(0.9, storm_prob + 0.05), 2),
                    cloud_frac=round(min(0.9, 0.15 + storm_prob), 2),
                    visibility_m=20000.0 - 8000.0 * storm_prob,
                    storm_prob=round(storm_prob, 2),
                    pressure_hpa=1013.0,
                )
            )

        return Forecast(
            spot_id=spot_id,
            day=day,
            hours=hours,
            provider_id=self.id,
            model_id="synthetic-thermal-v1",
            provenance="SYNTHETIC",
            attribution=None,
            retrieved_at=datetime.now(UTC).isoformat(timespec="seconds"),
            notes=[SYNTHETIC_NOTE],
        )


def _seed(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)
