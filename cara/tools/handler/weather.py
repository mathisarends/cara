from datetime import datetime
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator

_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"

_CURRENT_FIELDS = "temperature_2m,apparent_temperature,weather_code,wind_speed_10m,is_day"
_HOURLY_FIELDS = "temperature_2m,weather_code,precipitation_probability"
_HOURLY_HOURS_AHEAD = 24

# WMO weather interpretation codes, condensed to spoken German phrases.
_WEATHER_CODES: dict[int, str] = {
    0: "klar",
    1: "überwiegend klar",
    2: "teils bewölkt",
    3: "bedeckt",
    45: "neblig",
    48: "gefrierender Nebel",
    51: "leichter Nieselregen",
    53: "Nieselregen",
    55: "starker Nieselregen",
    56: "gefrierender Nieselregen",
    57: "starker gefrierender Nieselregen",
    61: "leichter Regen",
    63: "Regen",
    65: "starker Regen",
    66: "gefrierender Regen",
    67: "starker gefrierender Regen",
    71: "leichter Schneefall",
    73: "Schneefall",
    75: "starker Schneefall",
    77: "Schneegriesel",
    80: "leichte Regenschauer",
    81: "Regenschauer",
    82: "heftige Regenschauer",
    85: "leichte Schneeschauer",
    86: "starke Schneeschauer",
    95: "Gewitter",
    96: "Gewitter mit leichtem Hagel",
    99: "Gewitter mit starkem Hagel",
}


class Location(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    latitude: float
    longitude: float
    timezone: str = "Europe/Berlin"


class HourlyForecast(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)

    time: datetime
    temperature_c: float = Field(alias="temperature_2m")
    precipitation_probability: int
    description: str

    @model_validator(mode="before")
    @classmethod
    def _describe_weather_code(cls, data: Any) -> Any:
        return _with_weather_description(data)


class WeatherReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)

    location_name: str
    temperature_c: float = Field(alias="temperature_2m")
    apparent_temperature_c: float = Field(alias="apparent_temperature")
    wind_speed_kmh: float = Field(alias="wind_speed_10m")
    is_day: bool
    description: str
    hourly: list[HourlyForecast] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _describe_weather_code(cls, data: Any) -> Any:
        return _with_weather_description(data)


class OpenMeteoClient:
    """Current weather and place lookup via the keyless Open-Meteo APIs."""

    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None, timeout: float = 10.0) -> None:
        self._transport = transport
        self._timeout = timeout

    async def locate(self, query: str) -> Location | None:
        data = await self._get(
            _GEOCODING_URL,
            {"name": query, "count": 1, "language": "de", "format": "json"},
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

    async def current(self, location: Location) -> WeatherReport:
        data = await self._get(
            _FORECAST_URL,
            {
                "latitude": location.latitude,
                "longitude": location.longitude,
                "current": _CURRENT_FIELDS,
                "hourly": _HOURLY_FIELDS,
                "forecast_days": 2,
                "wind_speed_unit": "kmh",
                "timezone": location.timezone,
            },
        )
        current_time = datetime.fromisoformat(data["current"]["time"])
        hourly = _upcoming_hourly_entries(data["hourly"], after=current_time, limit=_HOURLY_HOURS_AHEAD)
        return WeatherReport.model_validate({**data["current"], "location_name": location.name, "hourly": hourly})

    async def _get(self, url: str, params: dict[str, object]) -> dict:
        async with httpx.AsyncClient(transport=self._transport, timeout=self._timeout) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()


def _with_weather_description(data: Any) -> Any:
    if isinstance(data, dict) and "weather_code" in data and "description" not in data:
        description = _WEATHER_CODES.get(data["weather_code"], "unbekannte Wetterlage")
        return {**data, "description": description}
    return data


def _upcoming_hourly_entries(hourly: dict[str, list], *, after: datetime, limit: int) -> list[dict]:
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
