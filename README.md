# External Brain

A small ADHD helper that runs in your browser. It puts the things that are hard to hold in your head on the screen: what to do now, how much time is left, and when to leave.

**Open it:** https://likelystudying.github.io/external-brain/

> This is a self-help tool, not medical advice or treatment.

## What it does

| Screen | What you do there |
| --- | --- |
| **Today** | Write down everything on your mind, put up to 3 tasks on today, and write one small next step for the first one (your **Now** task). |
| **Timer** | Start a visual countdown: 2-min start, 25-min focus, 5-min break, 15-min reward, or a custom time. Set **Leave on time** alarms for appointments: one to wrap up, one to leave. |
| **Stuck?** | Pick what's going on ("I can't start", "I'm frozen", "Criticism hurts", ...) and get 3 short steps plus a button that starts the fix. |

A strip at the top shows the running timer and when to leave, whichever screen you're on.

Single static page (`index.html`), no build step and nothing to install. Data is stored in the browser's localStorage, so it does not sync between devices; use **Backup and restore** in the footer to move data.

## Good to know

- **Alarms ring only while the page is open in a tab.** Tap anything on the page once so the browser allows sound. **Turn on notifications** in the footer to also get a system notification while the tab is in the background. Some phones only allow notifications for sites added to the home screen.
- For anything important, set a phone alarm too.
- To use it offline, download `index.html` and open it in your browser.

## Change the wording

All the text is in the lists near the top of the script in `index.html`: `TIMERS`, `AFTER`, `SITUATIONS` and `MORE_TIPS`.

## Publish with GitHub Pages (once)

In the repo, go to **Settings → Pages**. Under **Build and deployment**, set **Source** to **Deploy from a branch**, choose **main** and **/ (root)**, and click **Save**. After a minute or two the app is live at the link above.

## Earlier Python version

The first version was a Streamlit app. It's in the git history at commit `142d968`.

## License

MIT. See [LICENSE](LICENSE).
