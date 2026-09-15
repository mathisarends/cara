from datetime import datetime

import httpx

from gateway.agent_runtime.tools.handler.ports import (
    MAX_FORECAST_DAYS,
    Location,
    Weather,
    WeatherReport,
)

_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"

_CURRENT_FIELDS = (
    "temperature_2m,apparent_temperature,weather_code,wind_speed_10m,is_day"
)
_HOURLY_FIELDS = "temperature_2m,weather_code,precipitation_probability"
_DAILY_FIELDS = (
    "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"
)


class OpenMeteoWeather(Weather):
    """Current weather and place lookup via the keyless Open-Meteo APIs."""

    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._transport = transport
        self._timeout = timeout

    async def locate(self, query: str) -> Location | None:
        data = await self._get(
            _GEOCODING_URL,
            {"name": query, "count": 1, "language": "en", "format": "json"},
        )
        results = data.get("results")
        if not results:
            return None
        result = results[0]
        return Location(
            name=result["name"],
            latitude=result["latitude"],
            longitude=result["longitude"],
            timezone=result["timezone"],
        )

    async def forecast(self, location: Location, *, days: int) -> WeatherReport:
        days = max(1, min(days, MAX_FORECAST_DAYS))
        data = await self._get(
            _FORECAST_URL,
            {
                "latitude": location.latitude,
                "longitude": location.longitude,
                "current": _CURRENT_FIELDS,
                "hourly": _HOURLY_FIELDS,
                "daily": _DAILY_FIELDS,
                "forecast_days": days,
                "wind_speed_unit": "kmh",
                "timezone": location.timezone,
            },
        )
        current_time = datetime.fromisoformat(data["current"]["time"])
        hourly = _upcoming_hourly_entries(
            data["hourly"], after=current_time, limit=days * 24
        )
        return WeatherReport.model_validate(
            {
                **data["current"],
                "location_name": location.name,
                "hourly": hourly,
                "daily": _daily_entries(data["daily"]),
            }
        )

    async def _get(self, url: str, params: dict[str, object]) -> dict:
        async with httpx.AsyncClient(
            transport=self._transport, timeout=self._timeout
        ) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()


def _daily_entries(daily: dict[str, list]) -> list[dict]:
    return [
        {
            "time": day,
            "weather_code": daily["weather_code"][index],
            "temperature_2m_max": daily["temperature_2m_max"][index],
            "temperature_2m_min": daily["temperature_2m_min"][index],
            "precipitation_probability_max": daily["precipitation_probability_max"][
                index
            ],
        }
        for index, day in enumerate(daily["time"])
    ]


def _upcoming_hourly_entries(
    hourly: dict[str, list], *, after: datetime, limit: int
) -> list[dict]:
    entries: list[dict] = []
    for index, time_str in enumerate(hourly["time"]):
        if datetime.fromisoformat(time_str) < after:
            continue
        entries.append(
            {
                "time": time_str,
                "temperature_2m": hourly["temperature_2m"][index],
                "weather_code": hourly["weather_code"][index],
                "precipitation_probability": hourly["precipitation_probability"][index],
            }
        )
        if len(entries) >= limit:
            break
    return entries
