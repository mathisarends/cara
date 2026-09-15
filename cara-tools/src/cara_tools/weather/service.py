from cara_tools.weather.client import OpenMeteoWeather
from cara_tools.weather.location import IpLocationLookup
from cara_tools.weather.models import WeatherPeriod
from cara_tools.weather.rendering import render_weather_report


async def weather_report(
    location: str | None,
    period: WeatherPeriod,
    days: int,
) -> str:
    weather = OpenMeteoWeather()
    if location:
        resolved_location = await weather.locate(location)
        if resolved_location is None:
            return f"No place named '{location}' was found."
    else:
        location_lookup = IpLocationLookup()
        resolved_location = await location_lookup.current()
    report = await weather.forecast(
        resolved_location,
        days=_required_days(period, days),
    )
    return render_weather_report(report, period, days)


def _required_days(period: WeatherPeriod, days: int) -> int:
    match period:
        case WeatherPeriod.NOW | WeatherPeriod.TODAY:
            return 1
        case WeatherPeriod.TOMORROW:
            return 2
        case WeatherPeriod.DAYS:
            return days
