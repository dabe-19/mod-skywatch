---
name: skywatch
description: Local Field, Ham Radio, Weather, Space-Weather & Aviation Situational Bench (NOAA/NWS, METAR/TAF, SWPC Kp/SFI/HF, Open-Meteo 72h windows, and ADS-B).
---

# SkyWatch Skill

Use `+sky` tools to pull live public government & open situational telemetry without any API keys:
- `sky_nws_watch`: Active NWS alerts, forecast office metadata, latest observation, and 3h barometric trend.
- `sky_aviation`: Nearby METAR/TAF observations decoded to FAA flight categories (VFR/MVFR/IFR/LIFR), ceiling, visibility, and wind.
- `sky_space_weather`: Live NOAA SWPC Kp index (`G0`–`G5`), 10.7cm SFI, GOES X-ray (`R0`–`R5`), aurora visibility estimate, and 80m–10m Day/Night HF band status.
- `sky_window_planner`: 72-hour scored Go/No-Go windows for `stargazing`, `drone`, `boating`, or `ham_field_day`.
- `sky_adsb_traffic`: Live ADS-B aircraft from local `dump1090`/`readsb` or OpenSky Network.
