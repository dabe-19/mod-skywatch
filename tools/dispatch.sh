#!/usr/bin/env bash
# tools/dispatch.sh — Blue Lodge Native Tool Dispatcher for mod-skywatch
set -euo pipefail

TOOL_NAME="${1:-}"
ARGS_JSON="${2:-}"
[ -z "$ARGS_JSON" ] && ARGS_JSON="{}"

LODGE_DIR="${LODGE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)}"
MODULE_DIR="${MODULE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
MODULE_DATA_DIR="${MODULE_DATA_DIR:-$LODGE_DIR/.george/module_data/skywatch}"
export MODULE_DIR MODULE_DATA_DIR LODGE_DIR
mkdir -p "$MODULE_DATA_DIR"

PY="$LODGE_DIR/.venv/bin/python"
[ -x "$PY" ] || PY="python3"

case "$TOOL_NAME" in
    sky_nws_watch)       printf '%s' "$ARGS_JSON" | "$PY" "$MODULE_DIR/tools/sky_cli.py" fetch_nws ;;
    sky_aviation)        printf '%s' "$ARGS_JSON" | "$PY" "$MODULE_DIR/tools/sky_cli.py" fetch_aviation ;;
    sky_space_weather)   printf '%s' "$ARGS_JSON" | "$PY" "$MODULE_DIR/tools/sky_cli.py" fetch_space_weather ;;
    sky_window_planner)  printf '%s' "$ARGS_JSON" | "$PY" "$MODULE_DIR/tools/sky_cli.py" fetch_windows ;;
    sky_adsb_traffic)    printf '%s' "$ARGS_JSON" | "$PY" "$MODULE_DIR/tools/sky_cli.py" fetch_adsb ;;
    sky_briefing_save)   printf '%s' "$ARGS_JSON" | "$PY" "$MODULE_DIR/tools/sky_cli.py" save_briefing ;;
    sky_station_set)     printf '%s' "$ARGS_JSON" | "$PY" "$MODULE_DIR/tools/sky_cli.py" save_station ;;
    *)
        printf '{"status":"error","message":"Unknown skywatch tool: %s"}\n' "$TOOL_NAME"
        exit 1
        ;;
esac
