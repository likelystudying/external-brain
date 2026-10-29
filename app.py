"""
External Brain: a small ADHD helper app built with Streamlit.

Three screens:
  Today   Add tasks, pick up to 3 for today, and write one small next step for the first one
  Timer   A visual countdown, plus "Leave on time" alarms for appointments
  Stuck?  Pick what's going on and get a short fix, with a button that starts it

Run:
  pip install -r requirements.txt
  streamlit run app.py

Data is saved to data.json next to this file (set EXTERNAL_BRAIN_DATA to change it).
Alarms ring only while the app is open in a browser tab.
"""
from __future__ import annotations

import html
import io
import json
import math
import os
import re
import struct
import time
import uuid
import wave
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import streamlit as st

DATA_FILE = Path(os.environ.get("EXTERNAL_BRAIN_DATA") or Path(__file__).with_name("data.json"))
PAGES = ["Today", "Timer", "Stuck?"]
MAX_TODAY = 3

# ---------------------------------------------------------------------------
# Wording. Edit these lists to change what the app says.
# ---------------------------------------------------------------------------

# key: (label, minutes, kind)
TIMERS = {
    "start2": ("2-min start", 2, "start"),
    "focus25": ("Focus 25 min", 25, "work"),
    "break5": ("Break 5 min", 5, "break"),
    "reward15": ("Reward 15 min", 15, "free"),
    "rest10": ("Rest 10 min", 10, "rest"),
    "phone15": ("Phone 15 min", 15, "free"),
    "cool20": ("Cool down 20 min", 20, "cool"),
    "me60": ("Me time 60 min", 60, "free"),
}
TIMER_BUTTONS = ["start2", "focus25", "break5", "reward15"]  # shown on the Timer screen

# kind: (what to say when the timer ends, timer to suggest next or None)
AFTER = {
    "start": ("Keep going? Switch to 25 minutes. Stopping here still counts.", "focus25"),
    "work": ("Nice work. Take a 5-minute break, or a reward that has an end.", "break5"),
    "break": ("Break's over. Back to your Now task.", "start2"),
    "rest": ("No choosing needed. Just do the top task on today's list.", "start2"),
    "cool": ("Reply once you feel calm.", None),
    "free": ("That's it. Put the phone down and move on.", None),
}

# What's going on -> why -> steps -> buttons.
# A button is (label, "timer", timer key) or (label, "page", page name).
SITUATIONS = [
    {
        "label": "I can't start",
        "terms": "Task paralysis · Wall of Awful",
        "why": "The task isn't a physical action yet, or you're afraid of how it will turn out.",
        "steps": [
            "Write one physical step you can start in 30 seconds.",
            "Do it for 2 minutes. You're allowed to stop after that.",
            "If you dread it, write down the outcome you fear, then do a deliberately rough version.",
        ],
        "buttons": [("2-min start", "timer", "start2"), ("Write the next step", "page", "Today")],
    },
    {
        "label": "I'm frozen",
        "terms": "ADHD shutdown · Doom pile",
        "why": "You're out of capacity. Pushing makes it worse, so stop choosing first.",
        "steps": [
            "Rest for 10 minutes without choosing anything.",
            "Then write down everything on your mind, for 10 minutes at most.",
            "Pick only 3 for today. Make one of them quick.",
        ],
        "buttons": [("Rest 10 min", "timer", "rest10"), ("Write it all down", "page", "Today")],
    },
    {
        "label": "Time disappears",
        "terms": "Time blindness · “Dopamine addiction”",
        "why": "Your sense of time is weak, and feeds with no end eat it up.",
        "steps": [
            "Start a timer before you pick up your phone.",
            "Rewards come after work, and must have an end: one video, one episode.",
            "While you work, keep the phone in another room.",
        ],
        "buttons": [("Phone 15 min", "timer", "phone15")],
    },
    {
        "label": "Waiting for an appointment",
        "terms": "Waiting mode",
        "why": "Your brain keeps guarding the appointment. Hand that job to two alarms.",
        "steps": [
            "Plan around when you leave, not when it starts.",
            "Let two alarms do the watching: one to wrap up, one to leave.",
            "Until the first alarm, work freely.",
        ],
        "buttons": [("Set a leave time", "page", "Timer")],
    },
    {
        "label": "I can't focus",
        "terms": "Understimulation · Sensory overload · Body doubling",
        "why": "Too little and too much stimulation both hurt focus.",
        "steps": [
            "Bored? Add stimulation: stand, walk, or play music without lyrics.",
            "Overloaded? Reduce it: earplugs, dimmer lights, notifications off.",
            "Can't do it alone? Work alongside someone, even on a silent call.",
        ],
        "buttons": [("Focus 25 min", "timer", "focus25")],
    },
    {
        "label": "Criticism hurts",
        "terms": "RSD (rejection sensitive dysphoria)",
        "why": "At the peak of a feeling you can't think it through. Wait first, reframe after.",
        "steps": [
            "Don't reply for 20 minutes.",
            "Read this: “They criticized the work, not my worth.”",
            "Reply once you feel calm.",
        ],
        "buttons": [("Cool down 20 min", "timer", "cool20")],
    },
    {
        "label": "I don't want to go to bed",
        "terms": "Revenge bedtime procrastination",
        "why": "If night is your only free time, going to sleep means giving it up.",
        "steps": [
            "Count back from your wake-up time to set a bedtime.",
            "Protect some me time before bed, so you don't have to steal it later.",
            "Charge your phone outside the bedroom.",
        ],
        "buttons": [("Me time 60 min", "timer", "me60")],
    },
]

