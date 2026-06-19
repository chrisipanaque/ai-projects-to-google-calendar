import re
from datetime import datetime, timedelta

from zoneinfo import ZoneInfo


def get_timezone(config):
    name = config.get("timezone")
    if name:
        try:
            return ZoneInfo(name)
        except (KeyError, TypeError):
            pass
    return datetime.now().astimezone().tzinfo


def floor_to_half_hour(dt):
    minute = dt.minute
    return dt.replace(minute=(minute // 30) * 30, second=0, microsecond=0)


def ceil_to_half_hour(dt):
    minute = dt.minute
    if minute == 0 and dt.second == 0 and dt.microsecond == 0:
        return dt
    result = ((minute + 29) // 30) * 30
    if result == 60:
        return dt.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    return dt.replace(minute=result, second=0, microsecond=0)


def epoch_ms_to_dt(epoch_ms, tz=None):
    dt = datetime.fromtimestamp(epoch_ms / 1000)
    if tz:
        return dt.astimezone(tz)
    return dt


def has_date_component(value):
    return "-" in value


def parse_time_or_datetime(value, tz):
    if has_date_component(value):
        if "T" in value:
            dt = datetime.fromisoformat(value)
        else:
            dt = datetime.strptime(value, "%Y-%m-%d %H:%M")
        return dt.replace(tzinfo=tz) if not dt.tzinfo else dt.astimezone(tz)
    m = re.match(r"^(\d{1,2}):(\d{2})$", value.strip())
    if not m:
        raise ValueError(f"Invalid time format: '{value}' — use HH:MM or YYYY-MM-DD HH:MM")
    hour, minute = int(m.group(1)), int(m.group(2))
    now = datetime.now(tz)
    return now.replace(hour=hour, minute=minute, second=0, microsecond=0)


def resolve_end(start_dt, end_value, tz):
    end_dt = parse_time_or_datetime(end_value, tz)
    if not has_date_component(end_value) and end_dt <= start_dt:
        end_dt += timedelta(days=1)
    return end_dt
