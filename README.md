# SkyWatch (`mod-skywatch`) — Field, Ham Radio, Weather & Aviation Situational Bench

A zero-API-key Blue Lodge situational awareness workbench built entirely on free public government & open feeds (NOAA/NWS, AviationWeather.gov, NOAA SWPC, Open-Meteo, Iowa Environmental Mesonet NEXRAD, and optional OpenSky / local `dump1090` ADS-B).

## Features

- **Live Leaflet Situational Map**:
  - Toggleable **NEXRAD Live Weather Radar** tile overlay (free IEM NEXRAD TMS).
  - Color-coded **METAR / TAF** airport markers (`VFR`, `MVFR`, `IFR`, `LIFR`) with ceiling, visibility, wind, and altimeter.
  - Optional **Live ADS-B Aircraft** overlay (local RTL-SDR `dump1090`/`readsb` JSON receiver or OpenSky Network public bounding-box feed) + 25nm / 50nm range rings.
- **NOAA SWPC Space Weather & Ham HF Propagation HUD**:
  - Live Planetary Kp Index (`G0`–`G5`), 10.7cm Solar Flux Index (`SFI`), GOES X-ray Radio Blackout (`R0`–`R5`), local aurora visibility estimate, and derived **80m–10m Day/Night HF Band Propagation Matrix**.
- **72-Hour Outdoor Activity Window Planner**:
  - Pure-Python astronomical twilight / darkness & moon phase calculator paired with Open-Meteo 72h wind, gusts, clouds, CAPE, visibility, and precipitation to score optimal windows for **Stargazing**, **Drone Flight**, **Boating**, and **Ham Field Day**.
- **ALP v1 Agentic Workflows (200-turn FIFO Parallel + ReAct)**:
  - `severe_weather_prop_watch`: Concurrent FIFO fetch of NWS alerts + METAR/TAF + SWPC solar/Kp/HF + barometer trend → ReAct actionable briefing + optional Discord / Google Home spoken alert.
  - `outdoor_window_planner`: Concurrent FIFO 72h weather/darkness/aviation/HF pull → ReAct ranked window schedule saved to SQLite.
- **Event Bus & Cron Integration**:
  - Includes `cron/skywatch_watch.sh` and opt-in `reactors/skywatch_reactors.json` to emit `skywatch.severe_alert` and `skywatch.geomagnetic_storm` events into Blue Lodge's POSIX Event Bus FIFO.