MORE_TIPS = [
    ("Out of sight, out of mind", "Object permanence",
     "Keep only the things that need action where you can see them. If everything is visible, nothing stands out."),
    ("Paying extra for forgetting", "ADHD tax",
     "Automate payments, give keys and wallet a fixed spot, and check it all once a month."),
    ("Craving a quick reward", "Dopamine menu",
     "Pick 3 small rewards in advance: a glass of water, a stretch, a 5-minute walk."),
]

# ---------------------------------------------------------------------------
# Saving and loading
# ---------------------------------------------------------------------------


def load_data() -> tuple[dict, bool]:
    """Return (data, loaded_ok)."""
    data = {"tasks": [], "today": [], "draft": "", "timer": None, "event": None}
    if not DATA_FILE.exists():
        return data, True
    try:
        data.update(json.loads(DATA_FILE.read_text(encoding="utf-8")))
        return data, True
    except (OSError, json.JSONDecodeError):
        return data, False


def data() -> dict:
    return st.session_state.data


def save() -> None:
    tmp = DATA_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data(), ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(DATA_FILE)  # one atomic step, so a crash never leaves a half-written file


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def now() -> float:
    return time.time()


def user_tz():
    """The browser's time zone, so times are right even when the server runs elsewhere."""
    name = st.context.timezone
    if name:
        try:
            return ZoneInfo(name)
        except Exception:
            pass
    return datetime.now().astimezone().tzinfo


def clock(ts: float) -> str:
    return datetime.fromtimestamp(ts, user_tz()).strftime("%H:%M")


def mmss(seconds: float) -> str:
    s = max(0, math.ceil(seconds))
    return f"{s // 60}:{s % 60:02d}"


def duration(seconds: float) -> str:
    h, m = divmod(max(0, round(seconds / 60)), 60)
    return f"{h} h {m} min" if h else f"{m} min"


_MD_SPECIAL = re.compile(r"([\\`*_\[\]<>#|~$])")


def md(text: str) -> str:
    """Escape user text so st.markdown shows it exactly as typed."""
    return _MD_SPECIAL.sub(r"\\\1", text)


def task_by_id(task_id: str) -> dict | None:
    return next((t for t in data()["tasks"] if t["id"] == task_id), None)


def open_tasks() -> list[dict]:
    return [t for t in data()["tasks"] if not t["done"]]


