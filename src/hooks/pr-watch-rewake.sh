#!/bin/sh
# Claude Code background watcher for PR watch: an async Stop hook with
# asyncRewake. It polls GitHub after the agent stops and exits 2, waking an
# idle session, when new review comments, CI failures or conflicts arrive.
# See pr-watch.py (--event=Rewake).
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd) || exit 0
command -v python3 >/dev/null 2>&1 || exit 0
exec python3 "$script_dir/pr-watch.py" --event=Rewake "$@"
