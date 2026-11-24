#!/usr/bin/env bash
# hooks/context.sh — Injects compact active SkyWatch station & barometer summary
set -euo pipefail
LODGE_DIR="${LODGE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)}"
MODULE_DIR="${MODULE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
MODULE_DATA_DIR="${MODULE_DATA_DIR:-$LODGE_DIR/.george/module_data/skywatch}"
export MODULE_DIR MODULE_DATA_DIR LODGE_DIR
PY="$LODGE_DIR/.venv/bin/python"
[ -x "$PY" ] || PY="python3"
"$PY" -c '
import sys
sys.path.insert(0, "'"$MODULE_DIR"'/tools")
import sky_db
conn = sky_db.get_conn()
st = sky_db.get_station(conn)
baro = sky_db.get_baro_trend(conn, st["id"])
print(f"SKYWATCH ACTIVE STATION: [{st[\"id\"]}] {st[\"name\"]} @ {st[\"lat\"]:.4f},{st[\"lon\"]:.4f} (ICAO hint: {st[\"icao_hint\"] or \"auto\"}, radius: {st[\"radius_nm\"]}nm) | Baro trend: {baro[\"trend\"]}")
' 2>/dev/null || true
