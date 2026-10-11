#!/bin/sh
# Usage: [START=no-light] sim/run.sh OUT TOOL TARGET [FLAG...]
# Create a fresh simulated Dot, in stock fastboot or, with START=no-light,
# unplugged with boot0 erased and plugged in when the tool asks for the
# short. Run TOOL (firebreak or dot_firmware) to TARGET with FLAGs, under the
# simulator's virtualenv and with the simulator first on PATH, and leave
# OUT.log, OUT.jsonl, OUT.txt, OUT.snapshot and OUT.table.
set -u
here=$(cd "$(dirname "$0")" && pwd)
out=$1 tool=$2 target=$3
shift 3
start=${START:-fastboot}
cache=${FIREBREAK_SIM_CACHE:-$HOME/.cache/firebreak-sim-cache}
work=${FIREBREAK_SIM:-$HOME/.cache/firebreak-sim}
python3 "$here/dot.py" create --start "$start" >/dev/null || exit 1
python=$work/venv/bin/python
case $tool in
    firebreak) set -- env PYTHONPATH="$here/.." "$python" -m firebreak "$target" "$@" ;;
    dot_firmware) set -- "$python" "${DOT_FIRMWARE:?set DOT_FIRMWARE to dot_firmware.py}" "$target" "$@" ;;
    *) echo "unknown tool $tool" >&2; exit 2 ;;
esac
PATH="$here/bin:$PATH"
export PATH
[ "$(command -v adb)" = "$here/bin/adb" ] || { echo "adb is not the simulator's" >&2; exit 2; }
[ "$(command -v fastboot)" = "$here/bin/fastboot" ] || { echo "fastboot is not the simulator's" >&2; exit 2; }
: > "$out.log"
plugger=
if [ "$start" = no-light ]; then
    (
        until grep -q "Short the Dot's test point" "$out.log"; do sleep 0.5; done
        python3 "$here/dot.py" plug >/dev/null
    ) &
    plugger=$!
fi
PYTHONUNBUFFERED=1 XDG_CACHE_HOME=$cache timeout 1500 "$@" < /dev/null > "$out.log" 2>&1
status=$?
[ -n "$plugger" ] && kill "$plugger" 2>/dev/null
cp "$work/trace.jsonl" "$out.jsonl"
python3 "$here/trace.py" "$out.jsonl" > "$out.txt"
python3 "$here/dot.py" snapshot > "$out.snapshot"
python3 "$here/dot.py" table "$out.table"
echo "$tool $target: exit $status, $(grep -c '"tool"' "$out.jsonl") calls, $(grep -m1 -o 'The Dot is [a-z]*' "$out.log" || echo 'no verdict')"
exit $status
