# External Brain

A small, phone-friendly ADHD helper. It puts the things that are hard to hold in your head on the screen: what to do now, how much time is left, and when to leave.

One Python file built with [Streamlit](https://streamlit.io). No account needed; your data stays on your computer.

> This is a self-help tool, not medical advice or treatment.

## What it does

| Screen | What you do there |
| --- | --- |
| **Today** | Write down everything on your mind, pick up to 3 tasks for today, and write one small next step for the first one. |
| **Timer** | Start a visual countdown (2-min start, 25-min focus, 5-min break, 15-min reward). Set **Leave on time** alarms for appointments: one to wrap up, one to leave. |
| **Stuck?** | Pick what's going on ("I can't start", "I'm frozen", "Criticism hurts", ...) and get 3 short steps plus a button that starts the fix. |

A bar at the top always shows your Now task, the time left on the timer, and when to leave.

## Run it

Requires Python 3.10 or newer.

```bash
git clone https://github.com/<your-username>/external-brain.git
cd external-brain
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

The app opens at http://localhost:8501. To use it on your phone, connect the phone to the same Wi-Fi and open the **Network URL** that Streamlit prints.

## Good to know

- **Alarms only ring while the app is open in a browser tab.** Browsers also block sound until you've tapped something on the page. For anything important, set a phone alarm too.
- **Your data is saved in `data.json`** next to `app.py`. It's listed in `.gitignore`, so it never gets pushed. To keep it somewhere else, set `EXTERNAL_BRAIN_DATA=/path/to/file.json`.
- **It's built for one person.** If you deploy it publicly (for example on Streamlit Community Cloud), every visitor shares the same data file, and the host can wipe it when the app restarts.

## Change the wording

All the text lives in the lists at the top of `app.py`: `TIMERS`, `AFTER`, `SITUATIONS` and `MORE_TIPS`. Edit them and reload the page.

## Run the tests

```bash
pip install pytest
pytest
```

## Project layout

```
app.py                  the whole app
requirements.txt        dependencies
.streamlit/config.toml  theme and toolbar settings
tests/test_app.py       end-to-end tests using Streamlit's AppTest
```

## License

MIT. See [LICENSE](LICENSE).
