"""Small summary statistics over the sensor readings.

Plain functions over a list of numbers. Nothing here knows anything about the
rest of the project, which makes it the easiest place to contribute, to
review, and to write a test against.
"""


def mean(values):
    """Arithmetic mean, rounded to two places."""
    if not values:
        raise ValueError("mean of an empty list")
    return round(sum(values) / len(values), 2)


def median(values):
    """Middle value, rounded to two places."""
    if not values:
        raise ValueError("median of an empty list")
    ordered = sorted(values)
    return round(ordered[len(ordered) // 2], 2)


def spread(values):
    """Difference between the largest and smallest value."""
    if not values:
        raise ValueError("spread of an empty list")
    return round(max(values) - min(values), 2)


def summarise(values):
    """All three, as a dict."""
    return {"mean": mean(values),
            "median": median(values),
            "spread": spread(values)}


if __name__ == "__main__":
    import csv
    import io
    import os

    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(os.path.dirname(here), "data", "sensors.csv")
    with io.open(path, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))

    for column in ("temperature_c", "humidity_pct", "soil_moisture_pct"):
        numbers = [float(r[column]) for r in rows]
        print("%-20s %s" % (column, summarise(numbers)))