def today_tasks() -> list[dict]:
    tasks = (task_by_id(i) for i in data()["today"])
    return [t for t in tasks if t and not t["done"]]


def focus_task() -> dict | None:
    """The Now task is simply the first of today's tasks."""
    tasks = today_tasks()
    return tasks[0] if tasks else None


def event_times(ev: dict) -> tuple[float, float, float]:
    """Return (wrap-up time, leave time, start time) as timestamps."""
    leave = ev["start"] - ev["travel"] * 60
    wrap = leave - ev["prep"] * 60
    return wrap, leave, ev["start"]


@st.cache_data
def beep_wav() -> bytes:
    """Three short beeps, generated in code so no sound file is needed."""
    rate, tone, length = 22050, 880, 0.25
    frames = bytearray()
    n_tone = int(rate * length)
    for _ in range(3):
        for n in range(n_tone):
            fade = min(1.0, n / 300, (n_tone - n) / 300)  # avoid clicks
            frames += struct.pack("<h", int(0.45 * fade * math.sin(2 * math.pi * tone * n / rate) * 32767))
        frames += b"\x00\x00" * int(rate * 0.15)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))
    return buf.getvalue()


def pie_svg(fraction: float, size: int = 220) -> str:
    """A Time Timer style disc: the red area is the time left."""
    c, r = 100, 90
    ticks = "".join(
        f'<line x1="{c + 82 * math.sin(a):.1f}" y1="{c - 82 * math.cos(a):.1f}" '
        f'x2="{c + 94 * math.sin(a):.1f}" y2="{c - 94 * math.cos(a):.1f}" '
        f'stroke="currentColor" stroke-opacity="0.45" stroke-width="2"/>'
        for a in (i * math.pi / 6 for i in range(12))
    )
    if fraction >= 0.999:
        wedge = f'<circle cx="{c}" cy="{c}" r="{r}" fill="#E5533D"/>'
    elif fraction <= 0.001:
        wedge = ""
    else:
        a = fraction * 2 * math.pi
        x, y = c + r * math.sin(a), c - r * math.cos(a)
        large = 1 if fraction > 0.5 else 0
        wedge = f'<path d="M{c} {c} L{c} {c - r} A{r} {r} 0 {large} 1 {x:.2f} {y:.2f} Z" fill="#E5533D"/>'
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 200 200" role="img" aria-label="Time left">'
            f'<circle cx="{c}" cy="{c}" r="96" fill="rgba(128,128,128,0.12)" '
            f'stroke="rgba(128,128,128,0.35)"/>{wedge}{ticks}</svg>')


# ---------------------------------------------------------------------------
# Actions. These run as button callbacks, before the page redraws.
# ---------------------------------------------------------------------------


def go(page: str) -> None:
    st.session_state.page = page


def run_action(kind: str, target: str) -> None:
    if kind == "timer":
        start_timer(target)
    else:
        go(target)


def _start(label: str, minutes: int, kind: str) -> None:
    t = now()
    data()["timer"] = {"label": label, "kind": kind, "start": t, "end": t + minutes * 60, "notified": False}
    st.session_state.pop("alarm", None)
    save()
    go("Timer")


def start_timer(key: str) -> None:
    _start(*TIMERS[key])


def start_custom() -> None:
    minutes = int(st.session_state.custom_min)
    _start(f"Timer {minutes} min", minutes, "work")


def add_five() -> None:
    timer = data()["timer"]
    if timer:
        timer["end"] = max(timer["end"], now()) + 5 * 60
        timer["notified"] = False
        save()


def stop_timer() -> None:
    data()["timer"] = None
    st.session_state.pop("alarm", None)
    save()


def dismiss_alarm() -> None:
    st.session_state.pop("alarm", None)


def save_draft() -> None:
    data()["draft"] = st.session_state.draft
    save()


