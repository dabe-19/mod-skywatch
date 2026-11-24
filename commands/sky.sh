#!/usr/bin/env bash
# commands/sky.sh — /sky slash command for SkyWatch
set -euo pipefail
LODGE_DIR="${LODGE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)}"
MODULE_DIR="${MODULE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
PY="$LODGE_DIR/.venv/bin/python"
[ -x "$PY" ] || PY="python3"

cmd_sky() {
    local sub="${1:-hud}"
    shift || true
    case "$sub" in
        hud|status)  "$PY" "$MODULE_DIR/tools/sky_cli.py" fetch_hud <<<'{}' ;;
        nws|alerts)  "$PY" "$MODULE_DIR/tools/sky_cli.py" fetch_nws <<<'{}' ;;
        metar|taf)   "$PY" "$MODULE_DIR/tools/sky_cli.py" fetch_aviation <<<'{}' ;;
        hf|space)    "$PY" "$MODULE_DIR/tools/sky_cli.py" fetch_space_weather <<<'{}' ;;
        plan)
            local act="${1:-stargazing}"
            "$PY" "$MODULE_DIR/tools/sky_cli.py" fetch_windows <<<"{\"activity\":\"$act\"}"
            ;;
        adsb)        "$PY" "$MODULE_DIR/tools/sky_cli.py" fetch_adsb <<<'{}' ;;
        *)
            echo "Usage: /sky [hud | alerts | metar | hf | plan <stargazing|drone|boating|ham_field_day> | adsb]"
            ;;
    esac
}
