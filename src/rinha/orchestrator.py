from __future__ import annotations

import asyncio
import calendar
import json
import re
from datetime import date, timedelta

SLOTS_PER_DAY = [
    "9:00 AM", "9:15 AM", "9:30 AM", "9:45 AM",
    "10:00 AM", "10:15 AM", "10:30 AM", "10:45 AM",
    "11:00 AM", "11:15 AM", "11:30 AM", "11:45 AM",
    "12:00 PM", "12:15 PM", "12:30 PM", "12:45 PM",
    "4:00 PM", "4:15 PM", "4:30 PM", "4:45 PM",
    "5:00 PM", "5:15 PM", "5:30 PM", "5:45 PM",
    "6:00 PM", "6:15 PM", "6:30 PM", "6:45 PM",
]

BOOKED: dict[str, dict[str, list[str]]] = {}

_HI_KEYWORDS = {"hai", "hain", "kya", "mein", "main", "aap", "ka", "ke", "ki",
                "hoga", "hogee", "nahi", "mujhe", "mere", "hum", "hamara", "apna",
                "karna", "kar", "dijiye", "batao", "bol", "sun", "suno", "theek",
                "achha", "accha", "sahi", "galat", "dawai", "doctor", "daktar",
                "dard", "bukhar", "khansi", "sardi", "pet", "naam", "chahiye",
                "ho", "toh", "bhi", "de", "do", "dena", "le", "lo", "lena",
                "kab", "kaise", "kitne", "subah", "shaam", "kal", "aaj"}
_KN_KEYWORDS = {"ide", "illa", "madthira", "aagalla", "barutte", "beku", "beda",
                "gothilla", "gothu", "hogu", "hogi", "banni", "koodi",
                "kelasa", "swalpa", "chennagide", "chennagilla", "nimma", "nanna",
                "nimage", "eshtu", "yaake", "yaava", "yelli", "aagide", "aagilla",
                "hogi", "mathadi", "keli", "helu", "hosa", "hale", "dina",
                "vaidya", "aaspatre", "novu", "jvara", "kemmu", "negedi", "hotte"}


def detect_language(text: str) -> str:
    words = set(text.lower().split())
    hi = len(words & _HI_KEYWORDS)
    kn = len(words & _KN_KEYWORDS)
    if kn > hi:
        return "kn"
    elif hi > kn and hi >= 2:
        return "hi"
    return "en"


def _parse_date(s: str) -> str:
    s = s.strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        try:
            date.fromisoformat(s)
            return s
        except ValueError:
            pass
    today = date.today()
    s_lower = s.lower()
    if s_lower in ("today", "aaj", "indu", "ajj"):
        return today.isoformat()
    if s_lower in ("tomorrow", "kal", "naale", "kalg"):
        return (today + timedelta(days=1)).isoformat()
    days = {d.lower(): i for i, d in enumerate(calendar.day_name)}
    if s_lower in days:
        offset = (days[s_lower] - today.weekday()) % 7
        return (today + timedelta(days=offset if offset > 0 else 7)).isoformat()
    return today.isoformat()


def parse_booking_intent(text: str) -> dict | None:
    name = None
    m = re.search(
        r"(?:naam|name|i am|my name is)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
        text, re.I)
    if not m:
        m = re.search(r"(?:mera naam|myname)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", text, re.I)
    if m:
        name = m.group(1)

    phone = None
    m = re.search(r"(\d{10})", text)
    if m:
        phone = m.group(1)

    date_str = "tomorrow"
    m = re.search(r"(?:kal|tomorrow|aaj|today|202[0-9]-\d{2}-\d{2})", text, re.I)
    if m:
        date_str = m.group(0).lower()
    parsed_date = _parse_date(date_str)

    time_str = "10:00 AM"
    m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(AM|PM|baje|ghante)", text, re.I)
    if m:
        hour = int(m.group(1))
        ampm = m.group(2) or m.group(3) or ""
        if "pm" in ampm.lower() and hour < 12:
            hour += 12
        if hour > 12 or "AM" in ampm.upper():
            am_str = "AM"
        elif hour >= 12 or "PM" in ampm.upper():
            am_str = "PM"
        else:
            am_str = "AM" if hour < 12 else "PM"
        hour_12 = hour if hour <= 12 else hour - 12
        if hour_12 == 0:
            hour_12 = 12
        time_str = f"{hour_12}:00 {am_str}"

    reason = "Checkup"
    m = re.search(r"(?:reason|for|ke liye|ka|ki)\s+(.+)", text, re.I)
    if m and len(m.group(1)) < 30:
        reason = m.group(1).strip()

    if name or phone:
        return {
            "name": name or "Patient",
            "phone": phone or "N/A",
            "date": parsed_date,
            "time": time_str,
            "reason": reason,
        }
    return None


def book(data: dict) -> str:
    dt = data["date"]
    tm = data["time"]
    name = data["name"]
    phone = data["phone"]
    reason = data["reason"]
    BOOKED.setdefault(dt, {}).setdefault(tm, []).append(
        f"{name} ({phone}): {reason}")
    print(f"[booking] {name} ({phone}) on {dt} at {tm}")
    return f"Booked: {name} on {dt} at {tm}"