def add_tasks() -> None:
    lines = [ln.strip() for ln in st.session_state.draft.splitlines() if ln.strip()]
    for line in lines:
        data()["tasks"].append({"id": uuid.uuid4().hex[:8], "title": line[:200], "next": "", "done": False})
    data()["draft"] = ""
    st.session_state.draft = ""
    save()
    if lines:
        st.toast(f"Added {len(lines)}. Now pick up to {MAX_TODAY} for today.")


def pick_today() -> None:
    """Keep today's list in the order tasks were picked, so the first pick stays Now."""
    picked = st.session_state.today_pick or []
    kept = [i for i in data()["today"] if i in picked]
    today = kept + [i for i in picked if i not in kept]
    if len(today) > MAX_TODAY:
        today = today[:MAX_TODAY]
        st.toast(f"Up to {MAX_TODAY} for today. Unpick one first.")
    data()["today"] = today
    save()


def save_next(task_id: str) -> None:
    task = task_by_id(task_id)
    if task:
        task["next"] = st.session_state[f"next_{task_id}"].strip()
        save()


def complete(task_id: str) -> None:
    task = task_by_id(task_id)
    if task:
        task["done"] = True
    data()["today"] = [i for i in data()["today"] if i != task_id]
    save()
    st.toast("Done!")


def clear_done() -> None:
    data()["tasks"] = open_tasks()
    save()


def set_event() -> None:
    s = st.session_state
    start = datetime.combine(s.ev_date, s.ev_time).replace(tzinfo=user_tz()).timestamp()
    if start <= now():
        s.ev_error = "That time has already passed. Check the date and start time."
        return
    data()["event"] = {"title": s.ev_title.strip() or "Appointment", "start": start,
                       "travel": int(s.ev_travel), "prep": int(s.ev_prep), "fired": []}
    s.pop("ev_error", None)
    save()
    st.toast("Alarms set")


def clear_event() -> None:
    data()["event"] = None
    save()


# ---------------------------------------------------------------------------
# Alarms and the status bar (refreshed every second)
# ---------------------------------------------------------------------------


def check_alarms() -> None:
    d, t = data(), now()
    message, changed = None, False

    timer = d["timer"]
    if timer and not timer["notified"] and t >= timer["end"]:
        timer["notified"] = changed = True
        message = f"{timer['label']} is done. {AFTER[timer['kind']][0]}"

    ev = d["event"]
    if ev:
        wrap, leave, _ = event_times(ev)
        for key, ts, msg in (("wrap", wrap, f"Time to wrap up. Leave at {clock(leave)}."),
                             ("leave", leave, f"Time to leave for {ev['title']}.")):
            if key not in ev["fired"] and t >= ts:
                ev["fired"].append(key)
                changed = True
                if t - ts < 180:  # stay quiet about alarms that passed while the app was closed
                    message = msg

    if changed:
        save()
    if message:
        st.session_state.alarm = message
        st.rerun()  # redraw the whole page so the alarm and the right buttons appear


@st.fragment(run_every=1)
def status_bar() -> None:
    check_alarms()
    t, lines = now(), []

    task = focus_task()
    if task and st.session_state.get("page") != "Today":  # the Today screen already shows it
        nxt = f" → {md(task['next'])}" if task["next"] else " → :orange[add a next step]"
        lines.append(f"**Now:** {md(task['title'])}{nxt}")

    timer = data()["timer"]
    if timer:
        left = timer["end"] - t
        lines.append(f"**Timer:** {timer['label']} · " + (f"**{mmss(left)}** left" if left > 0 else "done"))

    ev = data()["event"]
    if ev and t < ev["start"]:
        wrap, leave, _ = event_times(ev)
        if t < wrap:
            state = f"wrap up in {duration(wrap - t)}"
        elif t < leave:
            state = ":orange[time to wrap up]"
        else:
            state = ":red[time to leave]"
        lines.append(f"**{md(ev['title'])}:** leave at {clock(leave)} · {state}")

    if lines:
        with st.container(border=True):
            st.markdown("  \n".join(lines))


