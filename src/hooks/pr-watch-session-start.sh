#!/bin/sh
# SessionStart entry point for PR watch: the same check as the Stop hook, run
# when a session starts or resumes, so activity that arrived while the agent
# was idle reaches it as context. See pr-watch.py.
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd) || exit 0
command -v python3 >/dev/null 2>&1 || exit 0
exec python3 "$script_dir/pr-watch.py" --event=SessionStart "$@"
