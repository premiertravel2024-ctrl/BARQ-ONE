"""Local automation, weather and prayer-time APIs for the BARQ ONE UI."""
from __future__ import annotations

from datetime import datetime, timedelta
import json
import re
import threading
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services import automation_alarms

router = APIRouter(prefix="/v1/automation", tags=["automation"])
# City is deliberately chosen by the user. No GPS or precise location request.
CITIES = {
    "riyadh": {"label_ar": "الرياض", "name": "Riyadh", "country": "Saudi Arabia", "lat": 24.7136, "lon": 46.6753, "timezone": "Asia/Riyadh"},
    "jeddah": {"label_ar": "جدة", "name": "Jeddah", "country": "Saudi Arabia", "lat": 21.4858, "lon": 39.1925, "timezone": "Asia/Riyadh"},
    "makkah": {"label_ar": "مكة المكرمة", "name": "Mecca", "country": "Saudi Arabia", "lat": 21.4225, "lon": 39.8262, "timezone": "Asia/Riyadh"},
    "madinah": {"label_ar": "المدينة المنورة", "name": "Medina", "country": "Saudi Arabia", "lat": 24.5247, "lon": 39.5692, "timezone": "Asia/Riyadh"},
    "dammam": {"label_ar": "الدمام", "name": "Dammam", "country": "Saudi Arabia", "lat": 26.4207, "lon": 50.0888, "timezone": "Asia/Riyadh"},
    "cairo": {"label_ar": "القاهرة", "name": "Cairo", "country": "Egypt", "lat": 30.0444, "lon": 31.2357, "timezone": "Africa/Cairo"},
}
_CACHE: dict[str, tuple[float, dict]] = {}
_LOCK = threading.Lock()
_NAMES = ("Fajr", "Dhuhr", "Asr", "Maghrib", "Isha")
_AR = {"Fajr":"الفجر", "Dhuhr":"الظهر", "Asr":"العصر", "Maghrib":"المغرب", "Isha":"العشاء"}


def _get_json(url: str) -> dict:
    req = Request(url, headers={"User-Agent":"BARQ-ONE/2.40.2", "Accept":"application/json"})
    with urlopen(req, timeout=7) as response:
        if response.status != 200:
            raise RuntimeError("Service unavailable")
        data = response.read(150000)
    result = json.loads(data)
    if not isinstance(result, dict):
        raise ValueError("Invalid provider data")
    return result


def _weather(city: dict) -> dict:
    query = urlencode({
        "latitude": city["lat"], "longitude":city["lon"],
        "current":"temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m",
        "daily":"temperature_2m_max,temperature_2m_min",
        "forecast_days":1,
        "timezone":city["timezone"],
    })
    data = _get_json("https://api.open-meteo.com/v1/forecast?" + query)
    current = data["current"]
    daily = data["daily"]
    return {
        "temperature": round(float(current["temperature_2m"])),
        "feels_like": round(float(current["apparent_temperature"])),
        "humidity": int(current["relative_humidity_2m"]),
        "wind_kmh": round(float(current["wind_speed_10m"])),
        "weather_code": int(current["weather_code"]),
        "high": round(float(daily["temperature_2m_max"][0])),
        "low": round(float(daily["temperature_2m_min"][0])),
        "source":"Open-Meteo",
    }


def _prayer_day(city: dict, date: datetime) -> list[dict]:
    query = urlencode({"city":city["name"],"country":city["country"],
                       "method":4 if city["country"] == "Saudi Arabia" else 5,"school":0})
    result = _get_json("https://api.aladhan.com/v1/timingsByCity/" + date.strftime("%d-%m-%Y") + "?" + query)
    timings = result["data"]["timings"]
    rows = []
    for key in _NAMES:
        raw = str(timings[key])
        match = re.match(r"^(\d\d):(\d\d)", raw)
        if not match:
            raise ValueError("Invalid prayer time")
        hours, minutes = int(match.group(1)), int(match.group(2))
        local = date.replace(hour=hours, minute=minutes, second=0, microsecond=0)
        rows.append({"key":key, "label":_AR[key], "time":f"{hours:02d}:{minutes:02d}", "at":local.isoformat()})
    return rows


@router.get("/overview")
def overview(city: str = "riyadh"):
    if city not in CITIES:
        raise HTTPException(400, "اختر مدينة مدعومة.")
    info = CITIES[city]
    now = datetime.now(ZoneInfo(info["timezone"]))
    key = city + ":" + now.strftime("%Y-%m-%d")
    with _LOCK:
        cached = _CACHE.get(key)
        if cached and time.monotonic() < cached[0]:
            return cached[1]
    data = {"city":city, "city_label":info["label_ar"],"timezone":info["timezone"],
            "updated_at":now.isoformat(),"weather":None,"prayers":[],"next_prayer":None,
            "errors":[],"prayer_source":"AlAdhan"}
    try:
        data["weather"] = _weather(info)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError):
        data["errors"].append("بيانات الطقس مش متاحة حاليًا.")
    try:
        today = _prayer_day(info, now)
        tomorrow = _prayer_day(info, now + timedelta(days=1))
        data["prayers"] = today
        for prayer in today + tomorrow:
            if datetime.fromisoformat(prayer["at"]) > now:
                data["next_prayer"] = prayer
                break
    except (OSError, ValueError, KeyError, TypeError, RuntimeError):
        data["errors"].append("مواقيت الصلاة مش متاحة حاليًا.")
    with _LOCK:
        _CACHE[key] = (time.monotonic() + 600, data)
        if len(_CACHE) > 20:
            _CACHE.clear()
            _CACHE[key] = (time.monotonic() + 600, data)
    return data


@router.get("/cities")
def cities():
    return {"cities":[{"id":key,**value} for key,value in CITIES.items()]}


@router.get("/alarms")
def list_alarms():
    return {"alarms":automation_alarms.alarms(), "runs_while_app_open":True}


class AlarmRequest(BaseModel):
    time: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    label: str = Field(min_length=1,max_length=70)
    repeat: bool = True


@router.post("/alarms")
def create_alarm(payload: AlarmRequest):
    try:
        return automation_alarms.create_alarm(payload.time,payload.label,payload.repeat)
    except ValueError as exc:
        raise HTTPException(400,str(exc)) from exc


class AlarmToggle(BaseModel):
    enabled: bool


@router.patch("/alarms/{alarm_id}")
def toggle_alarm(alarm_id: str, request: AlarmToggle):
    if not re.fullmatch(r"[0-9a-f]{32}", alarm_id):
        raise HTTPException(404,"المنبّه مش موجود.")
    try:
        return automation_alarms.toggle_alarm(alarm_id,request.enabled)
    except KeyError as exc:
        raise HTTPException(404,str(exc)) from exc


@router.delete("/alarms/{alarm_id}")
def remove_alarm(alarm_id: str):
    if not re.fullmatch(r"[0-9a-f]{32}", alarm_id):
        raise HTTPException(404,"المنبّه مش موجود.")
    return {"deleted":automation_alarms.delete_alarm(alarm_id)}