def alarm_banner() -> None:
    message = st.session_state.get("alarm")
    if message:
        st.warning(message, icon=":material/alarm:")
        st.audio(beep_wav(), format="audio/wav", autoplay=True)
        st.button("OK", on_click=dismiss_alarm, type="primary", width="stretch")


# ---------------------------------------------------------------------------
# Screens
# ---------------------------------------------------------------------------


def page_today() -> None:
    tasks = open_tasks()
    focus = focus_task()

    if focus:
        with st.container(border=True):
            st.caption("Now")
            st.markdown(f"#### {md(focus['title'])}")
            key = f"next_{focus['id']}"
            st.session_state.setdefault(key, focus["next"])
            st.text_input("Next step: something you can start in 30 seconds", key=key,
                          on_change=save_next, args=(focus["id"],),
                          placeholder="e.g. Open the laptop and open the invoice")
            with st.container(horizontal=True):
                st.button("2-min start", on_click=start_timer, args=("start2",), type="primary")
                st.button("Done", on_click=complete, args=(focus["id"],))
        rest = today_tasks()[1:]
        if rest:
            st.caption("Up next")
            st.markdown("\n".join(f"{n}. {md(t['title'])}" for n, t in enumerate(rest, 2)))
    elif tasks:
        st.info(f"Pick up to {MAX_TODAY} tasks for today. The first one you pick becomes **Now**.")
    else:
        st.info("Start by writing down what's on your mind.")

    if tasks:
        open_ids = [t["id"] for t in tasks]
        st.session_state.today_pick = [i for i in data()["today"] if i in open_ids]
        st.pills(f"Today (up to {MAX_TODAY})", options=open_ids, selection_mode="multi",
                 format_func=lambda i: task_by_id(i)["title"], key="today_pick", on_change=pick_today)
        st.caption("Tip: make one of them quick, so you get moving.")

    with st.expander("Add tasks", expanded=not tasks):
        st.session_state.setdefault("draft", data()["draft"])
        st.text_area("One per line. Stop after 10 minutes.", key="draft", on_change=save_draft,
                     height=120, placeholder="e.g.\nSend the invoice\nLaundry\nBook the dentist")
        st.button("Add", on_click=add_tasks, type="primary")

    if tasks:
        with st.expander("Finish or remove tasks"):
            for task in tasks:
                st.checkbox(task["title"], value=False, key=f"chk_{task['id']}",
                            on_change=complete, args=(task["id"],))
            n_done = len(data()["tasks"]) - len(tasks)
            if n_done:
                st.button(f"Clear {n_done} finished", on_click=clear_done)


@st.fragment(run_every=1)
def timer_face() -> None:
    timer = data()["timer"]
    if timer:
        left = max(0.0, timer["end"] - now())
        fraction = left / max(1.0, timer["end"] - timer["start"])
        big, label = mmss(left), timer["label"]
    else:
        fraction, big, label = 0.0, "—", "Pick a timer"
    st.markdown(
        '<div style="display:flex;flex-direction:column;align-items:center;gap:4px">'
        f"{pie_svg(fraction)}"
        f'<div style="font-size:3rem;font-weight:700;line-height:1.1;font-variant-numeric:tabular-nums">{big}</div>'
        f'<div style="opacity:.7">{html.escape(label)}</div></div>',
        unsafe_allow_html=True,
    )


