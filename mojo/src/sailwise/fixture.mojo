"""The synthetic Dervio day, as Mojo code.

The same numbers as data/fixtures/day_dervio_synthetic.json. They are duplicated
here rather than parsed, because the compute core deliberately has no I/O and no
JSON parser (ADR 0001) — writing one just to load test data would be the tail
wagging the dog. `scripts/check_fixture_sync.py` asserts the two copies agree, so
the duplication cannot drift silently.

WARNING: these numbers are INVENTED. They are a test fixture, not a forecast, and
they must never be presented as data about a real day at a real place.
"""

from .weather import HourlyWeather


fn dervio_synthetic_day() -> List[HourlyWeather]:
    """Nine hours, 09:00–17:00: a thermal that builds to 15 kn and dies by evening."""
    var hours = List[HourlyWeather]()
    #                      hour  wind  gust   dir   temp  prec  prob  cloud   vis   storm
    hours.append(HourlyWeather(9, 5.0, 7.0, 20.0, 21.0, 0.0, 0.05, 0.20, 20000.0, 0.00))
    hours.append(HourlyWeather(10, 7.0, 9.5, 25.0, 23.0, 0.0, 0.05, 0.20, 20000.0, 0.00))
    hours.append(HourlyWeather(11, 9.0, 12.0, 180.0, 25.0, 0.0, 0.05, 0.25, 20000.0, 0.00))
    hours.append(HourlyWeather(12, 12.0, 15.0, 190.0, 27.0, 0.0, 0.05, 0.30, 20000.0, 0.05))
    hours.append(HourlyWeather(13, 14.0, 17.0, 195.0, 28.0, 0.0, 0.10, 0.35, 18000.0, 0.05))
    hours.append(HourlyWeather(14, 15.0, 17.8, 195.0, 28.0, 0.0, 0.10, 0.40, 18000.0, 0.10))
    hours.append(HourlyWeather(15, 13.0, 16.0, 200.0, 27.0, 0.0, 0.10, 0.40, 18000.0, 0.10))
    hours.append(HourlyWeather(16, 10.0, 13.0, 200.0, 26.0, 0.0, 0.15, 0.45, 15000.0, 0.15))
    hours.append(HourlyWeather(17, 7.0, 9.0, 205.0, 25.0, 0.0, 0.15, 0.45, 15000.0, 0.15))
    return hours
