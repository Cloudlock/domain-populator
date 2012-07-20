import calendar
from datetime import datetime


def diff_seconds(diff):
    """
    Calculate total seconds in a timedelta.
    """
    return (diff.microseconds + (diff.seconds + diff.days *
                                 24 * 3600) * 10**6) / 10**6


def datetime_to_timestamp(dt):
    """
    Convert a datetime into a Unix timestamp.
    """
    return calendar.timegm(dt.timetuple())


def datetime_to_iso(dt):
    """
    Convert datetime to isoformat-ish string.

    These strings are mostly used in Google API entry objects.
    """
    try:
        fmt = dt.isoformat()[:-3] + 'Z'
        assert len(fmt) == 24
    except AssertionError:
        fmt = dt.isoformat() + '.000Z'
    return fmt


def iso_to_datetime(iso):
    """
    Convert isoformat-ish string to datetime.

    These strings are mostly used in Google API entry objects.
    """
    try:
        return datetime.strptime(iso[:-5], '%Y-%m-%dT%H:%M:%S')
    except ValueError: # No microsecond
        return datetime.strptime(iso[:-2], '%Y-%m-%dT%H:%M:%S')

