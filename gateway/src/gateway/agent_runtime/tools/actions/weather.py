from collections.abc import Sequence
from datetime import date, timedelta
from enum import StrEnum

from agenttoolkit import Inject, Tools
from pydantic import Field

from agent.tools.params import ToolParams
from gateway.agent_runtime.tools.handler import (
    MAX_FORECAST_DAYS,
    DailyForecast,
    HourlyForecast,
    LocationLookup,
    Weather,
    WeatherReport,
)

_RAIN_THRESHOLD = 30
_HOURLY_STEP = 2
_HOURLY_COUNT = 4


class WeatherPeriod(StrEnum):
    NOW = "now"
    TODAY = "today"
    TOMORROW = "tomorrow"
    DAYS = "days"


class WeatherParams(ToolParams):
    location: str | None = Field(
        default=None,
        description=(
            "City or place to look up the weather for, e.g. 'München'. "
            "Omit this to use the user's current location."
        ),
    )
    period: WeatherPeriod = Field(
        default=WeatherPeriod.NOW,
        description=(
            "Which stretch of time to report on: 'now' for current conditions "
            "and the next few hours, 'today' or 'tomorrow' for that day hour by "
            "hour, 'days' for a multi-day outlook sized by params.days."
        ),
    )
    days: int = Field(
        default=3,
        ge=1,
        le=MAX_FORECAST_DAYS,
        description="Number of days to summarise when params.period is 'days'.",
    )


def register_weather_tools(tools: Tools) -> None:
    @tools.tool(
        description=(
            "Look up the weather for the current location or a given place, "
            "either right now, for a whole day, or as a multi-day outlook. "
            "Only use params.location when a specific place is explicitly "
            "asked about."
        ),
        params=WeatherParams,
    )
    async def weather_report(
        params: WeatherParams,
        location_client: Inject[LocationLookup],
        weather_client: Inject[Weather],
    ) -> str:
        if params.location:
            location = await weather_client.locate(params.location)
            if location is None:
                return f"No place named '{params.location}' was found."
        else:
            location = await location_client.current()
        report = await weather_client.forecast(
            location, days=_required_days(params.period, params.days)
        )
        return _render_weather_report(report, params.period, params.days)


def _render_weather_report(
    report: WeatherReport, period: WeatherPeriod, days: int
) -> str:
    if period is WeatherPeriod.DAYS:
        return "\n".join([_render_now(report), _render_daily(report.daily[:days])])

    hourly = _hours_for(report, period)
    lines = [_render_now(report)]
    if hourly:
        lines.append(_render_hourly(hourly, period))
        lines.append(_render_rain(hourly))
    return "\n".join(lines)


def _required_days(period: WeatherPeriod, days: int) -> int:
    match period:
        case WeatherPeriod.NOW | WeatherPeriod.TODAY:
            return 1
        case WeatherPeriod.TOMORROW:
            return 2
        case WeatherPeriod.DAYS:
            return days


def _hours_for(report: WeatherReport, period: WeatherPeriod) -> list[HourlyForecast]:
    if period is WeatherPeriod.NOW:
        return list(report.hourly[: _HOURLY_COUNT * _HOURLY_STEP : _HOURLY_STEP])
    target = _target_day(report.observed_at.date(), period)
    return [hour for hour in report.hourly if hour.time.date() == target]


def _target_day(today: date, period: WeatherPeriod) -> date:
    return today + timedelta(days=1) if period is WeatherPeriod.TOMORROW else today


def _render_now(report: WeatherReport) -> str:
    text = f"Weather in {report.location_name}: {round(report.temperature_c)} °C"
    if abs(report.temperature_c - report.apparent_temperature_c) >= 2:
        text += f" (feels like {round(report.apparent_temperature_c)} °C)"
    wind = round(report.wind_speed_kmh)
    return f"{text}, {report.description.lower()}, wind {wind} km/h."


def _render_hourly(hourly: Sequence[HourlyForecast], period: WeatherPeriod) -> str:
    picked = hourly if period is WeatherPeriod.NOW else hourly[::_HOURLY_STEP]
    entries = (
        f"{hour.time:%H:%M} {round(hour.temperature_c)} °C {hour.description.lower()}"
        + (
            f", {hour.precipitation_probability}% rain"
            if hour.precipitation_probability >= _RAIN_THRESHOLD
            else ""
        )
        for hour in picked
    )
    return f"{_hourly_label(period)}: " + "; ".join(entries)


def _hourly_label(period: WeatherPeriod) -> str:
    match period:
        case WeatherPeriod.TODAY:
            return "Today"
        case WeatherPeriod.TOMORROW:
            return "Tomorrow"
        case _:
            return "Next hours"


def _render_daily(daily: Sequence[DailyForecast]) -> str:
    entries = (
        f"{day.day:%a} {round(day.temperature_min_c)}–"
        f"{round(day.temperature_max_c)} °C {day.description.lower()}"
        + (
            f", {day.precipitation_probability}% rain"
            if day.precipitation_probability >= _RAIN_THRESHOLD
            else ""
        )
        for day in daily
    )
    return "Outlook: " + "; ".join(entries)


def _render_rain(hourly: Sequence[HourlyForecast]) -> str:
    wet = [hour for hour in hourly if hour.precipitation_probability >= _RAIN_THRESHOLD]
    if not wet:
        return "No rain expected."
    first = wet[0]
    return f"Rain likely from {first.time:%H:%M} ({first.precipitation_probability}%)."