def leave_on_time() -> None:
    st.subheader("Leave on time")
    st.caption("Plan around when you leave, not when it starts. Keep working until the first alarm.")

    ev = data()["event"]
    if "ev_date" not in st.session_state:  # fill the form from the saved event, or a sensible default
        tz = user_tz()
        if ev:
            start = datetime.fromtimestamp(ev["start"], tz)
            title, travel, prep = ev["title"], ev["travel"], ev["prep"]
        else:
            start = (datetime.now(tz) + timedelta(minutes=90)).replace(minute=0, second=0, microsecond=0)
            title, travel, prep = "", 30, 15
        st.session_state.update(ev_title=title, ev_date=start.date(), ev_time=start.time(),
                                ev_travel=travel, ev_prep=prep)

    st.text_input("What", key="ev_title", placeholder="e.g. Soccer")
    c1, c2 = st.columns(2)
    c1.date_input("Date", key="ev_date")
    c2.time_input("Starts at", key="ev_time", step=300)
    c3, c4 = st.columns(2)
    c3.number_input("Travel (min)", key="ev_travel", min_value=0, max_value=600, step=5)
    c4.number_input("Get ready (min)", key="ev_prep", min_value=0, max_value=240, step=5)
    st.button("Set alarms", on_click=set_event, type="primary", width="stretch")
    if st.session_state.get("ev_error"):
        st.error(st.session_state.ev_error)

    if ev:
        wrap, leave, start = event_times(ev)
        with st.container(border=True):
            st.markdown(f"**{md(ev['title'])}** · {datetime.fromtimestamp(start, user_tz()):%a %b %d}")
            c1, c2, c3 = st.columns(3)
            c1.metric("1 · Wrap up", clock(wrap))
            c2.metric("2 · Leave", clock(leave))
            c3.metric("Starts", clock(start))
            st.button("Clear", on_click=clear_event)


def page_timer() -> None:
    timer_face()
    timer = data()["timer"]
    finished = bool(timer) and now() >= timer["end"]
    if finished:
        st.markdown(f"**What next?** {AFTER[timer['kind']][0]}")
    with st.container(horizontal=True, horizontal_alignment="center"):
        if timer and not finished:
            st.button("+5 min", on_click=add_five)
            st.button("Stop", on_click=stop_timer, type="primary")
        elif timer:
            next_key = AFTER[timer["kind"]][1]
            if next_key:
                st.button(TIMERS[next_key][0], on_click=start_timer, args=(next_key,), type="primary")
            st.button("Close", on_click=stop_timer)
        else:
            for key in TIMER_BUTTONS:
                st.button(TIMERS[key][0], key=f"t_{key}", on_click=start_timer, args=(key,),
                          type="primary" if key == "start2" else "secondary")
    if not timer:
        with st.expander("Custom time"):
            st.number_input("Minutes", min_value=1, max_value=180, value=10, key="custom_min")
            st.button("Start", on_click=start_custom)
    st.caption("Alarms ring only while this app is open.")
    st.divider()
    leave_on_time()


def page_stuck() -> None:
    st.subheader("What's going on?")
    choice = st.pills("What's going on?", options=list(range(len(SITUATIONS))),
                      format_func=lambda i: SITUATIONS[i]["label"], key="situation",
                      label_visibility="collapsed")
    if choice is not None:
        s = SITUATIONS[choice]
        with st.container(border=True):
            st.caption(s["terms"])
            st.markdown(f"**{s['why']}**")
            st.markdown("\n".join(f"{n}. {step}" for n, step in enumerate(s["steps"], 1)))
            with st.container(horizontal=True):
                for i, (label, kind, target) in enumerate(s["buttons"]):
                    st.button(label, key=f"sit_{choice}_{i}", on_click=run_action, args=(kind, target),
                              type="primary" if i == 0 else "secondary")

    with st.expander("More tips"):
        for title, term, tip in MORE_TIPS:
            st.markdown(f"**{title}** ({term})  \n{tip}")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

st.set_page_config(page_title="External Brain", page_icon=":material/timer:", layout="centered")

if "data" not in st.session_state:
    st.session_state.data, loaded_ok = load_data()
    if not loaded_ok:
        st.session_state.load_error = True
st.session_state.setdefault("page", "Today")

st.markdown("### External Brain")
if st.session_state.pop("load_error", False):
    st.warning(f"Couldn't read {DATA_FILE.name}, so the app started empty.")

alarm_banner()
status_bar()
st.segmented_control("Screen", PAGES, key="page", required=True, label_visibility="collapsed", width="stretch")

{"Today": page_today, "Timer": page_timer, "Stuck?": page_stuck}[st.session_state.page]()
