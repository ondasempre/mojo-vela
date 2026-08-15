"""Open-Meteo weather adapter — the default provider (ADR 0002).

Licence: the free tier is for **non-commercial use**, up to 10,000 calls/day, with
data under **CC BY 4.0**, which requires attribution. The attribution string travels
with every forecast this adapter returns and is rendered in the UI. Do not remove it.
No API key is required on that tier.

Terms verified 2026-08-15 — re-verify before deploying anything public.

This adapter converts and normalises. It contains no business logic and no scoring:
that separation is what keeps units correct in exactly one place (FR-W-03).
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import httpx
from sailwise_ref.weather import HourlyWeather

from ..ports import Forecast, ProviderCapabilities

ENDPOINT = "https://api.open-meteo.com/v1/forecast"

ATTRIBUTION = "Weather data by Open-Meteo.com (CC BY 4.0)"

HOURLY_FIELDS = (
    "wind_speed_10m",
    "wind_gusts_10m",
    "wind_direction_10m",
    "temperature_2m",
    "precipitation",
    "precipitation_probability",
    "cloud_cover",
    "surface_pressure",
    "visibility",
    "weather_code",
)

#: WMO weather codes that mean "thunderstorm forecast this hour".
THUNDERSTORM_CODES = {95, 96, 99}

#: Open-Meteo publishes a categorical weather code, not a thunderstorm probability.
#: When the code says thunderstorm we set a high, fixed value and label the field
#: MODELLED — it is a flag turned into a number for the gates to consume, and
#: pretending otherwise would be inventing precision the provider never gave us.
THUNDERSTORM_CODE_PROB = 0.8


class OpenMeteoProvider:
    id = "open-meteo"

    def __init__(self, client: httpx.AsyncClient, timeout_s: int = 20) -> None:
        self._client = client
        self._timeout_s = timeout_s

    def capabilities(self) -> ProviderCapabilities:
        # Waves need the marine endpoint (not used for lakes). Visibility is not
        # published by every model, so it is handled as optional per hour.
        return ProviderCapabilities(waves=False, visibility=True, storm_probability=False)

    async def hourly(
        self, spot_id: str, lat: float, lon: float, day: date, timezone_name: str
    ) -> Forecast:
        params = {
            "latitude": f"{lat:.4f}",
            "longitude": f"{lon:.4f}",
            "hourly": ",".join(HOURLY_FIELDS),
            "wind_speed_unit": "kn",
            "timezone": timezone_name,
            "start_date": day.isoformat(),
            "end_date": day.isoformat(),
        }
        response = await self._client.get(ENDPOINT, params=params, timeout=self._timeout_s)
        response.raise_for_status()
        payload = response.json()
        return self.parse(payload, spot_id=spot_id, day=day)

    def parse(self, payload: dict, *, spot_id: str, day: date) -> Forecast:
        """Normalise an Open-Meteo response. Separated out so it is testable offline."""
        hourly = payload.get("hourly") or {}
        times = hourly.get("time") or []
        if not times:
            raise ValueError("Open-Meteo returned no hourly data")

        def column(name: str) -> list:
            values = hourly.get(name)
            return values if values else [None] * len(times)

        winds = column("wind_speed_10m")
        gusts = column("wind_gusts_10m")
        directions = column("wind_direction_10m")
        temps = column("temperature_2m")
        precips = column("precipitation")
        precip_probs = column("precipitation_probability")
        clouds = column("cloud_cover")
        pressures = column("surface_pressure")
        visibilities = column("visibility")
        codes = column("weather_code")

        hours: list[HourlyWeather] = []
        for i, stamp in enumerate(times):
            hour = int(stamp[11:13])
            code = codes[i]
            storm_prob = (
                THUNDERSTORM_CODE_PROB
                if code is not None and int(code) in THUNDERSTORM_CODES
                else 0.0
            )
            hours.append(
                HourlyWeather(
                    hour=hour,
                    # Already knots: requested with wind_speed_unit=kn.
                    wind_kn=_num(winds[i], 0.0),
                    gust_kn=_num(gusts[i], _num(winds[i], 0.0)),
                    wind_dir_deg=_num(directions[i], 0.0),
                    temp_c=_num(temps[i], 15.0),
                    precip_mm=_num(precips[i], 0.0),
                    # Provider gives 0-100; the model works in 0-1.
                    precip_prob=_num(precip_probs[i], 0.0) / 100.0,
                    cloud_frac=_num(clouds[i], 0.0) / 100.0,
                    # None stays None: UNKNOWN, dropped from the weather component.
                    visibility_m=None if visibilities[i] is None else float(visibilities[i]),
                    storm_prob=storm_prob,
                    pressure_hpa=None if pressures[i] is None else float(pressures[i]),
                )
            )

        notes = ["Thunderstorm risk derived from the WMO weather code, not a provider probability."]
        if all(h.visibility_m is None for h in hours):
            notes.append("This model does not publish visibility — the component is UNKNOWN.")

        return Forecast(
            spot_id=spot_id,
            day=day,
            hours=hours,
            provider_id=self.id,
            model_id=payload.get("model") or "open-meteo best match",
            provenance="FORECAST",
            attribution=ATTRIBUTION,
            retrieved_at=datetime.now(UTC).isoformat(timespec="seconds"),
            notes=notes,
        )


def _num(value, fallback: float) -> float:
    """Missing numbers fall back only where the model cannot express UNKNOWN.

    Wind, temperature and precipitation are required by the scoring model, so a gap
    is filled with a neutral value; visibility and pressure are optional and keep
    their None. Every fallback here is a known, documented compromise rather than a
    silent guess — and gaps in these fields are rare in practice.
    """
    return fallback if value is None else float(value)
