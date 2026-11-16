"""BARQ automation persists opt-in alarms, guards city APIs and due-time behavior."""
import json
from datetime import datetime
from fastapi.testclient import TestClient


def test_one_shot_alarm_fires_once_and_is_disabled(tmp_path, monkeypatch):
    from services import automation_alarms as alarm
    path=tmp_path/"alarms.json"
    monkeypatch.setattr(alarm,"_path",lambda:path)
    new=alarm.create_alarm("12:05","اختبار",False)
    called=[]
    class FakeThread:
        def __init__(self,target,args,daemon):self.fn=target;self.args=args
        def start(self):self.fn(*self.args)
    monkeypatch.setattr(alarm.threading,"Thread",FakeThread)
    now=datetime(2026,11,16,12,5)
    assert alarm.tick(now,notify=called.append)==1
    assert called==["اختبار"]
    assert alarm.tick(now,notify=called.append)==0
    assert alarm.alarms()[0]["enabled"] is False
    assert alarm.delete_alarm(new["id"]) is True


def test_daily_alarm_does_not_repeat_within_same_minute(tmp_path,monkeypatch):
    from services import automation_alarms as alarm
    monkeypatch.setattr(alarm,"_path",lambda:tmp_path/"alarms.json")
    class FakeThread:
        def __init__(self,target,args,daemon):self.fn=target;self.args=args
        def start(self):self.fn(*self.args)
    monkeypatch.setattr(alarm.threading,"Thread",FakeThread)
    a=alarm.create_alarm("07:30","صباح الخير",True)
    calls=[]
    assert alarm.tick(datetime(2026,11,16,7,30),notify=calls.append)==1
    assert alarm.tick(datetime(2026,11,16,7,30),notify=calls.append)==0
    assert alarm.tick(datetime(2026,11,17,7,30),notify=calls.append)==1
    assert calls==["صباح الخير","صباح الخير"]
    assert alarm.toggle_alarm(a["id"],False)["enabled"] is False


def test_automation_provider_payloads_are_checked_without_any_real_network(monkeypatch):
    from api_routes import automation as tools
    fake_weather={"current":{"temperature_2m":29,"apparent_temperature":31,"relative_humidity_2m":23,"wind_speed_10m":9,"weather_code":1},
                  "daily":{"temperature_2m_max":[35],"temperature_2m_min":[22]}}
    def fake_get(url):
        if "open-meteo" in url:return fake_weather
        return {"data":{"timings":{"Fajr":"05:01 (+03)","Dhuhr":"11:50 (+03)","Asr":"15:00 (+03)","Maghrib":"17:20 (+03)","Isha":"18:50 (+03)"}}}
    monkeypatch.setattr(tools,"_get_json",fake_get)
    tools._CACHE.clear()
    payload=tools.overview("riyadh")
    assert payload["city"]=="riyadh"
    assert payload["weather"]["temperature"]==29
    assert len(payload["prayers"])==5
    assert payload["prayer_source"]=="AlAdhan"
    assert payload["next_prayer"] is not None
