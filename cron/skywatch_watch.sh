#!/usr/bin/env bash
# cron/skywatch_watch.sh — Polls NWS severe alerts + NOAA SWPC Kp and emits Event Bus alerts on threshold
set -euo pipefail
LODGE_DIR="${LODGE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)}"
MODULE_DIR="${MODULE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
MODULE_DATA_DIR="${MODULE_DATA_DIR:-$LODGE_DIR/.george/module_data/skywatch}"
export MODULE_DIR MODULE_DATA_DIR LODGE_DIR

PY="$LODGE_DIR/.venv/bin/python"
[ -x "$PY" ] || PY="python3"

NWS_JSON=$("$PY" "$MODULE_DIR/tools/sky_cli.py" fetch_nws <<<'{}' 2>/dev/null || echo '{}')
SW_JSON=$("$PY" "$MODULE_DIR/tools/sky_cli.py" fetch_space_weather <<<'{}' 2>/dev/null || echo '{}')

ALERTS=$(printf '%s' "$NWS_JSON" | "$PY" -c 'import json,sys; d=json.loads(sys.stdin.read() or "{}"); sev=[a for a in (d.get("alerts") or []) if str(a.get("severity","")).lower() in ("extreme","severe")]; print(len(sev))' 2>/dev/null || echo 0)
KP=$(printf '%s' "$SW_JSON" | "$PY" -c 'import json,sys; d=json.loads(sys.stdin.read() or "{}"); print(float(d.get("kp") or 0))' 2>/dev/null || echo 0)

if [ -f "$LODGE_DIR/lib/ipc/event_bus.sh" ]; then
    # shellcheck disable=SC1091
    source "$LODGE_DIR/lib/ipc/event_bus.sh" 2>/dev/null || true
    if [ "${ALERTS:-0}" -gt 0 ]; then
        event_emit "skywatch.severe_alert" "{\"severe_alerts\":$ALERTS}" 2>/dev/null || true
    fi
    if "$PY" -c "import sys; sys.exit(0 if float('${KP:-0}') >= 6.0 else 1)" 2>/dev/null; then
        event_emit "skywatch.geomagnetic_storm" "{\"kp\":$KP}" 2>/dev/null || true
    fi
fi
