#!/usr/bin/env python3
"""
tools/sky_cli.py — Unified JSON CLI for mod-skywatch agent tools, web actions, and cron watch.
"""
from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sky_db  # noqa: E402
import sky_feeds  # noqa: E402


def handle(action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    conn = sky_db.get_conn()
    try:
        st = sky_db.get_station(conn, station_id=payload.get("station_id"))
        lat = float(payload.get("lat") if payload.get("lat") is not None else st["lat"])
        lon = float(payload.get("lon") if payload.get("lon") is not None else st["lon"])
        radius_nm = float(payload.get("radius_nm") or st.get("radius_nm") or 45.0)
        icao = str(payload.get("icao_hint") if payload.get("icao_hint") is not None else (st.get("icao_hint") or ""))
        adsb_url = str(payload.get("adsb_local_url") if payload.get("adsb_local_url") is not None else (st.get("adsb_local_url") or ""))

        if action == "get_state":
            return {
                "status": "ok",
                "station": st,
                "stations": sky_db.list_stations(conn),
                "baro_trend": sky_db.get_baro_trend(conn, st["id"]),
                "briefings": sky_db.list_briefings(conn, st["id"], limit=12),
                "db_path": sky_db.db_path(),
            }

        if action == "save_station":
            saved = sky_db.save_station(conn, payload)
            return {"status": "ok", "station": saved, "stations": sky_db.list_stations(conn)}

        if action == "fetch_nws":
            res = sky_feeds.fetch_nws_watch(lat, lon)
            p_hpa = (res.get("observation") or {}).get("pressure_hpa")
            if p_hpa:
                res["baro_trend"] = sky_db.record_baro(conn, st["id"], float(p_hpa))
            else:
                res["baro_trend"] = sky_db.get_baro_trend(conn, st["id"])
            return res

        if action == "fetch_aviation":
            return sky_feeds.fetch_aviation_metar_taf(lat, lon, radius_nm=radius_nm, icao_hint=icao)

        if action == "fetch_space_weather":
            return sky_feeds.fetch_space_weather(user_lat=lat)

        if action == "fetch_windows":
            sw = sky_feeds.fetch_space_weather(user_lat=lat)
            return sky_feeds.fetch_open_meteo_72h(
                lat,
                lon,
                activity=str(payload.get("activity") or "stargazing"),
                kp=float(sw.get("kp") or 2.0),
                sfi=float(sw.get("sfi") or 120.0),
            )

        if action == "fetch_adsb":
            return sky_feeds.fetch_adsb_aircraft(lat, lon, radius_nm=radius_nm, local_url=adsb_url)

        if action == "fetch_hud":
            activity = str(payload.get("activity") or "stargazing")
            include_adsb = bool(payload.get("include_adsb", True))
            with ThreadPoolExecutor(max_workers=5) as ex:
                f_nws = ex.submit(sky_feeds.fetch_nws_watch, lat, lon)
                f_av = ex.submit(sky_feeds.fetch_aviation_metar_taf, lat, lon, radius_nm, icao)
                f_sw = ex.submit(sky_feeds.fetch_space_weather, lat)
                f_adsb = ex.submit(sky_feeds.fetch_adsb_aircraft, lat, lon, radius_nm, adsb_url) if include_adsb else None
                nws = f_nws.result()
                av = f_av.result()
                sw = f_sw.result()
                adsb = f_adsb.result() if f_adsb else {"status": "skipped", "count": 0, "aircraft": []}
            p_hpa = (nws.get("observation") or {}).get("pressure_hpa")
            baro = sky_db.record_baro(conn, st["id"], float(p_hpa)) if p_hpa else sky_db.get_baro_trend(conn, st["id"])
            try:
                win = sky_feeds.fetch_open_meteo_72h(lat, lon, activity=activity, kp=float(sw.get("kp") or 2.0), sfi=float(sw.get("sfi") or 120.0))
            except Exception as e:
                win = {"status": "degraded", "error": str(e), "top_windows": [], "hourly": []}
            return {
                "status": "ok",
                "station": st,
                "nws": nws,
                "baro_trend": baro,
                "aviation": av,
                "space_weather": sw,
                "windows": win,
                "adsb": adsb,
                "briefings": sky_db.list_briefings(conn, st["id"], limit=10),
            }

        if action == "save_briefing":
            row = sky_db.save_briefing(conn, {**payload, "station_id": payload.get("station_id") or st["id"]})
            return {"status": "ok", "briefing": row}

        return {"status": "error", "message": f"Unknown skywatch action: {action}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()


def main() -> int:
    action = sys.argv[1] if len(sys.argv) > 1 else "get_state"
    raw = sys.stdin.read().strip()
    payload = json.loads(raw) if raw else {}
    res = handle(action, payload)
    print(json.dumps(res, indent=2))
    return 0 if res.get("status") != "error" else 1


if __name__ == "__main__":
    sys.exit(main())
