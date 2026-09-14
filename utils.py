from datetime import datetime, date, time, timedelta
from config import TIMEZONE, WORK_START_HOUR, WORK_END_HOUR, TIME_STEP_MINUTES, MIN_BOOKING_DAYS

def now_local():
    return datetime.now(TIMEZONE)

def allowed_date(d: date) -> bool:
    return d.weekday() < 5

def min_pickup_date():
    return now_local().date() + timedelta(days=MIN_BOOKING_DAYS)

def valid_pickup_date(d: date) -> bool:
    return allowed_date(d) and d >= min_pickup_date()

def time_options():
    result = []
    cur = time(WORK_START_HOUR, 0)
    end = time(WORK_END_HOUR, 0)
    while cur <= end:
        result.append(cur)
        minutes = cur.hour * 60 + cur.minute + TIME_STEP_MINUTES
        cur = time(minutes // 60, minutes % 60)
    return result

def parse_date(text: str):
    try:
        return datetime.strptime(text.strip(), "%d.%m.%Y").date()
    except ValueError:
        return None

def dt_iso(d: date, t: time):
    return datetime.combine(d, t, tzinfo=TIMEZONE).isoformat()

def fmt_iso(value: str):
    dt = datetime.fromisoformat(value)
    return dt.astimezone(TIMEZONE).strftime("%d.%m.%Y о %H:%M")

def booking_period_valid(pickup_d, pickup_t, return_d, return_t):
    pickup = datetime.combine(pickup_d, pickup_t)
    ret = datetime.combine(return_d, return_t)
    return ret > pickup

def next_workdays(start: date, count=14):
    dates = []
    d = start
    for _ in range(count):
        if valid_pickup_date(d):
            dates.append(d)
        d += timedelta(days=1)
    return dates
