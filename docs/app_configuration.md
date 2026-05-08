# Adhan Clock App Configuration Guide

## Configuration File

The app stores its settings in `config.json` at the project root. Example:

```json
{
    "fajr_angle": 18.0,
    "isha_angle": 18.0,
    "method": "NORTH_AMERICA"
}
```

### Fields

- **fajr_angle** (float, 0–30): The twilight angle below the horizon used to calculate Fajr start time. Higher = earlier Fajr.
- **isha_angle** (float, 0–30): The twilight angle below the horizon used to calculate Isha start time. Higher = later Isha.
- **method** (string): The named calculation method preset. Overrides individual angles when selected. Options: `NORTH_AMERICA`, `MUSLIM_WORLD_LEAGUE`, `ISNA`, `UMM_AL_QURA`, `EGYPTIAN`.

## Changing Settings via the UI

1. Click **Edit Settings** in the main window.
2. Select a **Method** from the dropdown to apply a preset.
3. Adjust **Fajr Angle** or **Isha Angle** manually if needed.
4. Click **Save Settings**.
5. The app will reload and recalculate prayer times immediately.

## Location Detection

The app detects your location in two ways:
1. **System timezone**: Reads the system timezone to infer your region.
2. **IP geolocation**: Calls `http://ip-api.com/json/` to get city name and timezone.

If offline, location defaults to "Offline" and timezone defaults to UTC.

## Running the App

```bash
python gui_clock.py
```

Or via the main entry point:
```bash
python main.py
```

## The AI Agent

The project includes an AI coding agent (`agent.py`) that can modify the codebase using Claude or Gemini.

```bash
# Using Claude (default)
python agent.py "add a dark mode toggle to the settings dialog"
ANTHROPIC_API_KEY=your_key python agent.py "show hijri date"

# Using Gemini
python agent.py --provider gemini "refactor prayer_engine.py"
GOOGLE_API_KEY=your_key python agent.py --provider gemini "your task"

# Specify a different model
python agent.py --model claude-haiku-4-5 "your task"
```

## Prayer Alerts

The app plays an Adhan audio file (`lib/makkah_adhan.mp3`) and sends a macOS notification at each prayer time. The `pygame` library handles audio playback.

To disable sound: remove or replace the MP3 file.

## Troubleshooting

- **Prayer times wrong**: Check your system timezone is set correctly, or try clicking "Refresh Location / Times".
- **No sound**: Ensure `lib/makkah_adhan.mp3` exists and `pygame` is installed.
- **App won't start**: Check all dependencies are installed: `pip install adhanpy pygame mac-notifications PyQt5 requests pytz`.
