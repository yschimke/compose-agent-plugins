#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repository_root"

python3 scripts/check-release.py
python3 scripts/generate.py
python3 scripts/check_generated.py

while IFS= read -r -d '' json_file; do
  python3 -m json.tool "$json_file" >/dev/null
done < <(find . -name '*.json' -not -path './.git/*' -print0)

python3 scripts/validate_manifests.py
python3 tests/validate_manifests_test.py
python3 tests/onboarding_skill_test.py
python3 tests/app_manifest_test.py
python3 tests/release_test.py
tests/harness_test.sh
tests/session_start_summary_test.sh
tests/compose_edit_reminder_test.sh
tests/stop_gate_test.sh
python3 tests/viewer_asset_test.py
python3 tests/card_helper_test.py
python3 tests/antigravity_install_test.py
python3 tests/echo_mcp_test.py
python3 tests/spike_fixture_test.py
python3 tests/opencode_install_test.py
node --test tests/opencode_plugin_test.mjs
