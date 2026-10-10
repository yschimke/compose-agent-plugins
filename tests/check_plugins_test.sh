#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
temporary_root="$(mktemp -d)"
fixture="$temporary_root/repository"
trap 'rm -rf "$temporary_root"' EXIT

mkdir "$fixture"
tar -C "$repository_root" --exclude=.git -cf - . | tar -C "$fixture" -xf -
git -C "$fixture" init --quiet
git -C "$fixture" config user.email test@example.invalid
git -C "$fixture" config user.name 'Plugin test'
git -C "$fixture" add .
git -C "$fixture" commit --quiet -m 'test fixture'

touch "$fixture/unrelated-user-note.txt"
"$fixture/scripts/check-plugins.sh"

# A removed Codex skill must be committed as a generated deletion too.
python3 - "$fixture/src/plugins.json" <<'PYTEST'
import json
import sys
from pathlib import Path
p = Path(sys.argv[1])
data = json.loads(p.read_text())
plugin = next(p for p in data["plugins"] if p["name"] == "compose-preview")
plugin["codexSkills"].remove("harness-notes")
p.write_text(json.dumps(data, indent=2) + "\n")
PYTEST
python3 "$fixture/scripts/generate.py"
git -C "$fixture" add src/plugins.json plugins/compose-preview/.codex-plugin/plugin.json
git -C "$fixture" commit --quiet -m 'omit generated skill deletion'
if python3 "$fixture/scripts/check_generated.py" >"$temporary_root/codex-drift.out" 2>"$temporary_root/codex-drift.err"; then
  printf '%s\n' 'FAIL: omitted Codex skill deletion must fail drift check' >&2
  exit 1
fi
grep -q 'missing generated files:.*.codex-plugin/skills/harness-notes/SKILL.md' "$temporary_root/codex-drift.err"
git -C "$fixture" reset --hard --quiet HEAD^

python3 -c '
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
# Claude Code takes the token from a sensitive userConfig option, never the environment (#53).
for relative, key, expected in (
    ("plugins/compose-catalogs/.mcp.json", "mcpServers", "${user_config.compose_preview_token}"),
    ("plugins/compose-catalogs/mcp_config.json", "mcpServers", "${COMPOSE_PREVIEW_TOKEN:-}"),
    ("plugins/compose-catalogs/.cursor-plugin/plugin.json", "mcpServers", "${COMPOSE_PREVIEW_TOKEN}"),
    ("gemini-extension.json", "mcpServers", "${COMPOSE_PREVIEW_TOKEN}"),
):
    data = json.loads((root / relative).read_text(encoding="utf-8"))
    actual = data[key]["compose-preview-catalog"]["headers"]["X-Compose-Preview-Token"]
    if actual != expected:
        raise SystemExit(f"{relative}: expected {expected!r}, got {actual!r}")
claude = json.loads((root / "plugins/compose-catalogs/.claude-plugin/plugin.json").read_text(encoding="utf-8"))
if claude["userConfig"]["compose_preview_token"].get("sensitive") is not True:
    raise SystemExit(f"Claude userConfig token must be sensitive: {claude!r}")
gemini = json.loads((root / "gemini-extension.json").read_text(encoding="utf-8"))
if [setting["envVar"] for setting in gemini["settings"]] != ["COMPOSE_PREVIEW_TOKEN"]:
    raise SystemExit(f"Gemini must declare the token variable: {gemini!r}")
' "$fixture"

cp "$fixture/src/plugins.json" "$fixture/src/plugins.json.valid-claude-headers"
python3 -c '
import json
import sys
from pathlib import Path

source = Path(sys.argv[1])
data = json.loads(source.read_text(encoding="utf-8"))
catalog = next(plugin for plugin in data["plugins"] if plugin["name"] == "compose-catalogs")
catalog["mcp"][0].pop("userConfigHeaders")
source.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
' "$fixture/src/plugins.json"
if python3 "$fixture/scripts/generate.py" >"$fixture/missing-claude-header.out" 2>"$fixture/missing-claude-header.err"; then
  printf '%s\n' 'FAIL: remote headers require a Claude userConfig mapping' >&2
  exit 1
