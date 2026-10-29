"""End-to-end tests that drive the app with Streamlit's AppTest. Run with: pytest"""
import datetime as dt
import json
import time
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "app.py")


@pytest.fixture
def app(tmp_path, monkeypatch):
    data_file = tmp_path / "data.json"
    monkeypatch.setenv("EXTERNAL_BRAIN_DATA", str(data_file))
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    assert not at.exception
    return at, data_file


def saved(data_file):
    return json.loads(data_file.read_text())


def click(at, label):
    next(b for b in at.button if b.label == label).click().run()
    assert not at.exception


def add_tasks(at, text):
    at.text_area(key="draft").input(text).run()
    click(at, "Add")


def test_add_and_pick_today(app):
    at, f = app
    add_tasks(at, "Send the invoice\nLaundry\n\nTaxes\nCall mom")
    ids = [t["id"] for t in saved(f)["tasks"]]
    assert [t["title"] for t in saved(f)["tasks"]] == ["Send the invoice", "Laundry", "Taxes", "Call mom"]
    assert saved(f)["draft"] == ""

    # The first task picked becomes Now, even if it's lower in the list.
    # (AppTest selects pills by their visible label.)
    at.button_group(key="today_pick").set_value(["Laundry"]).run()
    at.button_group(key="today_pick").set_value(["Send the invoice", "Laundry"]).run()
    assert saved(f)["today"] == [ids[1], ids[0]]

    # A 4th pick is refused.
    at.button_group(key="today_pick").set_value(["Send the invoice", "Laundry", "Taxes", "Call mom"]).run()
    assert len(saved(f)["today"]) == 3

    at.text_input(key=f"next_{ids[1]}").input("Open the washer").run()
    assert saved(f)["tasks"][1]["next"] == "Open the washer"

    click(at, "Done")
    assert saved(f)["tasks"][1]["done"] is True
    assert saved(f)["today"][0] == ids[0]


def test_two_minute_start_opens_timer(app):
    at, f = app
    add_tasks(at, "Write report")
    at.button_group(key="today_pick").set_value(["Write report"]).run()
    click(at, "2-min start")
    assert saved(f)["timer"]["label"] == "2-min start"
    assert at.session_state["page"] == "Timer"


def test_timer_end_rings_once_and_suggests_next(app):
    at, f = app
    at.session_state["page"] = "Timer"
    at.run()
    click(at, "Focus 25 min")
    d = saved(f)
    d["timer"]["end"] = time.time() - 1
    at.session_state["data"] = d
    at.run()
    assert "Focus 25 min is done" in at.session_state["alarm"]
    labels = [b.label for b in at.button]
    assert "OK" in labels and "Break 5 min" in labels
    assert saved(f)["timer"]["notified"] is True


def test_leave_on_time_alarms(app):
    at, f = app
    at.session_state["page"] = "Timer"
    at.run()
    at.text_input(key="ev_title").input("Soccer").run()
    click(at, "Set alarms")
    ev = saved(f)["event"]
    assert ev["title"] == "Soccer" and ev["travel"] == 30 and ev["prep"] == 15
    assert [m.label for m in at.metric] == ["1 · Wrap up", "2 · Leave", "Starts"]

    # Move the event so the wrap-up time passed 5 seconds ago.
    wrap = ev["start"] - (ev["travel"] + ev["prep"]) * 60
    ev["start"] -= wrap - time.time() + 5
    d = saved(f)
    d["event"] = ev
    at.session_state["data"] = d
    at.run()
    assert at.session_state["alarm"].startswith("Time to wrap up")
    assert saved(f)["event"]["fired"] == ["wrap"]


def test_past_event_is_rejected(app):
    at, f = app
    at.session_state["page"] = "Timer"
    at.run()
    at.date_input(key="ev_date").set_value(dt.date(2020, 1, 1)).run()
    click(at, "Set alarms")
    assert at.error and "already passed" in at.error[0].value
    assert not f.exists() or saved(f)["event"] is None


def test_stuck_button_starts_its_timer(app):
    at, f = app
    at.session_state["page"] = "Stuck?"
    at.run()
    at.button_group(key="situation").set_value(1).run()  # "I'm frozen"
    click(at, "Rest 10 min")
    assert saved(f)["timer"]["kind"] == "rest"
    assert at.session_state["page"] == "Timer"
