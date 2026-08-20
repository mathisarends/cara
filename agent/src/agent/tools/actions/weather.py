from agenttoolkit import Inject, Tools
from pydantic import Field

from agent.tools.handler import LocationLookup, Weather, WeatherReport
from agent.tools.params import ToolParams


class WeatherParams(ToolParams):
    location: str | None = Field(
        default=None,
        description=(
            "City or place to look up the weather for, e.g. 'München'. "
            "Omit this to use the user's current location."
        ),
    )


def register_weather_tools(tools: Tools) -> None:
    @tools.action(
        description=(
            "Look up the weather for the current location or a given "
            "place. Only use params.location when a specific place is "
            "explicitly asked about."
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
        report = await weather_client.current(location)
        return _render_weather_report(report)


def _render_weather_report(report: WeatherReport) -> str:
    parts = [f"**{round(report.temperature_c)} °C**"]
    if abs(report.temperature_c - report.apparent_temperature_c) >= 2:
        parts.append(f"feels like {round(report.apparent_temperature_c)} °C")
    parts.append(report.description)
    parts.append(f"Wind {round(report.wind_speed_kmh)} km/h")
    summary = f"## Weather in {report.location_name}\n\n" + ", ".join(parts) + "."

    if not report.hourly:
        return summary

    rows = (
        f"| {hour.time:%H:%M} | {hour.description} | {round(hour.temperature_c)} °C | "
        f"{hour.precipitation_probability}% |"
        for hour in report.hourly
    )
    table = "\n".join(
        ["| Time | Weather | Temp | Rain |", "| --- | --- | --- | --- |", *rows]
    )
    return f"{summary}\n\n{table}"