fi
grep -q 'userConfigHeaders must cover the same headers as headers' "$fixture/missing-claude-header.err"
mv "$fixture/src/plugins.json.valid-claude-headers" "$fixture/src/plugins.json"

python3 -c '
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
manifest = json.loads(
    (root / "plugins/compose-catalogs/.codex-plugin/plugin.json").read_text(encoding="utf-8")
)
server = manifest["mcpServers"]["compose-preview-catalog"]
expected = {"X-Compose-Preview-Token": "COMPOSE_PREVIEW_TOKEN"}
if server.get("env_http_headers") != expected:
    raise SystemExit(f"Codex env_http_headers: expected {expected!r}, got {server!r}")
if "headers" in server or "http_headers" in server:
    raise SystemExit(f"Codex manifest must not embed a literal token header: {server!r}")
' "$fixture"

cp "$fixture/src/plugins.json" "$fixture/src/plugins.json.valid-codex-headers"
python3 -c '
import json
import sys
from pathlib import Path

source = Path(sys.argv[1])
data = json.loads(source.read_text(encoding="utf-8"))
catalog = next(plugin for plugin in data["plugins"] if plugin["name"] == "compose-catalogs")
catalog["mcp"][0].pop("envHeaders")
source.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
' "$fixture/src/plugins.json"
if python3 "$fixture/scripts/generate.py" >"$fixture/missing-codex-header.out" 2>"$fixture/missing-codex-header.err"; then
  printf '%s\n' 'FAIL: remote headers require a Codex environment mapping' >&2
  exit 1
fi
grep -q 'envHeaders must cover the same headers as headers' "$fixture/missing-codex-header.err"
mv "$fixture/src/plugins.json.valid-codex-headers" "$fixture/src/plugins.json"
python3 "$fixture/scripts/generate.py"

cp "$fixture/src/plugins.json" "$fixture/src/plugins.json.valid-version"
for invalid_version in next '1.2.3٣'; do
  cp "$fixture/src/plugins.json.valid-version" "$fixture/src/plugins.json"
  python3 -c '
import json
import sys
from pathlib import Path

source = Path(sys.argv[1])
data = json.loads(source.read_text(encoding="utf-8"))
data["plugins"][0]["version"] = sys.argv[2]
source.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
' "$fixture/src/plugins.json" "$invalid_version"
  if python3 "$fixture/scripts/generate.py" >"$fixture/invalid-version.out" 2>"$fixture/invalid-version.err"; then
    printf '%s\n' "FAIL: non-semver Codex plugin version $invalid_version must fail generation" >&2
    exit 1
  fi
  grep -q 'version must use strict semver' "$fixture/invalid-version.err"
done
mv "$fixture/src/plugins.json.valid-version" "$fixture/src/plugins.json"

cp "$fixture/src/plugins.json" "$fixture/src/plugins.json.valid-interface"
for invalid_interface_field in displayName capability defaultPrompt; do
  cp "$fixture/src/plugins.json.valid-interface" "$fixture/src/plugins.json"
  python3 -c '
import json
import sys
from pathlib import Path

source = Path(sys.argv[1])
field = sys.argv[2]
data = json.loads(source.read_text(encoding="utf-8"))
interface = data["plugins"][0]["interface"]
if field == "capability":
    interface["capabilities"][0] = "   "
elif field == "defaultPrompt":
    interface["defaultPrompt"][0] = "   "
else:
    interface[field] = "   "
source.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
' "$fixture/src/plugins.json" "$invalid_interface_field"
  if python3 "$fixture/scripts/generate.py" >"$fixture/invalid-interface.out" 2>"$fixture/invalid-interface.err"; then
    printf '%s\n' "FAIL: whitespace-only Codex interface field $invalid_interface_field must fail generation" >&2
    exit 1
  fi
  grep -q 'must be a non-empty string' "$fixture/invalid-interface.err"
