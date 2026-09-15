from datetime import datetime

import httpx

from cara_tools.weather.models import (
    MAX_FORECAST_DAYS,
    DailyForecast,
    HourlyForecast,
    Location,
    OpenMeteoDaily,
    OpenMeteoForecastResponse,
    OpenMeteoGeocodingResponse,
    OpenMeteoHourly,
    WeatherReport,
    weather_description,
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


class OpenMeteoWeather:
    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._transport = transport
        self._timeout = timeout

    async def locate(self, query: str) -> Location | None:
        response = await self._get(
            _GEOCODING_URL,
            {"name": query, "count": 1, "language": "en", "format": "json"},
        )
        payload = OpenMeteoGeocodingResponse.model_validate(response)
        if not payload.results:
            return None
        place = payload.results[0]
        return Location(
            name=place.name,
            latitude=place.latitude,
            longitude=place.longitude,
            timezone=place.timezone,
        )

    async def forecast(self, location: Location, *, days: int) -> WeatherReport:
        forecast_days = max(1, min(days, MAX_FORECAST_DAYS))
        response = await self._get(
            _FORECAST_URL,
            {
                "latitude": location.latitude,
                "longitude": location.longitude,
                "current": _CURRENT_FIELDS,
                "hourly": _HOURLY_FIELDS,
                "daily": _DAILY_FIELDS,
                "forecast_days": forecast_days,
                "wind_speed_unit": "kmh",
                "timezone": location.timezone,
            },
        )
        payload = OpenMeteoForecastResponse.model_validate(response)
        current = payload.current
        return WeatherReport(
            location_name=location.name,
            observed_at=current.time,
            temperature_c=current.temperature_2m,
            apparent_temperature_c=current.apparent_temperature,
            wind_speed_kmh=current.wind_speed_10m,
            is_day=current.is_day,
            description=weather_description(current.weather_code),
            hourly=_upcoming_hourly(payload.hourly, after=current.time),
            daily=_daily_forecasts(payload.daily),
        )

    async def _get(
        self,
        url: str,
        params: dict[str, str | int | float],
    ) -> object:
        async with httpx.AsyncClient(
            transport=self._transport, timeout=self._timeout
        ) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()


def _upcoming_hourly(
    payload: OpenMeteoHourly, *, after: datetime
) -> tuple[HourlyForecast, ...]:
    forecasts = (
        HourlyForecast(
            time=time,
            temperature_c=payload.temperature_2m[index],
            precipitation_probability=payload.precipitation_probability[index],
            description=weather_description(payload.weather_code[index]),
        )
        for index, time in enumerate(payload.time)
        if time >= after
    )
    return tuple(forecasts)


def _daily_forecasts(payload: OpenMeteoDaily) -> tuple[DailyForecast, ...]:
    return tuple(
        DailyForecast(
            day=day,
            temperature_min_c=payload.temperature_2m_min[index],
            temperature_max_c=payload.temperature_2m_max[index],
            precipitation_probability=payload.precipitation_probability_max[index],
            description=weather_description(payload.weather_code[index]),
        )
        for index, day in enumerate(payload.time)
    )
