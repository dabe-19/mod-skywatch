#!/usr/bin/env python3
"""
tools/sky_feeds.py — Free public government/open feed fetchers & calculators for mod-skywatch.

Feeds (ZERO API keys required):
  - NOAA / NWS (api.weather.gov): alerts, grid metadata, nearest surface observation
  - AviationWeather.gov (aviationweather.gov/api/data/metar & /taf): METAR/TAF + VFR/MVFR/IFR/LIFR
  - NOAA SWPC (services.swpc.noaa.gov): Planetary Kp, 10.7cm SFI, GOES X-ray + HF 80m-10m propagation & aurora
  - Open-Meteo (api.open-meteo.com): 72h hourly weather + pure-Python solar twilight/darkness & moon phase + activity window scorer
  - ADS-B (optional local dump1090/readsb JSON or OpenSky Network public REST API)
"""
from __future__ import annotations

import ipaddress
import json
import math
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import sky_db

USER_AGENT = "BlueLodge-SkyWatch/1.0 (+https://github.com/dabe-19/blue-lodge-public)"


def _http_get_json(url: str, timeout: float = 12.0, cache_key: str = "", ttl_sec: int = 0) -> Any:
    cfile: Optional[Path] = None
    if cache_key and ttl_sec > 0:
        safe_key = "".join(c if c.isalnum() or c in "._-" else "_" for c in cache_key)
        cfile = sky_db.cache_dir() / f"{safe_key}.json"
        if cfile.exists() and (time.time() - cfile.stat().st_mtime) < ttl_sec:
            try:
                return json.loads(cfile.read_text(encoding="utf-8"))
            except Exception:
                pass
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/geo+json, application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    data = json.loads(raw)
    if cfile is not None:
        try:
            cfile.write_text(json.dumps(data), encoding="utf-8")
        except Exception:
            pass
    return data