done
mv "$fixture/src/plugins.json.valid-interface" "$fixture/src/plugins.json"

# design-reviewer ships once, in compose-preview (#34); a second copy is a duplicate Claude Code agent.
if test -e "$fixture/plugins/compose-catalogs/agents/design-reviewer.md"; then
  printf '%s\n' 'FAIL: design-reviewer must ship only in compose-preview' >&2
  exit 1
fi
for plugin in compose-preview; do
  reviewer="$fixture/plugins/$plugin/agents/design-reviewer.md"
  test -f "$reviewer"
  grep -q '^name: design-reviewer$' "$reviewer"
  grep -Fq '"Bash(gh pr view:*)"' "$reviewer"
  grep -Fq '"Bash(gh pr comment:*)"' "$reviewer"
  grep -Fq '"Bash(gh issue view:*)"' "$reviewer"
  grep -Fq '"Bash(gh issue comment:*)"' "$reviewer"
  if grep -Eq '"(Bash|Edit|Write)"' "$reviewer"; then
    printf '%s\n' 'FAIL: reviewer must not receive unrestricted mutation tools' >&2
    exit 1
  fi
done

hook="$fixture/plugins/compose-preview/hooks/hooks.json"
test -f "$hook"
grep -q '"SessionStart"' "$hook"
grep -q 'session-start-summary.sh' "$hook"
python3 -c '
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
for harness, name in (("claude", "hooks.json"), ("codex", "codex-hooks.json")):
    hooks = json.loads((root / "hooks" / name).read_text(encoding="utf-8"))["hooks"]
    entry = hooks["SessionStart"][0]
    assert entry["matcher"] == "startup", entry
    assert entry["hooks"][0]["timeout"] == 10, entry
    # Every generated command names its harness explicitly (#9).
    for entries in hooks.values():
        for group in entries:
            for hook in group["hooks"]:
                assert hook["command"].endswith(f" --harness={harness}"), hook
