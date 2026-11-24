#!/usr/bin/env python3
"""Unit & integration tests for mod-skywatch (SQLite, SSRF guard, FAA flight categories, HF propagation, solar/darkness & activity scorer)."""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

MOD_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MOD_DIR / "tools"))

import sky_cli  # noqa: E402
import sky_db  # noqa: E402
import sky_feeds  # noqa: E402


def run_all() -> None:
    with tempfile.TemporaryDirectory(prefix="skywatch-test-") as tmp:
        os.environ["MODULE_DATA_DIR"] = tmp

        # 1. Default station & baro trend
        st = sky_cli.handle("get_state", {})
        assert st["status"] == "ok" and st["station"]["id"] >= 1
        saved = sky_cli.handle("save_station", {"name": "Northwoods Field", "lat": 44.5, "lon": -88.0, "icao_hint": "KGRB", "radius_nm": 50})
        assert saved["status"] == "ok" and saved["station"]["icao_hint"] == "KGRB"

        conn = sky_db.get_conn()
        sky_db.record_baro(conn, saved["station"]["id"], 1018.0)
        tr = sky_db.record_baro(conn, saved["station"]["id"], 1015.2)
        assert tr["trend"] == "FALLING_RAPIDLY" and tr["delta_3h_hpa"] == -2.8
        conn.close()

        # 2. Flight category classification
        assert sky_feeds.classify_flight_category(4500, 10.0) == "VFR"
        assert sky_feeds.classify_flight_category(2200, 6.0) == "MVFR"
        assert sky_feeds.classify_flight_category(700, 4.0) == "IFR"
        assert sky_feeds.classify_flight_category(300, 0.5) == "LIFR"

        # 3. HF propagation & geomagnetic aurora math
        quiet = sky_feeds.compute_hf_propagation(kp=2.0, sfi=160.0, xray_class="B2", user_lat=44.5)
        assert quiet["g_scale"] == "G0" and quiet["r_scale"] == "R0"
        assert any(b["band"] == "20m" and b["day"] == "OPEN" for b in quiet["bands"])
        storm = sky_feeds.compute_hf_propagation(kp=7.2, sfi=140.0, xray_class="X1.5", user_lat=45.0)
        assert storm["g_scale"] == "G3" and storm["r_scale"] == "R3+" and storm["aurora_possible_here"] is True

        # 4. Pure-Python solar elevation & moon illumination + outdoor window scorer
        noon_utc = datetime(2026, 6, 21, 18, 0, tzinfo=timezone.utc)
        night_utc = datetime(2026, 6, 21, 6, 0, tzinfo=timezone.utc)
        assert sky_feeds.solar_elevation_deg(44.5, -88.0, noon_utc) > 60.0
        assert sky_feeds.solar_elevation_deg(44.5, -88.0, night_utc) < -18.0
        moon = sky_feeds.moon_illumination_pct(noon_utc)
        assert 0.0 <= moon <= 100.0

        sample_hours = [
            {"time_utc": "2026-06-21T06:00Z", "cloud_cover_pct": 5, "wind_kt": 4, "gust_kt": 6, "precip_prob_pct": 0, "precip_mm": 0, "cape": 0, "visibility_km": 24, "solar_elev_deg": -22.0, "sky_phase": "DARK"},
            {"time_utc": "2026-06-21T18:00Z", "cloud_cover_pct": 10, "wind_kt": 8, "gust_kt": 11, "precip_prob_pct": 0, "precip_mm": 0, "cape": 50, "visibility_km": 24, "solar_elev_deg": 65.0, "sky_phase": "DAY"},
        ]
        star = sky_feeds.score_outdoor_windows(sample_hours, activity="stargazing", moon_pct=10.0)
        assert star[0]["score"] >= 85 and star[1]["score"] == 0
        drone = sky_feeds.score_outdoor_windows(sample_hours, activity="drone")
        assert drone[1]["score"] >= 85 and drone[0]["score"] < 55

        # 5. SSRF guard on custom ADS-B URL
        assert sky_feeds._validate_local_adsb_url("http://127.0.0.1:8080/data/aircraft.json").startswith("http://127.0.0.1")
        blocked = False
        try:
            sky_feeds._validate_local_adsb_url("http://169.254.169.254/latest/meta-data/")
        except ValueError:
            blocked = True
        assert blocked is True

        # 6. Save briefing
        br = sky_cli.handle("save_briefing", {"kind": "watch", "title": "Evening Check", "summary_md": "All VFR, 20m open."})
        assert br["status"] == "ok" and br["briefing"]["id"] >= 1

        print("ALL_SKYWATCH_TESTS_PASS")


if __name__ == "__main__":
    run_all()
