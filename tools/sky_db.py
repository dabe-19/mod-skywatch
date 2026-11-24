#!/usr/bin/env python3
"""
tools/sky_db.py — Parameterized SQLite store for mod-skywatch stations, baro history & briefings.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


def now_ts() -> int:
    return int(time.time())


def data_dir() -> Path:
    base = os.environ.get("MODULE_DATA_DIR")
    if base:
        p = Path(base)
    else:
        lodge = Path(os.environ.get("LODGE_DIR", Path(__file__).resolve().parents[4]))
        p = lodge / ".george" / "module_data" / "skywatch"
    p.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(p, 0o700)
    except OSError:
        pass
    return p


def cache_dir() -> Path:
    d = data_dir() / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def db_path() -> str:
    return str(data_dir() / "skywatch.db")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path(), timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    init_schema(conn)
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS stations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            lat REAL NOT NULL,
            lon REAL NOT NULL,
            icao_hint TEXT DEFAULT '',
            adsb_local_url TEXT DEFAULT '',
            radius_nm REAL DEFAULT 45.0,
            is_default INTEGER DEFAULT 0,
            updated_at INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS baro_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            station_id INTEGER NOT NULL REFERENCES stations(id) ON DELETE CASCADE,
            pressure_hpa REAL NOT NULL,
            observed_at INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS briefings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            station_id INTEGER REFERENCES stations(id) ON DELETE SET NULL,
            kind TEXT NOT NULL DEFAULT 'watch',
            title TEXT NOT NULL,
            summary_md TEXT NOT NULL,
            payload_json TEXT DEFAULT '{}',
            created_at INTEGER NOT NULL
        );
        """
    )
    conn.commit()
    # Seed a neutral default station if none exists so SkyWatch works instantly on first load
    cnt = conn.execute("SELECT COUNT(*) FROM stations").fetchone()[0]
    if cnt == 0:
        conn.execute(
            "INSERT INTO stations (name, lat, lon, icao_hint, adsb_local_url, radius_nm, is_default, updated_at) VALUES (?, ?, ?, ?, ?, ?, 1, ?)",
            ("Default US Field Station (Kansas Center)", 39.8283, -98.5795, "KSLN", "", 50.0, now_ts()),
        )
        conn.commit()


def list_stations(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    return [dict(r) for r in conn.execute("SELECT * FROM stations ORDER BY is_default DESC, updated_at DESC, id ASC").fetchall()]


def get_station(conn: sqlite3.Connection, station_id: Optional[int] = None) -> Dict[str, Any]:
    if station_id is not None:
        r = conn.execute("SELECT * FROM stations WHERE id = ?", (int(station_id),)).fetchone()
        if r:
            return dict(r)
    r = conn.execute("SELECT * FROM stations ORDER BY is_default DESC, updated_at DESC, id ASC LIMIT 1").fetchone()
    return dict(r)


def save_station(conn: sqlite3.Connection, payload: Dict[str, Any]) -> Dict[str, Any]:
    name = str(payload.get("name") or "Field Station").strip()[:120]
    lat = float(payload["lat"])
    lon = float(payload["lon"])
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        raise ValueError("lat must be in [-90, 90] and lon in [-180, 180]")
    icao = str(payload.get("icao_hint") or "").strip().upper()[:8]
    adsb = str(payload.get("adsb_local_url") or "").strip()[:240]
    radius = max(10.0, min(150.0, float(payload.get("radius_nm") or 45.0)))
    is_def = 1 if payload.get("is_default", True) else 0
    ts = now_ts()
    if is_def:
        conn.execute("UPDATE stations SET is_default = 0")
    sid = payload.get("id")
    if sid:
        conn.execute(
            "UPDATE stations SET name=?, lat=?, lon=?, icao_hint=?, adsb_local_url=?, radius_nm=?, is_default=?, updated_at=? WHERE id=?",
            (name, lat, lon, icao, adsb, radius, is_def, ts, int(sid)),
        )
        conn.commit()
        return get_station(conn, int(sid))
    cur = conn.execute(
        "INSERT INTO stations (name, lat, lon, icao_hint, adsb_local_url, radius_nm, is_default, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (name, lat, lon, icao, adsb, radius, is_def, ts),
    )
    conn.commit()
    return get_station(conn, cur.lastrowid)


def record_baro(conn: sqlite3.Connection, station_id: int, pressure_hpa: float) -> Dict[str, Any]:
    ts = now_ts()
    conn.execute(
        "INSERT INTO baro_history (station_id, pressure_hpa, observed_at) VALUES (?, ?, ?)",
        (int(station_id), float(pressure_hpa), ts),
    )
    conn.execute("DELETE FROM baro_history WHERE station_id = ? AND observed_at < ?", (int(station_id), ts - 86400))
    conn.commit()
    return get_baro_trend(conn, station_id)


def get_baro_trend(conn: sqlite3.Connection, station_id: int) -> Dict[str, Any]:
    rows = conn.execute(
        "SELECT pressure_hpa, observed_at FROM baro_history WHERE station_id = ? ORDER BY observed_at ASC",
        (int(station_id),),
    ).fetchall()
    if not rows:
        return {"trend": "NO_HISTORY", "delta_3h_hpa": 0.0, "latest_hpa": None}
    latest = float(rows[-1]["pressure_hpa"])
    latest_ts = int(rows[-1]["observed_at"])
    ref = float(rows[0]["pressure_hpa"])
    for r in rows:
        if latest_ts - int(r["observed_at"]) <= 10800:
            ref = float(r["pressure_hpa"])
            break
    delta = round(latest - ref, 2)
    if delta <= -2.0:
        label = "FALLING_RAPIDLY"
    elif delta <= -0.6:
        label = "FALLING"
    elif delta >= 2.0:
        label = "RISING_RAPIDLY"
    elif delta >= 0.6:
        label = "RISING"
    else:
        label = "STEADY"
    return {
        "trend": label,
        "delta_3h_hpa": delta,
        "latest_hpa": round(latest, 1),
        "latest_inhg": round(latest * 0.02952998, 2),
        "samples": len(rows),
    }


def save_briefing(conn: sqlite3.Connection, payload: Dict[str, Any]) -> Dict[str, Any]:
    sid = int(payload["station_id"]) if payload.get("station_id") else None
    kind = str(payload.get("kind") or "watch")[:32]
    title = str(payload.get("title") or "SkyWatch Briefing").strip()[:180]
    summary = str(payload.get("summary_md") or "").strip()[:16000]
    if not summary:
        raise ValueError("summary_md is required")
    cur = conn.execute(
        "INSERT INTO briefings (station_id, kind, title, summary_md, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (sid, kind, title, summary, json.dumps(payload.get("payload") or {}), now_ts()),
    )
    conn.commit()
    return dict(conn.execute("SELECT * FROM briefings WHERE id = ?", (cur.lastrowid,)).fetchone())


def list_briefings(conn: sqlite3.Connection, station_id: Optional[int] = None, limit: int = 15) -> List[Dict[str, Any]]:
    if station_id is not None:
        rows = conn.execute(
            "SELECT * FROM briefings WHERE station_id = ? OR station_id IS NULL ORDER BY created_at DESC, id DESC LIMIT ?",
            (int(station_id), int(limit)),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM briefings ORDER BY created_at DESC, id DESC LIMIT ?", (int(limit),)).fetchall()
    return [dict(r) for r in rows]