def _validate_local_adsb_url(url: str) -> str:
    """SSRF guard: custom ADS-B URLs must be http(s) pointing to localhost or private LAN dump1090/readsb."""
    parsed = urllib.parse.urlparse(url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Invalid ADS-B URL scheme or host")
    host = parsed.hostname.lower()
    if host in ("localhost", "127.0.0.1", "::1"):
        return url.strip()
    try:
        ip = ipaddress.ip_address(host)
        if (ip.is_private or ip.is_loopback) and not ip.is_link_local and not ip.is_unspecified:
            return url.strip()
    except ValueError:
        pass
    raise ValueError("Custom ADS-B URL must point to localhost or a private LAN dump1090/readsb receiver")


def fetch_nws_watch(lat: float, lon: float) -> Dict[str, Any]:
    """Fetch NOAA/NWS point metadata, active severe weather alerts, and nearest station obs."""
    lat_r = round(float(lat), 4)
    lon_r = round(float(lon), 4)
    alerts_out: List[Dict[str, Any]] = []
    point_info: Dict[str, Any] = {}
    obs_out: Dict[str, Any] = {}
    errors: List[str] = []

    try:
        al = _http_get_json(
            f"https://api.weather.gov/alerts/active?point={lat_r},{lon_r}",
            timeout=12.0,
            cache_key=f"nws_alerts_{lat_r}_{lon_r}",
            ttl_sec=120,
        )
        for feat in (al.get("features") or [])[:12]:
            p = feat.get("properties") or {}
            alerts_out.append({
                "id": p.get("id", ""),
                "event": p.get("event", "Weather Alert"),
                "severity": p.get("severity", "Unknown"),
                "urgency": p.get("urgency", ""),
                "certainty": p.get("certainty", ""),
                "headline": p.get("headline", ""),
                "onset": p.get("onset", ""),
                "expires": p.get("expires", ""),
                "instruction": (p.get("instruction") or "")[:600],
            })
    except Exception as e:
        errors.append(f"NWS alerts: {e}")

    try:
        pt = _http_get_json(
            f"https://api.weather.gov/points/{lat_r},{lon_r}",
            timeout=12.0,
            cache_key=f"nws_pt_{lat_r}_{lon_r}",
            ttl_sec=3600,
        )
        props = pt.get("properties") or {}
        rel = (props.get("relativeLocation") or {}).get("properties") or {}
        point_info = {
            "city": rel.get("city", ""),
            "state": rel.get("state", ""),
            "cwa": props.get("cwa", ""),
            "radar_station": props.get("radarStation", ""),
            "grid_id": props.get("gridId", ""),
        }
        st_url = props.get("observationStations")
        if st_url:
            st_list = _http_get_json(st_url, timeout=10.0, cache_key=f"nws_sts_{lat_r}_{lon_r}", ttl_sec=3600)
            feats = st_list.get("features") or []
            if feats:
                st_id = (feats[0].get("properties") or {}).get("stationIdentifier")
                if st_id:
                    ob = _http_get_json(
                        f"https://api.weather.gov/stations/{st_id}/observations/latest",
                        timeout=10.0,
                        cache_key=f"nws_obs_{st_id}",
                        ttl_sec=180,
                    )
                    op = ob.get("properties") or {}
                    baro_pa = (op.get("barometricPressure") or {}).get("value")
                    temp_c = (op.get("temperature") or {}).get("value")
                    dew_c = (op.get("dewpoint") or {}).get("value")
                    wind_kmh = (op.get("windSpeed") or {}).get("value")
                    obs_out = {
                        "station_id": st_id,
                        "timestamp": op.get("timestamp", ""),
                        "text_description": op.get("textDescription", ""),
                        "temp_c": round(temp_c, 1) if temp_c is not None else None,
                        "temp_f": round(temp_c * 9 / 5 + 32, 1) if temp_c is not None else None,
                        "dewpoint_c": round(dew_c, 1) if dew_c is not None else None,
                        "pressure_hpa": round(baro_pa / 100.0, 1) if baro_pa else None,
                        "wind_dir_deg": (op.get("windDirection") or {}).get("value"),
                        "wind_kt": round(wind_kmh * 0.539957, 1) if wind_kmh is not None else None,
                        "humidity_pct": round((op.get("relativeHumidity") or {}).get("value") or 0, 1) if (op.get("relativeHumidity") or {}).get("value") is not None else None,
                    }
    except Exception as e:
        errors.append(f"NWS point/obs: {e}")

    return {
        "status": "ok" if not errors or alerts_out or point_info else "degraded",
        "point": point_info,
        "alerts_count": len(alerts_out),
        "alerts": alerts_out,
        "observation": obs_out,
        "errors": errors,
    }


def classify_flight_category(ceiling_ft: Optional[int], vis_sm: Optional[float]) -> str:
    """FAA flight category classification from ceiling (ft AGL) and visibility (statute miles)."""
    c = ceiling_ft if ceiling_ft is not None else 99999
    v = vis_sm if vis_sm is not None else 10.0
    if c < 500 or v < 1.0:
        return "LIFR"
    if c < 1000 or v < 3.0:
        return "IFR"
    if c <= 3000 or v <= 5.0:
        return "MVFR"
    return "VFR"


def _extract_ceiling_ft(clouds: Any) -> Optional[int]:
    if not isinstance(clouds, list):
        return None
    ceilings = []
    for cl in clouds:
        if isinstance(cl, dict) and str(cl.get("cover") or "").upper() in ("BKN", "OVC", "VV"):
            base = cl.get("base")
            if base is not None:
                try:
                    ceilings.append(int(base))
                except (ValueError, TypeError):
                    pass
    return min(ceilings) if ceilings else None


def fetch_aviation_metar_taf(lat: float, lon: float, radius_nm: float = 45.0, icao_hint: str = "") -> Dict[str, Any]:
    """Fetch nearby METAR & TAF observations from AviationWeather.gov (free, zero keys)."""
    deg_pad = max(0.35, min(2.5, float(radius_nm) / 55.0))
    lat0, lat1 = round(lat - deg_pad, 3), round(lat + deg_pad, 3)
    lon0, lon1 = round(lon - deg_pad * 1.3, 3), round(lon + deg_pad * 1.3, 3)
    bbox = f"{lat0},{lon0},{lat1},{lon1}"
    stations: List[Dict[str, Any]] = []
    tafs: List[Dict[str, Any]] = []
    errors: List[str] = []

    try:
        metar_url = f"https://aviationweather.gov/api/data/metar?bbox={bbox}&format=json"
        raw = _http_get_json(metar_url, timeout=12.0, cache_key=f"metar_{bbox}", ttl_sec=180)
        if not isinstance(raw, list):
            raw = []
        if icao_hint:
            hint_u = icao_hint.upper()
            if not any(str(m.get("icaoId") or "").upper() == hint_u for m in raw):
                try:
                    extra = _http_get_json(
                        f"https://aviationweather.gov/api/data/metar?ids={urllib.parse.quote(hint_u)}&format=json",
                        timeout=10.0,
                        cache_key=f"metar_id_{hint_u}",
                        ttl_sec=180,
                    )
                    if isinstance(extra, list):
                        raw = extra + raw
                except Exception:
                    pass
        if isinstance(raw, list):
            for m in raw[:20]:
                slat = float(m.get("lat") or 0)
                slon = float(m.get("lon") or 0)
                dist_nm = round(math.hypot((slat - lat) * 60.0, (slon - lon) * 60.0 * math.cos(math.radians(lat))), 1)
                vis_raw = m.get("visib")
                vis_sm = 10.0 if str(vis_raw) == "10+" else (float(vis_raw) if vis_raw not in (None, "") else None)
                ceil_ft = _extract_ceiling_ft(m.get("clouds"))
                flt = m.get("fltCat") or classify_flight_category(ceil_ft, vis_sm)
                stations.append({
                    "icao": m.get("icaoId", ""),
                    "name": m.get("name", ""),
                    "lat": slat,
                    "lon": slon,
                    "dist_nm": dist_nm,
                    "flight_category": flt,
                    "ceiling_ft": ceil_ft,
                    "vis_sm": vis_sm,
                    "temp_c": m.get("temp"),
                    "dewp_c": m.get("dewp"),
                    "wdir": m.get("wdir"),
                    "wspd_kt": m.get("wspd"),
                    "wgst_kt": m.get("wgst"),
                    "altim_hpa": m.get("altim"),
                    "raw_ob": m.get("rawOb", ""),
                })
            stations.sort(key=lambda x: x["dist_nm"])
    except Exception as e:
        errors.append(f"METAR: {e}")

    try:
        taf_ids = ",".join([s["icao"] for s in stations[:4] if s.get("icao")]) or (icao_hint.upper() if icao_hint else "")
        if taf_ids:
            t_raw = _http_get_json(
                f"https://aviationweather.gov/api/data/taf?ids={urllib.parse.quote(taf_ids)}&format=json",
                timeout=12.0,
                cache_key=f"taf_{taf_ids}",
                ttl_sec=300,
            )
            if isinstance(t_raw, list):
                for t in t_raw[:4]:
                    tafs.append({"icao": t.get("icaoId", ""), "raw_taf": t.get("rawTAF", "")})
    except Exception as e:
        errors.append(f"TAF: {e}")

    return {
        "status": "ok" if stations or not errors else "degraded",
        "count": len(stations),
        "nearest": stations[0] if stations else None,
        "stations": stations[:12],
        "tafs": tafs,
        "errors": errors,
    }


def compute_hf_propagation(kp: float, sfi: float, xray_class: str = "B", user_lat: float = 40.0) -> Dict[str, Any]:
    """Derive NOAA G/R scales, aurora visibility threshold, estimated MUF, and 80m-10m HF band status."""
    g_scale = "G0"
    if kp >= 9: g_scale = "G5"
    elif kp >= 8: g_scale = "G4"
    elif kp >= 7: g_scale = "G3"
    elif kp >= 6: g_scale = "G2"
    elif kp >= 5: g_scale = "G1"

    xc = (xray_class or "A").upper()
    r_scale = "R0"
    if xc.startswith("X"):
        r_scale = "R3+"
    elif xc.startswith("M5") or xc.startswith("M6") or xc.startswith("M7") or xc.startswith("M8") or xc.startswith("M9"):
        r_scale = "R2"
    elif xc.startswith("M"):
        r_scale = "R1"

    # Approximate equatorward aurora visibility boundary (geographic latitude, North America)
    aurora_min_lat = round(max(36.0, 66.5 - (kp * 3.1)), 1)
    aurora_chance = abs(user_lat) >= aurora_min_lat
    est_muf_mhz = round(max(7.0, min(38.0, 9.0 + (sfi - 70.0) * 0.14 - max(0.0, kp - 3.0) * 1.8)), 1)

    def _band_state(freq_mhz: float, is_day: bool) -> str:
        if r_scale in ("R2", "R3+") and is_day and freq_mhz <= 14.5:
            return "CLOSED"
        if kp >= 6:
            return "POOR" if freq_mhz <= 14.5 else "CLOSED"
        if is_day:
            if freq_mhz <= 7.5:
                return "FAIR" if sfi < 140 else "POOR"
            if freq_mhz <= est_muf_mhz * 0.92:
                return "OPEN"
            if freq_mhz <= est_muf_mhz * 1.08:
                return "FAIR"
            return "CLOSED"
        else:
            if freq_mhz <= 10.5:
                return "OPEN" if kp < 5 else "FAIR"
            if freq_mhz <= 14.5:
                return "OPEN" if sfi >= 115 and kp < 4 else "FAIR"
            if freq_mhz <= 21.5:
                return "FAIR" if sfi >= 150 and kp < 4 else "CLOSED"
            return "CLOSED"

    bands = []
    for name, mhz in (("80m", 3.5), ("40m", 7.0), ("30m", 10.1), ("20m", 14.0), ("17m", 18.1), ("15m", 21.0), ("12m", 24.9), ("10m", 28.0)):
        bands.append({
            "band": name,
            "freq_mhz": mhz,
            "day": _band_state(mhz, True),
            "night": _band_state(mhz, False),
        })

    return {
        "kp": round(kp, 2),
        "sfi": round(sfi, 1),
        "xray_class": xc,
        "g_scale": g_scale,
        "r_scale": r_scale,
        "est_muf_mhz": est_muf_mhz,
        "aurora_min_lat": aurora_min_lat,
        "aurora_possible_here": aurora_chance,
        "bands": bands,
    }


def fetch_space_weather(user_lat: float = 40.0) -> Dict[str, Any]:
    """Fetch live NOAA SWPC Kp index, 10.7cm solar flux (SFI), and GOES X-ray flux."""
    kp_val = 2.0
    kp_time = ""
    sfi_val = 120.0
    xray_cls = "B1"
    errors: List[str] = []

    try:
        kp_data = _http_get_json(
            "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json",
            timeout=10.0,
            cache_key="swpc_kp",
            ttl_sec=300,
        )
        if isinstance(kp_data, list) and kp_data:
            last = kp_data[-1]
            if isinstance(last, dict):
                kp_time = str(last.get("time_tag") or "")
                kp_val = float(last.get("Kp") if last.get("Kp") is not None else last.get("kp", 2.0))
            elif isinstance(last, list) and len(last) >= 2:
                kp_time = str(last[0])
                kp_val = float(last[1])
    except Exception as e:
        errors.append(f"SWPC Kp: {e}")

    try:
        sfi_data = _http_get_json(
            "https://services.swpc.noaa.gov/products/summary/10cm-flux.json",
            timeout=10.0,
            cache_key="swpc_sfi",
            ttl_sec=600,
        )
        if isinstance(sfi_data, list) and sfi_data:
            last_s = sfi_data[-1]
            if isinstance(last_s, dict):
                fv = last_s.get("flux") if last_s.get("flux") is not None else last_s.get("Flux")
                if fv is not None:
                    sfi_val = float(fv)
        elif isinstance(sfi_data, dict):
            fv = sfi_data.get("Flux") if sfi_data.get("Flux") is not None else sfi_data.get("flux")
            if fv is not None:
                sfi_val = float(fv)
    except Exception as e:
        errors.append(f"SWPC SFI: {e}")

    try:
        xr_data = _http_get_json(
            "https://services.swpc.noaa.gov/json/goes/primary/xrays-6-hour.json",
            timeout=10.0,
            cache_key="swpc_xray",
            ttl_sec=300,
        )
        if isinstance(xr_data, list) and xr_data:
            flux = 0.0
            for item in reversed(xr_data):
                if item.get("energy") == "0.1-0.8nm" and item.get("flux") is not None:
                    flux = float(item["flux"])
                    break
            if flux >= 1e-4: xray_cls = f"X{flux / 1e-4:.1f}"
            elif flux >= 1e-5: xray_cls = f"M{flux / 1e-5:.1f}"
            elif flux >= 1e-6: xray_cls = f"C{flux / 1e-6:.1f}"
            elif flux >= 1e-7: xray_cls = f"B{flux / 1e-7:.1f}"
            else: xray_cls = "A1.0"
    except Exception as e:
        errors.append(f"SWPC X-ray: {e}")

    prop = compute_hf_propagation(kp_val, sfi_val, xray_cls, user_lat=user_lat)
    return {
        "status": "ok" if not errors else "degraded",
        "kp_observed_utc": kp_time,
        **prop,
        "errors": errors,
    }


def solar_elevation_deg(lat: float, lon: float, dt_utc: datetime) -> float:
    """Pure-Python NOAA solar elevation angle (degrees) for twilight/darkness calculation."""
    doy = dt_utc.timetuple().tm_yday
    frac_hr = dt_utc.hour + dt_utc.minute / 60.0 + dt_utc.second / 3600.0
    gamma = 2.0 * math.pi / 365.0 * (doy - 1 + (frac_hr - 12.0) / 24.0)
    eqtime = 229.18 * (0.000075 + 0.001868 * math.cos(gamma) - 0.032077 * math.sin(gamma) - 0.014615 * math.cos(2 * gamma) - 0.040849 * math.sin(2 * gamma))
    decl = 0.006918 - 0.399912 * math.cos(gamma) + 0.070257 * math.sin(gamma) - 0.006758 * math.cos(2 * gamma) + 0.000907 * math.sin(2 * gamma)
    tst = (frac_hr * 60.0 + eqtime + 4.0 * lon) % 1440.0
    ha_deg = tst / 4.0 - 180.0
    lat_r = math.radians(lat)
    ha_r = math.radians(ha_deg)
    sin_alt = math.sin(lat_r) * math.sin(decl) + math.cos(lat_r) * math.cos(decl) * math.cos(ha_r)
    return round(math.degrees(math.asin(max(-1.0, min(1.0, sin_alt)))), 2)


def moon_illumination_pct(dt_utc: datetime) -> float:
    """Approximate lunar illumination percentage (0-100) from synodic cycle reference."""
    ref = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)
    days = (dt_utc - ref).total_seconds() / 86400.0
    phase = (days % 29.53058867) / 29.53058867
    illum = (1.0 - math.cos(2.0 * math.pi * phase)) * 50.0
    return round(illum, 1)


