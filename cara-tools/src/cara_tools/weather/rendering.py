from collections.abc import Sequence
from datetime import date, timedelta

from cara_tools.weather.models import (
    DailyForecast,
    HourlyForecast,
    WeatherPeriod,
    WeatherReport,
)

_RAIN_THRESHOLD = 30
_HOURLY_STEP = 2
_HOURLY_COUNT = 4


def render_weather_report(
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


def _hours_for(
    report: WeatherReport, period: WeatherPeriod
) -> tuple[HourlyForecast, ...]:
    if period is WeatherPeriod.NOW:
        return report.hourly[: _HOURLY_COUNT * _HOURLY_STEP : _HOURLY_STEP]
    target = _target_day(report.observed_at.date(), period)
    return tuple(hour for hour in report.hourly if hour.time.date() == target)


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
        f"{hour.time:%H:%M} {round(hour.temperature_c)} °C "
        f"{hour.description.lower()}"
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
