# Islamic Prayer Times Guide

## The Five Daily Prayers

Muslims are required to pray five times a day. Each prayer has a name and a time window defined by the position of the sun.

### Fajr (Dawn Prayer)
- **Time**: From the appearance of true dawn (astronomical twilight) until just before sunrise.
- **Rakats**: 2 obligatory (fard)
- **Significance**: The first prayer of the day, said before sunrise.
- The Fajr time is calculated based on a twilight angle below the horizon (typically 15°–18° depending on the method).

### Dhuhr (Midday Prayer)
- **Time**: After the sun passes its zenith (highest point) and begins to decline, until the shadow of an object equals its own length.
- **Rakats**: 4 obligatory
- **Significance**: The midday prayer. On Fridays, replaced by Jumu'ah (Friday congregational prayer).

### Asr (Afternoon Prayer)
- **Time**: When the shadow of an object is equal to its length (Standard method) or twice its length (Hanafi method), until just before sunset.
- **Rakats**: 4 obligatory
- **Significance**: The middle prayer specifically mentioned in the Quran.
- **Note**: There are two scholarly opinions on the start time:
  - Standard (Shafi'i, Maliki, Hanbali): shadow = 1× object length
  - Hanafi: shadow = 2× object length

### Maghrib (Sunset Prayer)
- **Time**: Immediately after sunset until the red twilight disappears from the sky (approximately 1.5 hours after sunset).
- **Rakats**: 3 obligatory
- **Significance**: The sunset prayer. Must be prayed promptly after sunset.

### Isha (Night Prayer)
- **Time**: When the red/white twilight disappears from the sky (approximately 1.5–2 hours after sunset), until midnight or dawn.
- **Rakats**: 4 obligatory
- **Significance**: The last obligatory prayer of the day.
- Like Fajr, Isha time is calculated based on a twilight angle (typically 15°–18°).

## Sunrise

Sunrise is not a prayer time itself, but marks the end of the Fajr prayer window. After sunrise, Fajr cannot be prayed (it becomes qada/makeup). The app shows Sunrise as a reference time.

---

## Prayer Time Calculation Methods

Prayer times are calculated using astronomical formulas. The main variable between methods is the **twilight angle** used to determine Fajr and Isha.

### NORTH_AMERICA (Islamic Society of North America - ISNA)
- Fajr angle: 15°
- Isha angle: 15°
- Used by: Mosques in the United States and Canada

### MUSLIM_WORLD_LEAGUE (MWL)
- Fajr angle: 18°
- Isha angle: 17°
- Used by: Mosques in Europe, Far East, and parts of the Americas

### ISNA (same as NORTH_AMERICA)
- Fajr angle: 15°
- Isha angle: 15°

### UMM_AL_QURA (Umm al-Qura University, Mecca)
- Fajr angle: 18.5°
- Isha: 90 minutes after Maghrib (not angle-based)
- Used by: Saudi Arabia and surrounding countries
- **Note**: During Ramadan, Isha is 120 minutes after Maghrib.

### EGYPTIAN (Egyptian General Authority of Survey)
- Fajr angle: 19.5°
- Isha angle: 17.5°
- Used by: Africa, Syria, Iraq, Lebanon, Malaysia

### Key Insight
A larger twilight angle means Fajr is **earlier** (deeper into darkness) and Isha is **later**. This matters significantly at high latitudes (e.g., UK, Canada) where twilight can last the entire night in summer, making prayer calculations complex.

---

## High Latitude Adjustments

At high latitudes (above ~48°N or below ~48°S), astronomical twilight may never fully disappear in summer. Several rules exist:

- **Middle of Night**: Split the night in half; Fajr and Isha are at 1/7 and 6/7 of the night respectively.
- **Seventh of Night**: Fajr = 1/7 of the night before midnight, Isha = 1/7 after.
- **Angle-Based**: Cap the twilight angle.

---

## Understanding the App's Calculation

This app uses the `adhanpy` library which implements standard astronomical formulas:

1. **Coordinates**: Latitude and longitude determine the sun's position.
2. **Date**: Solar declination changes with the date.
3. **Method**: Determines the twilight angle for Fajr/Isha.
4. **Timezone**: Converts UTC prayer times to local time.

The app reads your location from system settings or an IP-based geolocation API.
