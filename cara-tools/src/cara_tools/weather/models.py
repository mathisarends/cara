from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

MAX_FORECAST_DAYS = 7


class WeatherPeriod(StrEnum):
    NOW = "now"
    TODAY = "today"
    TOMORROW = "tomorrow"
    DAYS = "days"


class WeatherParams(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    location: str | None = Field(
        default=None,
        description=(
            "City or place to look up. Omit only when the user's current "
            "approximate location should be inferred from the public IP."
        ),
    )
    period: WeatherPeriod = Field(
        default=WeatherPeriod.NOW,
        description="Forecast period: now, today, tomorrow, or days.",
    )
    days: int = Field(
        default=3,
        ge=1,
        le=MAX_FORECAST_DAYS,
        description="Number of days when period is days.",
    )


class Location(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    latitude: float
    longitude: float
    timezone: str


class HourlyForecast(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    time: datetime
    temperature_c: float
    precipitation_probability: int
    description: str


class DailyForecast(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    day: date
    temperature_min_c: float
    temperature_max_c: float
    precipitation_probability: int
    description: str


class WeatherReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    location_name: str
    observed_at: datetime
    temperature_c: float
    apparent_temperature_c: float
    wind_speed_kmh: float
    is_day: bool
    description: str
    hourly: tuple[HourlyForecast, ...] = ()
    daily: tuple[DailyForecast, ...] = ()


class OpenMeteoCurrent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    time: datetime
    temperature_2m: float
    apparent_temperature: float
    weather_code: int
    wind_speed_10m: float
    is_day: bool


class OpenMeteoHourly(BaseModel):
    model_config = ConfigDict(extra="ignore")

    time: list[datetime]
    temperature_2m: list[float]
    weather_code: list[int]
    precipitation_probability: list[int]

    @model_validator(mode="after")
    def _matching_lengths(self) -> "OpenMeteoHourly":
        lengths = {
            len(self.time),
            len(self.temperature_2m),
            len(self.weather_code),
            len(self.precipitation_probability),
        }
        if len(lengths) != 1:
            raise ValueError("Open-Meteo hourly arrays must have matching lengths")
        return self


class OpenMeteoDaily(BaseModel):
    model_config = ConfigDict(extra="ignore")

    time: list[date]
    weather_code: list[int]
    temperature_2m_max: list[float]
    temperature_2m_min: list[float]
    precipitation_probability_max: list[int]

    @model_validator(mode="after")
    def _matching_lengths(self) -> "OpenMeteoDaily":
        lengths = {
            len(self.time),
            len(self.weather_code),
            len(self.temperature_2m_max),
            len(self.temperature_2m_min),
            len(self.precipitation_probability_max),
        }
        if len(lengths) != 1:
            raise ValueError("Open-Meteo daily arrays must have matching lengths")
        return self


class OpenMeteoForecastResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    current: OpenMeteoCurrent
    hourly: OpenMeteoHourly
    daily: OpenMeteoDaily


class OpenMeteoPlace(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    latitude: float
    longitude: float
    timezone: str


class OpenMeteoGeocodingResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    results: list[OpenMeteoPlace] = Field(default_factory=list)


class IpLocationTimezone(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str


class IpLocationSuccess(BaseModel):
    model_config = ConfigDict(extra="ignore")

    success: Literal[True]
    city: str
    latitude: float
    longitude: float
    timezone: IpLocationTimezone


class IpLocationFailure(BaseModel):
    model_config = ConfigDict(extra="ignore")

    success: Literal[False]
    message: str


type IpLocationResponse = Annotated[
    IpLocationSuccess | IpLocationFailure,
    Field(discriminator="success"),
]

IP_LOCATION_RESPONSE_ADAPTER = TypeAdapter(IpLocationResponse)


_WEATHER_CODES: dict[int, str] = {
    0: "clear",
    1: "mostly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "foggy",
    48: "freezing fog",
    51: "light drizzle",
    53: "drizzle",
    55: "heavy drizzle",
    56: "freezing drizzle",
    57: "heavy freezing drizzle",
    61: "light rain",
    63: "rain",
    65: "heavy rain",
    66: "freezing rain",
    67: "heavy freezing rain",
    71: "light snow",
    73: "snow",
    75: "heavy snow",
    77: "snow grains",
    80: "light rain showers",
    81: "rain showers",
    82: "violent rain showers",
    85: "light snow showers",
    86: "heavy snow showers",
    95: "thunderstorm",
    96: "thunderstorm with light hail",
    99: "thunderstorm with heavy hail",
}


def weather_description(code: int) -> str:
    return _WEATHER_CODES.get(code, "unknown weather condition")