def score_outdoor_windows(
    hourly: List[Dict[str, Any]],
    activity: str = "stargazing",
    kp: float = 2.0,
    sfi: float = 120.0,
    moon_pct: float = 35.0,
) -> List[Dict[str, Any]]:
    """Score each forecast hour (0-100) for stargazing, drone, boating, or ham_field_day."""
    act = str(activity or "stargazing").strip().lower()
    scored = []
    for h in hourly:
        cloud = float(h.get("cloud_cover_pct") or 0)
        wind_kt = float(h.get("wind_kt") or 0)
        gust_kt = float(h.get("gust_kt") or wind_kt)
        precip_p = float(h.get("precip_prob_pct") or 0)
        precip_mm = float(h.get("precip_mm") or 0)
        cape = float(h.get("cape") or 0)
        vis_km = float(h.get("visibility_km") or 20.0)
        sun_el = float(h.get("solar_elev_deg") or 0.0)

        score = 100.0
        reasons: List[str] = []

        if act == "stargazing":
            if sun_el > -12.0:
                score = 0.0
                reasons.append("daylight/bright twilight")
            else:
                if sun_el > -18.0:
                    score -= 18
                    reasons.append("nautical twilight")
                score -= cloud * 0.85
                score -= precip_p * 0.4
                score -= moon_pct * 0.22
                if wind_kt > 15:
                    score -= (wind_kt - 15) * 1.5
                if cloud <= 15:
                    reasons.append("clear skies")
        elif act == "drone":
            if sun_el < -4.0:
                score -= 55
                reasons.append("darkness (VLOS/night waiver)")
            if gust_kt > 20:
                score -= (gust_kt - 15) * 3.5
                reasons.append(f"gusts {gust_kt:.0f}kt")
            elif wind_kt > 14:
                score -= (wind_kt - 12) * 2.5
            score -= precip_p * 0.7 + (35 if precip_mm > 0.1 else 0)
            if vis_km < 5.0:
                score -= 35
                reasons.append("low visibility")
            if cape > 600:
                score -= 25
                reasons.append("convective/storm risk")
        elif act == "boating":
            if gust_kt > 18:
                score -= (gust_kt - 12) * 3.5
                reasons.append(f"chop/gusts {gust_kt:.0f}kt")
            score -= precip_p * 0.55 + (30 if precip_mm > 0.2 else 0)
            if cape > 500:
                score -= 35
                reasons.append("thunderstorm CAPE")
            if vis_km < 4.0:
                score -= 30
                reasons.append("fog/low vis")
        else:  # ham_field_day
            if cape > 500:
                score -= 45
                reasons.append("lightning/CAPE risk")
            score -= precip_p * 0.5 + (25 if precip_mm > 0.2 else 0)
            if gust_kt > 22:
                score -= (gust_kt - 18) * 2.5
                reasons.append("high antenna wind load")
            if kp >= 5:
                score -= (kp - 4) * 12
                reasons.append(f"geomag storm Kp={kp}")
            if sfi >= 130 and kp < 4:
                score = min(100.0, score + 8)
                reasons.append("strong HF SFI")

        final = int(max(0, min(100, round(score))))
        scored.append({
            **h,
            "activity": act,
            "score": final,
            "rating": "PRIME" if final >= 78 else ("GOOD" if final >= 58 else ("MARGINAL" if final >= 38 else "POOR")),
            "reasons": reasons,
        })
    return scored


