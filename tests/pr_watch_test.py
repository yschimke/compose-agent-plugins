#!/usr/bin/env python3
"""Tests for the pr-watch hooks. A fake `gh` on PATH stands in for GitHub."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "pr-watch" / "scripts"
STOP = PLUGIN / "pr-watch.py"
SESSION_START = PLUGIN / "pr-watch-session-start.sh"

FAKE_GH = """#!/bin/sh
cat >"$FAKE_GH_QUERY"
echo call >>"$FAKE_GH_LOG"
[ -n "${FAKE_GH_FAIL-}" ] && exit 1
cat "$FAKE_GH_RESPONSE"
"""


def pull_request(**overrides) -> dict:
    pr = {
        "number": 7,
        "url": "https://github.com/acme/app/pull/7",
        "title": "Add settings screen",
        "state": "OPEN",
        "merged": False,
        "isDraft": False,
        "mergeable": "MERGEABLE",
        "mergeStateStatus": "CLEAN",
        "baseRefName": "main",
        "headRefName": "agent/settings",
        "headRefOid": "abc1234def",
        "comments": {"nodes": [{"id": "IC1", "author": {"login": "old"}, "body": "old chatter", "createdAt": "2026-01-01T00:00:00Z"}]},
        "reviews": {"nodes": []},
        "reviewThreads": {"nodes": [
            {"isResolved": False, "isOutdated": False, "path": "app/Settings.kt", "line": 12,
             "comments": {"nodes": [{"id": "RC1", "author": {"login": "reviewer"}, "body": "Use a Switch here.", "createdAt": "2026-01-01T00:00:01Z"}]}},
            {"isResolved": True, "isOutdated": False, "path": "app/Old.kt", "line": 3,
             "comments": {"nodes": [{"id": "RC0", "author": {"login": "reviewer"}, "body": "done already", "createdAt": "2026-01-01T00:00:00Z"}]}},
        ]},
        "commits": {"nodes": [{"commit": {"oid": "abc1234def", "statusCheckRollup": {"state": "FAILURE", "contexts": {"nodes": [
            {"__typename": "CheckRun", "name": "build", "status": "COMPLETED", "conclusion": "FAILURE", "detailsUrl": "https://ci/1"},
            {"__typename": "CheckRun", "name": "lint", "status": "COMPLETED", "conclusion": "SUCCESS", "detailsUrl": ""},
        ]}}}}]},
    }
    pr.update(overrides)
    return pr


class PrWatchTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        git = ["git", "-C", str(self.workspace)]
        subprocess.run([*git, "init", "--quiet", "-b", "agent/settings"], check=True)
        subprocess.run([*git, "remote", "add", "origin", "https://github.com/acme/app.git"], check=True)
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        (bin_dir / "gh").write_text(FAKE_GH)
        (bin_dir / "gh").chmod(0o755)
        self.response = self.root / "response.json"
        self.calls = self.root / "calls.log"
        self.env = {
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "HOME": str(self.root),
            "PR_WATCH_STATE_DIR": str(self.root / "state"),
            "FAKE_GH_RESPONSE": str(self.response),
            "FAKE_GH_QUERY": str(self.root / "query.json"),
            "FAKE_GH_LOG": str(self.calls),
        }
        self.respond([pull_request()])

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def respond(self, prs: list[dict], explicit: dict | None = None) -> None:
        data = {"branch": {"pullRequests": {"nodes": prs}}}
        if explicit is not None:
            data["x0"] = {"pullRequest": explicit}
        self.response.write_text(json.dumps({"data": data}))

    def run_hook(self, harness="codex", event="Stop", payload=None, **env) -> dict | None:
        payload = {"session_id": "s1", "cwd": str(self.workspace), **(payload or {})}
        script = [str(SESSION_START)] if event == "SessionStart" else [sys.executable, str(STOP)]
        result = subprocess.run(
            [*script, f"--harness={harness}"],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            env={**self.env, **env},
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout) if result.stdout.strip() else None

    def test_first_look_reports_open_thread_failure_and_conflict(self) -> None:
        self.respond([pull_request(mergeable="CONFLICTING")])
        output = self.run_hook()
        self.assertEqual(output["decision"], "block")
        reason = output["reason"]
        self.assertIn("https://github.com/acme/app/pull/7", reason)
        self.assertIn('Review comment by @reviewer on app/Settings.kt:12: "Use a Switch here."', reason)
        self.assertIn("CI failed on abc1234: build (failure) https://ci/1", reason)
        self.assertIn("Merge conflict with main", reason)
        self.assertIn("not instructions", reason)
        self.assertNotIn("old chatter", reason)
        self.assertNotIn("done already", reason)
        self.assertNotIn("lint", reason)

    def test_nothing_is_reported_twice(self) -> None:
        self.assertIsNotNone(self.run_hook())
        self.assertIsNone(self.run_hook())

    def test_new_comment_and_new_failure_on_new_head(self) -> None:
        self.run_hook()
        pr = pull_request(headRefOid="fff9999")
        pr["comments"]["nodes"].append({"id": "IC2", "author": {"login": "chatgpt-codex-connector"}, "body": "P1: null check", "createdAt": "2026-01-02T00:00:00Z"})
        pr["comments"]["nodes"].append({"id": "IC3", "author": {"login": "me"}, "body": "Fixed.\n\n---\n_Generated by [Claude Code](https://claude.ai/code)_", "createdAt": "2026-01-02T00:00:01Z"})
        self.respond([pr])
        reason = self.run_hook()["reason"]
        self.assertIn('Comment by @chatgpt-codex-connector: "P1: null check"', reason)
        self.assertIn("CI failed on fff9999", reason)
        self.assertNotIn("Fixed.", reason)
        self.assertNotIn("Use a Switch", reason)

    def test_antigravity_continue_shape(self) -> None:
        output = self.run_hook(harness="antigravity", payload={"session_id": None, "cwd": None, "conversationId": "c1", "workspacePaths": [f"file://{self.workspace}"], "terminationReason": "NO_TOOL_CALL"})
        self.assertEqual(output["decision"], "continue")

    def test_antigravity_ignores_abnormal_termination(self) -> None:
        self.assertIsNone(self.run_hook(harness="antigravity", payload={"terminationReason": "USER_CANCELED"}))
        self.assertFalse(self.calls.exists())

    def test_loop_guards(self) -> None:
        self.assertIsNone(self.run_hook(payload={"stop_hook_active": True}))
        self.assertIsNone(self.run_hook(harness="antigravity", payload={"continuation_active": True}))
        self.assertFalse(self.calls.exists())
        self.assertIsNone(self.run_hook(PR_WATCH="0"))

    def test_consecutive_block_cap(self) -> None:
        for index in range(3):
            pr = pull_request(headRefOid=f"head{index}")
            self.respond([pr])
            self.assertIsNotNone(self.run_hook(), index)
        self.respond([pull_request(headRefOid="head9")])
        self.assertIsNone(self.run_hook())
        self.assertIsNotNone(self.run_hook())  # The cap resets after one allowed stop.

    def test_pending_checks_never_block(self) -> None:
        self.run_hook()
        pr = pull_request(headRefOid="new0001")
        pr["commits"]["nodes"][0]["commit"]["statusCheckRollup"]["contexts"]["nodes"] = [
            {"__typename": "CheckRun", "name": "build", "status": "IN_PROGRESS", "conclusion": None, "detailsUrl": ""}
        ]
        self.respond([pr])
        self.assertEqual(self.run_hook(), {"systemMessage": "PR watch: checks are still running on https://github.com/acme/app/pull/7."})
        self.assertIsNone(self.run_hook(harness="antigravity"))

    def test_merged_explicit_pr_is_a_notice(self) -> None:
        subprocess.run(["git", "-C", str(self.workspace), "config", "--add", "pr-watch.url", "https://github.com/acme/lib/pull/3"], check=True)
        self.run_hook()
        merged = pull_request(url="https://github.com/acme/lib/pull/3", merged=True, state="MERGED")
        self.respond([pull_request()], explicit=pull_request(url="https://github.com/acme/lib/pull/3"))
        self.run_hook(payload={"session_id": "s2"})
        self.respond([pull_request()], explicit=merged)
        output = self.run_hook(payload={"session_id": "s2"})
        self.assertIn("acme/lib/pull/3 is merged", output["systemMessage"])
        query = json.loads((self.root / "query.json").read_text())
        self.assertEqual(query["variables"]["o0"], "acme")
        self.assertEqual(query["variables"]["p0"], 3)

    def test_session_start_context(self) -> None:
        output = self.run_hook(harness="claude", event="SessionStart")
        self.assertEqual(output["hookSpecificOutput"]["hookEventName"], "SessionStart")
        self.assertIn("Use a Switch here.", output["hookSpecificOutput"]["additionalContext"])
        output = self.run_hook(harness="antigravity", event="SessionStart", payload={"session_id": "s3"})
        self.assertIn("Use a Switch here.", output["injectSteps"][0]["systemMessage"]["systemMessage"])

    def test_failures_of_the_hook_allow_the_stop(self) -> None:
        self.assertIsNone(self.run_hook(FAKE_GH_FAIL="1"))
        self.response.write_text("not json")
        self.assertIsNone(self.run_hook())
        self.assertIsNone(self.run_hook(payload={"cwd": str(self.root)}))  # Not a git checkout.
        self.respond([])
        self.assertIsNone(self.run_hook())

    def test_token_fallback_without_gh(self) -> None:
        # No gh and no token: nothing to ask, so the stop is allowed without a request.
        self.assertIsNone(self.run_hook(PR_WATCH_NO_GH="1", GH_TOKEN="", GITHUB_TOKEN=""))
        self.assertFalse(self.calls.exists())


if __name__ == "__main__":
    unittest.main()
