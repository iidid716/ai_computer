# Mommy Desktop Assistant 2.0 (Windows)

## Included
- Desktop companion window with black-haired anime artwork
- Live clock and date
- Monthly calendar
- Add/remove scheduled reminders
- Reminder popup messages
- Best-effort Windows fullscreen detection
- Option to wait until fullscreen ends, or allow reminders over fullscreen
- Optional launch at Windows sign-in
- OpenAI API chat

## Setup in VS Code (Windows PowerShell)

1. Extract the ZIP and open the `mommy_desktop_assistant_2` folder in VS Code.
2. In the VS Code terminal run:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

3. Copy `.env.example` to a new file named `.env`.
4. Put your own API key in `.env`:

```env
OPENAI_API_KEY=your_api_key_here
OPENAI_MODEL=gpt-5
```

Never share `.env` or commit it to GitHub. API use may cost money depending on your account and model access.

5. Start the app:

```powershell
python main.py
```

## Use
- The clock updates every second.
- Click a date on the calendar to view reminders scheduled for that weekday.
- Click `+ Add` to add a reminder. New reminders repeat every day by default.
- Select a reminder and click `Remove selected` to delete it.
- Turn on `Start with Windows` to create a startup shortcut. This makes the app launch when you sign in.
- By default, reminders do not cover fullscreen games/apps. They wait until fullscreen ends. Enable `Allow reminders over fullscreen games/apps` if you want popups over fullscreen apps.
- Closing the window hides it to the system tray. Use the tray icon to reopen or quit.

## Notes and limitations
- Fullscreen detection is a best-effort Windows check. It detects a foreground window that fills a monitor; it does not identify every game by name.
- This starter uses a still illustration, not a rigged Live2D model. Blinking, breathing, and body movement are a future upgrade.
- Calendar entries/reminders are stored locally in `data/schedule.json`; this is not yet synced with Google Calendar.
- The app does not monitor keystrokes, read game contents, or take screenshots.
