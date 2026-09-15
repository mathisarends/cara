from datetime import datetime

from cara_tools.weather.models import HourlyForecast, WeatherPeriod, WeatherReport
from cara_tools.weather.rendering import render_weather_report


def test_rendering_includes_hourly_rain_forecast() -> None:
    report = WeatherReport(
        location_name="Berlin",
        observed_at=datetime(2026, 7, 21, 13, 0),
        temperature_c=20,
        apparent_temperature_c=20,
        wind_speed_kmh=5,
        is_day=True,
        description="clear",
        hourly=(
            HourlyForecast(
                time=datetime(2026, 7, 21, 14),
                temperature_c=21,
                precipitation_probability=60,
                description="light rain",
            ),
        ),
    )

    rendered = render_weather_report(report, WeatherPeriod.NOW, 3)

    assert "14:00 21 °C light rain, 60% rain" in rendered
    assert rendered.endswith("Rain likely from 14:00 (60%).")
