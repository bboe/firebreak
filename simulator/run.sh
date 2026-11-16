#!/bin/sh
# Usage: [DEVICE=radar|donut] [START=no-light|twrp|stock-booted|fireos5] simulator/run.sh OUT TARGET [FLAG...]
# Create a fresh simulated Dot, or with DEVICE=radar an Echo (2nd
# Generation) and with DEVICE=donut an Echo Dot (3rd Generation), whose
# button is held into its bootrom when firebreak asks, in stock fastboot or,
# with START=no-light,
# unplugged with boot0 erased and plugged in when firebreak asks for the
# short. START=twrp starts it unlocked with amonet v2, in that TWRP, and
# START=stock-booted starts the stock Fire OS, which answers no adb.
# START=fireos5 runs `unlock fireos5` first, into OUT.fireos5.log, then gives
# that rooted Fire OS 5.5.5.4 a setup to keep and restarts it.
# Run firebreak to TARGET with FLAGs, under the simulator's
# virtualenv and with the simulator first on PATH, and leave
# OUT.log, OUT.jsonl, OUT.txt, OUT.snapshot and OUT.table. Destroy the Dot
# on exit, Ctrl-C included. FIREBREAK_SIM_SPEED runs the clock that many
# times faster; 1 is real time.
set -u
here=$(cd "$(dirname "$0")" && pwd)
out=$1 target=$2
shift 2
device=${DEVICE:-biscuit}
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
FIREBREAK_SIM_SPEED=${FIREBREAK_SIM_SPEED:-20}
export FIREBREAK_SIM_SPEED
created=$start
[ "$start" = fireos5 ] && created=fastboot
python3 "$here/dot.py" create --device "$device" --runner $$ --start "$created" >/dev/null || exit 1
python=$work/venv/bin/python
PATH="$here/bin:$PATH"
export PATH
[ "$(command -v adb)" = "$here/bin/adb" ] || { echo "adb is not the simulator's" >&2; exit 2; }
[ "$(command -v fastboot)" = "$here/bin/fastboot" ] || { echo "fastboot is not the simulator's" >&2; exit 2; }
command -v timeout >/dev/null || { echo "run.sh needs timeout (coreutils)" >&2; exit 2; }
"$python" -c 'import sys; sys.exit(not any(type(f).__module__ == "firebreak_sim_ports" for f in sys.meta_path))' \
    || { echo "the virtualenv's port hook is not active" >&2; exit 2; }
if [ "$start" = fireos5 ]; then
    PYTHONUNBUFFERED=1 XDG_CACHE_HOME=$cache timeout 1500 env PYTHONPATH="$here/.." \
        "$python" -m firebreak unlock fireos5 --no-update-check < /dev/null > "$out.fireos5.log" 2>&1 \
        || { echo "unlock fireos5 failed: see $out.fireos5.log" >&2; exit 1; }
    "$python" "$here/dot.py" register >/dev/null || exit 1
fi
set -- env PYTHONPATH="$here/.." "$python" -m firebreak "$target" --no-update-check "$@"
: > "$out.log"
if [ "$start" = no-light ] || [ "$device" = donut ]; then
    (
        trap 'exit 0' TERM
        until grep -qE "test point and plug it in|start it in its bootrom|on USB. Connect it|Waiting for an Echo to appear" "$out.log"; do sleep 0.5; done
        "$python" "$here/dot.py" plug >/dev/null
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
"$python" "$here/dot.py" halt
cp "$work/trace.jsonl" "$out.jsonl"
python3 "$here/trace.py" "$out.jsonl" > "$out.txt"
"$python" "$here/dot.py" snapshot > "$out.snapshot"
"$python" "$here/dot.py" table "$out.table"
echo "$target: exit $status, $(grep -c '"tool"' "$out.jsonl") calls, $(grep -m1 -oE '[Tt]he Echo[A-Za-z0-9 ()]* (is [a-z]*|runs [a-z]* [0-9.]*|runs its firmware, read as [A-Za-z0-9 -]*|(already )?waits in its bootrom)' "$out.log" || echo 'no verdict')"
exit $status