def fetch_open_meteo_72h(lat: float, lon: float, activity: str = "stargazing", kp: float = 2.0, sfi: float = 120.0) -> Dict[str, Any]:
    """Fetch 72-hour Open-Meteo hourly telemetry + astronomical darkness & activity window rankings."""
    lat_r = round(float(lat), 4)
    lon_r = round(float(lon), 4)
    url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={lat_r}&longitude={lon_r}"
        "&hourly=temperature_2m,cloud_cover,precipitation_probability,precipitation,wind_speed_10m,wind_gusts_10m,wind_direction_10m,visibility,cape,surface_pressure"
        "&wind_speed_unit=kn&forecast_days=3&timezone=UTC"
    )
    data = _http_get_json(url, timeout=12.0, cache_key=f"om72_{lat_r}_{lon_r}", ttl_sec=600)
    h = data.get("hourly") or {}
    times = h.get("time") or []
    now_dt = datetime.now(timezone.utc)
    moon_pct = moon_illumination_pct(now_dt)

    rows: List[Dict[str, Any]] = []
    for i, t_str in enumerate(times[:72]):
        dt = datetime.fromisoformat(t_str).replace(tzinfo=timezone.utc)
        if dt < now_dt.replace(minute=0, second=0, microsecond=0):
            continue
        sun_el = solar_elevation_deg(lat_r, lon_r, dt)
        rows.append({
            "time_utc": t_str + "Z",
            "temp_c": (h.get("temperature_2m") or [None])[i],
            "cloud_cover_pct": (h.get("cloud_cover") or [0])[i],
            "precip_prob_pct": (h.get("precipitation_probability") or [0])[i],
            "precip_mm": (h.get("precipitation") or [0])[i],
            "wind_kt": (h.get("wind_speed_10m") or [0])[i],
            "gust_kt": (h.get("wind_gusts_10m") or [0])[i],
            "wind_dir_deg": (h.get("wind_direction_10m") or [0])[i],
            "visibility_km": round(((h.get("visibility") or [20000])[i] or 20000) / 1000.0, 1),
            "cape": (h.get("cape") or [0])[i] or 0,
            "pressure_hpa": (h.get("surface_pressure") or [None])[i],
            "solar_elev_deg": sun_el,
            "sky_phase": "DARK" if sun_el <= -18 else ("ASTRO_TWILIGHT" if sun_el <= -12 else ("TWILIGHT" if sun_el <= 0 else "DAY")),
        })

    scored = score_outdoor_windows(rows, activity=activity, kp=kp, sfi=sfi, moon_pct=moon_pct)
    top_windows = sorted(scored, key=lambda x: (-x["score"], x["time_utc"]))[:8]
    return {
        "status": "ok",
        "activity": activity,
        "moon_illumination_pct": moon_pct,
        "hours_count": len(scored),
        "top_windows": top_windows,
        "hourly": scored[:48],
    }


