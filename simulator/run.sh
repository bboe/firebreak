#!/bin/sh
# Usage: [START=no-light] simulator/run.sh OUT TOOL TARGET [FLAG...]
# Create a fresh simulated Dot, in stock fastboot or, with START=no-light,
# unplugged with boot0 erased and plugged in when the tool asks for the
# short. Run TOOL (firebreak or dot_firmware) to TARGET with FLAGs, under the
# simulator's virtualenv and with the simulator first on PATH, and leave
# OUT.log, OUT.jsonl, OUT.txt, OUT.snapshot and OUT.table. Destroy the Dot
# on exit, Ctrl-C included.
set -u
here=$(cd "$(dirname "$0")" && pwd)
out=$1 tool=$2 target=$3
shift 3
start=${START:-fastboot}
cache=${FIREBREAK_SIM_CACHE:-$HOME/.cache/firebreak-sim-cache}
work=${FIREBREAK_SIM:-$HOME/.cache/firebreak-sim}
plugger='' runner=''
finish() {
    [ -n "$plugger" ] && kill "$plugger" 2>/dev/null
    [ -n "$runner" ] && kill "$runner" 2>/dev/null
    [ -n "$plugger" ] && wait "$plugger"
    [ -n "$runner" ] && wait "$runner"
    python3 "$here/dot.py" destroy
}
trap finish EXIT
trap 'exit 130' HUP INT QUIT TERM
python3 "$here/dot.py" create --runner $$ --start "$start" >/dev/null || exit 1
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
command -v timeout >/dev/null || { echo "run.sh needs timeout (coreutils)" >&2; exit 2; }
"$python" -c 'import sys; sys.exit(not any(type(f).__module__ == "firebreak_sim_ports" for f in sys.meta_path))' \
    || { echo "the virtualenv's port hook is not active" >&2; exit 2; }
: > "$out.log"
if [ "$start" = no-light ]; then
    (
        trap 'exit 0' TERM
        until grep -q "Short the Dot's test point" "$out.log"; do sleep 0.5; done
        python3 "$here/dot.py" plug >/dev/null
    ) &
    plugger=$!
fi
PYTHONUNBUFFERED=1 XDG_CACHE_HOME=$cache timeout 1500 "$@" < /dev/null > "$out.log" 2>&1 &
runner=$!
wait "$runner"
status=$?
runner=
[ -n "$plugger" ] && kill "$plugger" 2>/dev/null && wait "$plugger"
plugger=
python3 "$here/dot.py" halt
cp "$work/trace.jsonl" "$out.jsonl"
python3 "$here/trace.py" "$out.jsonl" > "$out.txt"
python3 "$here/dot.py" snapshot > "$out.snapshot"
python3 "$here/dot.py" table "$out.table"
echo "$tool $target: exit $status, $(grep -c '"tool"' "$out.jsonl") calls, $(grep -m1 -o 'The Dot is [a-z]*' "$out.log" || echo 'no verdict')"
exit $status
