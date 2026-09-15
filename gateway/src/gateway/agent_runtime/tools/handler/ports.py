from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_FORECAST_DAYS = 7


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


class DailyForecast(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)

    day: date = Field(alias="time")
    temperature_min_c: float = Field(alias="temperature_2m_min")
    temperature_max_c: float = Field(alias="temperature_2m_max")
    precipitation_probability: int = Field(alias="precipitation_probability_max")
    description: str

    @model_validator(mode="before")
    @classmethod
    def _describe_weather_code(cls, data: Any) -> Any:
        return _with_weather_description(data)


class WeatherReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)

    location_name: str
    observed_at: datetime = Field(alias="time")
    temperature_c: float = Field(alias="temperature_2m")
    apparent_temperature_c: float = Field(alias="apparent_temperature")
    wind_speed_kmh: float = Field(alias="wind_speed_10m")
    is_day: bool
    description: str
    hourly: list[HourlyForecast] = Field(default_factory=list)
    daily: list[DailyForecast] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _describe_weather_code(cls, data: Any) -> Any:
        return _with_weather_description(data)


class Weather(ABC):
    @abstractmethod
    async def locate(self, query: str) -> Location | None: ...

    @abstractmethod
    async def forecast(self, location: Location, *, days: int) -> WeatherReport: ...


class LocationLookup(ABC):
    @abstractmethod
    async def current(self) -> Location: ...


class SearchResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    title: str
    url: str
    content: str


class SearchResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    results: list[SearchResult] = Field(default_factory=list)
    answer: str | None = None

    def summary(self) -> str:
        if self.answer is None and not self.results:
            return "No results found."
        parts = [self.answer] if self.answer else []
        parts.extend(
            f"{result.title} ({result.url}): {result.content}"
            for result in self.results
        )
        return "\n\n".join(parts)


class WebSearch(ABC):
    @abstractmethod
    async def search(self, query: str, *, max_results: int = 5) -> SearchResponse: ...


@dataclass(frozen=True, slots=True)
class RemindOnce:
    when: datetime


@dataclass(frozen=True, slots=True)
class RemindEvery:
    seconds: float


@dataclass(frozen=True, slots=True)
class RemindOnCron:
    expression: str
    timezone: str


type ReminderSchedule = RemindOnce | RemindEvery | RemindOnCron


@dataclass(frozen=True, slots=True)
class Reminder:
    id: UUID
    instruction: str
    schedule: ReminderSchedule
    next_run_at: datetime
    name: str | None = None


class Reminders(ABC):
    """Scheduled reminders for the conversation the agent is currently in.

    Implementations are bound to one session and turn, so the agent can only
    ever reach the reminders of the conversation it is running in.
    """

    @abstractmethod
    async def list(self) -> tuple[Reminder, ...]: ...

    @abstractmethod
    async def create(
        self,
        *,
        instruction: str,
        schedule: ReminderSchedule,
        name: str | None = None,
    ) -> Reminder: ...

    @abstractmethod
    async def update(
        self,
        reminder_id: UUID,
        *,
        instruction: str,
        schedule: ReminderSchedule,
        name: str | None = None,
    ) -> Reminder: ...

    @abstractmethod
    async def delete(self, reminder_id: UUID) -> None: ...


# WMO weather interpretation codes, condensed to spoken English phrases.
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


def _with_weather_description(data: Any) -> Any:
    if isinstance(data, dict) and "weather_code" in data and "description" not in data:
        description = _WEATHER_CODES.get(
            data["weather_code"], "unknown weather condition"
        )
        return {**data, "description": description}
    return data
