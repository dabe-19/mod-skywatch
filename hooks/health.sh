#!/usr/bin/env bash
set -euo pipefail
LODGE_DIR="${LODGE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)}"
MODULE_DIR="${MODULE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
MODULE_DATA_DIR="${MODULE_DATA_DIR:-$LODGE_DIR/.george/module_data/skywatch}"
export MODULE_DIR MODULE_DATA_DIR LODGE_DIR
PY="$LODGE_DIR/.venv/bin/python"
[ -x "$PY" ] || PY="python3"
"$PY" -c '
import json, sys
sys.path.insert(0, "'"$MODULE_DIR"'/tools")
import sky_db
conn = sky_db.get_conn()
st = sky_db.list_stations(conn)
print(json.dumps({"status": "ok", "module": "skywatch", "stations": len(st), "db": sky_db.db_path()}))
'