def fetch_adsb_aircraft(lat: float, lon: float, radius_nm: float = 45.0, local_url: str = "") -> Dict[str, Any]:
    """Fetch live ADS-B traffic from local dump1090/readsb (if configured) or OpenSky Network public API."""
    aircraft: List[Dict[str, Any]] = []
    source = "opensky"
    note = ""

    if local_url and local_url.strip():
        try:
            safe_url = _validate_local_adsb_url(local_url)
            source = "local_dump1090"
            raw = _http_get_json(safe_url, timeout=4.0)
            for ac in (raw.get("aircraft") or [])[:60]:
                if ac.get("lat") is None or ac.get("lon") is None:
                    continue
                aircraft.append({
                    "icao24": str(ac.get("hex") or "").upper(),
                    "callsign": str(ac.get("flight") or "").strip(),
                    "lat": float(ac["lat"]),
                    "lon": float(ac["lon"]),
                    "alt_ft": int(ac.get("alt_baro") or ac.get("altitude") or 0) if str(ac.get("alt_baro") or "").lstrip("-").isdigit() else 0,
                    "speed_kt": round(float(ac.get("gs") or ac.get("speed") or 0), 0),
                    "heading": round(float(ac.get("track") or 0), 0),
                    "squawk": str(ac.get("squawk") or ""),
                })
            return {"status": "ok", "source": source, "count": len(aircraft), "aircraft": aircraft}
        except Exception as e:
            note = f"Local ADS-B unavailable ({e}); trying OpenSky public feed."

    deg_pad = max(0.35, min(1.8, float(radius_nm) / 55.0))
    lamin, lamax = round(lat - deg_pad, 3), round(lat + deg_pad, 3)
    lomin, lomax = round(lon - deg_pad * 1.3, 3), round(lon + deg_pad * 1.3, 3)
    try:
        url = f"https://opensky-network.org/api/states/all?lamin={lamin}&lomin={lomin}&lamax={lamax}&lomax={lomax}"
        raw = _http_get_json(url, timeout=8.0, cache_key=f"opensky_{lamin}_{lomin}", ttl_sec=25)
        for st in (raw.get("states") or [])[:50]:
            if len(st) < 11 or st[5] is None or st[6] is None:
                continue
            alt_m = st[13] if len(st) > 13 and st[13] is not None else (st[7] or 0)
            vel_ms = st[9] or 0
            aircraft.append({
                "icao24": str(st[0] or "").upper(),
                "callsign": str(st[1] or "").strip() or str(st[0] or "").upper(),
                "lat": float(st[6]),
                "lon": float(st[5]),
                "alt_ft": int(round(float(alt_m) * 3.28084)),
                "speed_kt": int(round(float(vel_ms) * 1.94384)),
                "heading": int(round(float(st[10] or 0))),
                "squawk": str(st[14] or "") if len(st) > 14 and st[14] else "",
            })
        return {"status": "ok", "source": "opensky", "count": len(aircraft), "aircraft": aircraft, "note": note}
    except Exception as e:
        return {"status": "rate_limited_or_offline", "source": "opensky", "count": 0, "aircraft": [], "note": f"{note} OpenSky public API unavailable/throttled ({e})".strip()}