codex = json.loads((root / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
assert codex["hooks"] == "./hooks/codex-hooks.json", codex
# Antigravity gets only the Stop gate (it has no SessionStart), from its
# installed copy, with its own --harness (#9, #39).
antigravity = json.loads((root / "hooks.json").read_text(encoding="utf-8"))
assert antigravity == {
    "compose-preview": {
        "enabled": True,
        "Stop": [
            {
                "command": "\"$HOME/.gemini/config/plugins/compose-preview/scripts/stop-gate.sh\" --harness=antigravity",
                "type": "command",
            }
        ],
    }
}, antigravity
' "$(dirname "$(dirname "$hook")")"

# The hook generator is event-generic so the future opt-in Stop gate can use
# the same source-of-truth rather than bypassing generated manifests.
cp "$fixture/src/plugins.json" "$fixture/src/plugins.json.before-stop"
printf '%s\n' '#!/bin/sh' 'exit 0' >"$fixture/src/hooks/future-stop.sh"
chmod +x "$fixture/src/hooks/future-stop.sh"
python3 -c '
import json
import sys
from pathlib import Path

source = Path(sys.argv[1])
data = json.loads(source.read_text(encoding="utf-8"))
preview = next(plugin for plugin in data["plugins"] if plugin["name"] == "compose-preview")
preview["hooks"].append({"event": "Stop", "command": "scripts/future-stop.sh", "timeout": 15})
source.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
' "$fixture/src/plugins.json"
python3 "$fixture/scripts/generate.py"
python3 -c '
import json
import sys
from pathlib import Path

for harness, name in (("claude", "hooks.json"), ("codex", "codex-hooks.json")):
    hooks = json.loads((Path(sys.argv[1]) / name).read_text(encoding="utf-8"))["hooks"]
    assert hooks["Stop"][-1]["hooks"][0] == {
        "command": f"\"${{CLAUDE_PLUGIN_ROOT}}/scripts/future-stop.sh\" --harness={harness}",
        "timeout": 15,
        "type": "command",
    }, hooks
' "$(dirname "$hook")"
test -x "$fixture/plugins/compose-preview/scripts/future-stop.sh"
mv "$fixture/src/plugins.json.before-stop" "$fixture/src/plugins.json"
rm "$fixture/src/hooks/future-stop.sh"
python3 "$fixture/scripts/generate.py"
test ! -e "$fixture/plugins/compose-preview/scripts/future-stop.sh"

viewer_source="$fixture/src/assets/compose-preview-viewer.html"
viewer_asset="$fixture/plugins/compose-preview/assets/compose-preview-viewer.html"
fallback_asset="$fixture/plugins/compose-preview/assets/compose-preview-viewer-fallback.md"
provenance_source="$fixture/src/assets/compose-preview-viewer.provenance.json"
provenance_asset="$fixture/plugins/compose-preview/assets/compose-preview-viewer.provenance.json"
cmp "$viewer_source" "$viewer_asset"
grep -q "ui/notifications/tool-result" "$viewer_asset"
grep -q "ui/update-model-context" "$viewer_asset"
grep -q "protocolVersion: '2026-01-26'" "$viewer_asset"
grep -q "MAX_STATIC_RESULT_BYTES = 500000" "$viewer_asset"
test -f "$fallback_asset"
cmp "$fixture/src/assets/compose-preview-card.py" "$fixture/plugins/compose-preview/assets/compose-preview-card.py"
grep -q '#compose-preview-result=<unpadded-base64url-envelope>' "$fallback_asset"
grep -q 'Text fallback' "$fallback_asset"
cmp "$provenance_source" "$provenance_asset"
grep -q 'd5f6b776872dd70a29653a6e2712bdce1eecd961cea53b75d23c6a32a7afe221' "$provenance_asset"
test -f "$fixture/plugins/compose-preview/skills/antigravity-viewer-card/SKILL.md"
test ! -e "$fixture/plugins/compose-catalogs/skills/antigravity-viewer-card/SKILL.md"

stale_asset="$fixture/plugins/compose-preview/assets/obsolete-viewer.html"
printf '%s\n' '<!doctype html>' >"$stale_asset"
if python3 "$fixture/scripts/check_generated.py" >"$fixture/stale-asset.out" 2>"$fixture/stale-asset.err"; then
  printf '%s\n' 'expected stale generated asset check to fail' >&2
  exit 1
fi
grep -q 'compose-preview has stale generated assets: obsolete-viewer.html' "$fixture/stale-asset.err"
rm "$stale_asset"

cp "$fixture/src/plugins.json" "$fixture/src/plugins.json.assets-saved"
python3 -c '
import json
import sys
from pathlib import Path

source = Path(sys.argv[1])
data = json.loads(source.read_text(encoding="utf-8"))
plugin = next(plugin for plugin in data["plugins"] if plugin["name"] == "compose-preview")
plugin["assets"].remove("compose-preview-viewer.html")
source.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
' "$fixture/src/plugins.json"
python3 "$fixture/scripts/generate.py"
if test -e "$viewer_asset"; then
  printf '%s\n' 'FAIL: generator must remove assets listed in its previous ledger' >&2
  exit 1
fi
test -f "$fallback_asset"
mv "$fixture/src/plugins.json.assets-saved" "$fixture/src/plugins.json"
python3 "$fixture/scripts/generate.py"
cmp "$viewer_source" "$viewer_asset"

cp "$fixture/src/plugins.json" "$fixture/src/plugins.json.all-assets-saved"
python3 -c '
import json
import sys
from pathlib import Path

source = Path(sys.argv[1])
data = json.loads(source.read_text(encoding="utf-8"))
next(plugin for plugin in data["plugins"] if plugin["name"] == "compose-preview")["assets"] = []
source.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
' "$fixture/src/plugins.json"
python3 "$fixture/scripts/generate.py"
test ! -e "$fixture/plugins/compose-preview/assets/.generated-assets.json"
if python3 "$fixture/scripts/check_generated.py" >"$fixture/deleted-assets.out" 2>"$fixture/deleted-assets.err"; then
  printf '%s\n' 'FAIL: deleting the final generated assets and ledger must fail the drift check' >&2
  exit 1
fi
grep -q 'generated files differ from their checked-out versions' "$fixture/deleted-assets.err"
mv "$fixture/src/plugins.json.all-assets-saved" "$fixture/src/plugins.json"
python3 "$fixture/scripts/generate.py"
cmp "$viewer_source" "$viewer_asset"

stale_hook="$fixture/plugins/compose-preview/scripts/obsolete-hook.sh"
printf '%s\n' '#!/bin/sh' 'exit 0' >"$stale_hook"
if "$fixture/scripts/check-plugins.sh" >"$fixture/stale-hook.out" 2>"$fixture/stale-hook.err"; then
  printf '%s\n' 'expected stale generated hook check to fail' >&2
  exit 1
fi
grep -q 'compose-preview has stale generated hooks: obsolete-hook.sh' "$fixture/stale-hook.err"
rm "$stale_hook"

cp "$fixture/src/plugins.json" "$fixture/src/plugins.json.saved"
python3 -c '
import json
import sys
from pathlib import Path

source = Path(sys.argv[1])
data = json.loads(source.read_text(encoding="utf-8"))
next(plugin for plugin in data["plugins"] if plugin["name"] == "compose-preview")["hooks"] = []
source.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
' "$fixture/src/plugins.json"
python3 "$fixture/scripts/generate.py"
if test -e "$fixture/plugins/compose-preview/scripts/session-start-summary.sh"; then
  printf '%s\n' 'FAIL: generator must remove scripts from its previous hook manifest' >&2
  exit 1
fi
test ! -e "$fixture/plugins/compose-preview/hooks/hooks.json"
test ! -e "$fixture/plugins/compose-preview/hooks/codex-hooks.json"
test ! -e "$fixture/plugins/compose-preview/hooks.json"
if grep -q '"hooks"' "$fixture/plugins/compose-preview/.codex-plugin/plugin.json"; then
  printf '%s\n' 'FAIL: Codex manifest must not name a removed hook manifest' >&2
  exit 1
fi
if python3 "$fixture/scripts/check_generated.py" >"$fixture/deleted-hook.out" 2>"$fixture/deleted-hook.err"; then
  printf '%s\n' 'FAIL: deleted generated hooks must fail the drift check' >&2
  exit 1
fi
grep -q 'generated files differ from their checked-out versions' "$fixture/deleted-hook.err"
mv "$fixture/src/plugins.json.saved" "$fixture/src/plugins.json"
python3 "$fixture/scripts/generate.py"

handwritten_agent="$fixture/plugins/compose-preview/agents/handwritten-reviewer.md"
printf '%s\n' 'handwritten' >"$handwritten_agent"
python3 -c '
import json
import sys
from pathlib import Path

source = Path(sys.argv[1])
data = json.loads(source.read_text(encoding="utf-8"))
next(plugin for plugin in data["plugins"] if plugin["name"] == "compose-preview")["agents"] = []
source.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
' "$fixture/src/plugins.json"
python3 "$fixture/scripts/generate.py"
if test -e "$fixture/plugins/compose-preview/agents/design-reviewer.md"; then
  printf '%s\n' 'FAIL: generator must remove agents recorded in its ledger' >&2
  exit 1
fi
if ! test -e "$handwritten_agent"; then
  printf '%s\n' 'FAIL: generator must preserve hand-written agents absent from its ledger' >&2
  exit 1
fi

mkdir "$fixture/plugins/stale-plugin"
if "$fixture/scripts/check-plugins.sh" >/dev/null 2>&1; then
  printf '%s\n' 'FAIL: stale plugin directory must fail generated drift check' >&2
  exit 1
fi
rmdir "$fixture/plugins/stale-plugin"

git -C "$fixture" rm --cached --quiet -r plugins/compose-preview
if "$fixture/scripts/check-plugins.sh" >/dev/null 2>&1; then
  printf '%s\n' 'FAIL: untracked generated plugin files must fail generated drift check' >&2
  exit 1
fi

printf '%s\n' 'plugin drift tests passed'
