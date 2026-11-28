#!/usr/bin/env python3
"""Tests for the pr-watch hooks. A fake `gh` on PATH stands in for GitHub."""
from __future__ import annotations

import json
import os
import re
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
echo "$*" >>"$FAKE_GH_LOG"
[ -n "${FAKE_GH_FAIL-}" ] && exit 1
if [ "$2" = graphql ]; then
  cat >"$FAKE_GH_QUERY"
  [ -n "${FAKE_GH_GRAPHQL_FAIL-}" ] && { echo 'GraphQL is not available' >&2; exit 1; }
  cat "$FAKE_GH_RESPONSE"
  exit 0
fi
file="$FAKE_REST_DIR/$(printf '%s' "$2" | tr -c 'A-Za-z0-9' '_')"
[ -f "$file" ] || { echo "no fixture for $2" >&2; exit 1; }
cat "$file"
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
        "headRepository": {"nameWithOwner": "acme/app"},
        "baseRepository": {"nameWithOwner": "acme/app"},
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
            "FAKE_REST_DIR": str(self.root / "rest"),
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
        self.assertIn("Merge conflict with acme/app's main: fetch main from the pull request's base repository", reason)
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

    # --- Output budget (deferred, never dropped) -----------------------------

    def busy_pull_request(self, number: int, count: int, body_length: int = 290) -> dict:
        pr = pull_request(number=number, url=f"https://github.com/acme/app/pull/{number}")
        pr["reviewThreads"]["nodes"] = [
            {"isResolved": False, "isOutdated": False, "path": f"app/F{index}.kt", "line": 1,
             "comments": {"nodes": [{"id": f"P{number}C{index}", "author": {"login": "reviewer"},
                                     "body": f"pr{number}-comment{index} " + "x" * body_length,
                                     "createdAt": f"2026-01-01T00:00:{index:02d}Z"}]}}
            for index in range(count)
        ]
        pr["commits"]["nodes"][0]["commit"]["statusCheckRollup"]["contexts"]["nodes"] = []
        return pr

    def test_comments_over_the_per_pr_limit_follow_next_stop(self) -> None:
        self.respond([self.busy_pull_request(7, 10, body_length=10)])
        first = self.run_hook()["reason"]
        self.assertIn("pr7-comment7 ", first)
        self.assertNotIn("pr7-comment8 ", first)
        self.assertIn("2 more comments will follow at the next stop", first)
        second = self.run_hook(payload={"stop_hook_active": False})["reason"]
        self.assertIn("pr7-comment8 ", second)
        self.assertIn("pr7-comment9 ", second)
        self.assertNotIn("pr7-comment0 ", second)
        self.assertIsNone(self.run_hook())

    def test_pull_requests_over_the_budget_follow_next_stop(self) -> None:
        # Codex review example on #213: three PRs, eight 300-character comments each.
        prs = [self.busy_pull_request(number, 8) for number in (7, 8, 9)]
        subprocess.run(["git", "-C", str(self.workspace), "config", "--add", "pr-watch.url",
                        "https://github.com/acme/app/pull/9"], check=True)
        self.respond(prs[:2], explicit=prs[2])
        first = self.run_hook()["reason"]
        self.assertIn("more pull request(s) will follow at the next stop.", first)
        reasons = [first]
        while True:
            output = self.run_hook()
            if output is None:
                break
            reasons.append(output["reason"])
            self.assertLessEqual(len(reasons), 3)
        reported = "\n".join(reasons)
        for number in (7, 8, 9):
            for index in range(8):
                self.assertEqual(reported.count(f"pr{number}-comment{index} "), 1, (number, index))

    # --- REST fallback -------------------------------------------------------

    def rest_fixture(self, path: str, value: object) -> None:
        directory = self.root / "rest"
        directory.mkdir(exist_ok=True)
        (directory / re.sub(r"[^A-Za-z0-9]", "_", path)).write_text(json.dumps(value))

    def rest_pull_request(self, sha="abc1234def", mergeable_state="dirty", state="open", merged=False) -> None:
        repo = "repos/acme/app"
        self.rest_fixture(f"{repo}/pulls?state=open&head=acme:agent%2Fsettings&per_page=100", [{"number": 7}])
        self.rest_fixture(f"{repo}/pulls/7", {
            "number": 7, "html_url": "https://github.com/acme/app/pull/7", "title": "Add settings screen",
            "state": state, "merged": merged, "draft": False, "mergeable": mergeable_state != "dirty",
            "mergeable_state": mergeable_state, "base": {"ref": "main", "repo": {"full_name": "acme/app"}},
            "head": {"ref": "agent/settings", "sha": sha},
        })
        self.rest_fixture(f"{repo}/issues/7/comments?per_page=100", [
            {"node_id": "IC1", "user": {"login": "old"}, "body": "old chatter", "created_at": "2026-01-01T00:00:00Z"},
        ])
        self.rest_fixture(f"{repo}/pulls/7/reviews?per_page=100", [])
        self.rest_fixture(f"{repo}/pulls/7/comments?per_page=100", [
            {"id": 1, "node_id": "RC1", "user": {"login": "reviewer"}, "body": "Use a Switch here.",
             "path": "app/Settings.kt", "line": 12, "created_at": "2026-01-01T00:00:01Z"},
            {"id": 2, "node_id": "RC0", "user": {"login": "reviewer"}, "body": "outdated note",
             "path": "app/Old.kt", "line": None, "created_at": "2026-01-01T00:00:00Z"},
        ])
        self.rest_fixture(f"{repo}/commits/{sha}/check-runs?per_page=100", {"total_count": 2, "check_runs": [
            {"name": "build", "status": "completed", "conclusion": "failure", "details_url": "https://ci/1"},
            {"name": "lint", "status": "completed", "conclusion": "success", "details_url": ""},
        ]})
        self.rest_fixture(f"{repo}/commits/{sha}/statuses?per_page=100", [
            {"context": "deploy/preview", "state": "error", "target_url": "https://preview/1"},
            {"context": "deploy/preview", "state": "pending", "target_url": ""},
            {"context": "deploy/docs", "state": "success", "target_url": ""},
            {"context": "deploy/docs", "state": "failure", "target_url": "https://old/1"},
        ])

    def test_rest_fallback_when_graphql_is_refused(self) -> None:
        self.rest_pull_request()
        reason = self.run_hook(FAKE_GH_GRAPHQL_FAIL="1")["reason"]
        self.assertIn('Review comment by @reviewer on app/Settings.kt:12: "Use a Switch here."', reason)
        self.assertIn("build (failure) https://ci/1", reason)
        self.assertIn("deploy/preview (error) https://preview/1", reason)
        self.assertIn("Merge conflict with acme/app's main", reason)
        self.assertNotIn("old chatter", reason)
        self.assertNotIn("outdated note", reason)
        self.assertNotIn("lint", reason)
        self.assertIsNone(self.run_hook(FAKE_GH_GRAPHQL_FAIL="1"))

    def test_rest_forced_and_reply_threads(self) -> None:
        self.rest_pull_request(mergeable_state="clean")
        self.run_hook(PR_WATCH_API="rest")
        self.assertNotIn("graphql", self.calls.read_text())
        self.rest_fixture("repos/acme/app/pulls/7/comments?per_page=100", [
            {"id": 1, "node_id": "RC1", "user": {"login": "reviewer"}, "body": "Use a Switch here.",
             "path": "app/Settings.kt", "line": 12, "created_at": "2026-01-01T00:00:01Z"},
            {"id": 3, "node_id": "RC3", "in_reply_to_id": 1, "user": {"login": "reviewer"},
             "body": "Still not a Switch.", "path": "app/Settings.kt", "line": 12, "created_at": "2026-01-03T00:00:00Z"},
        ])
        reason = self.run_hook(PR_WATCH_API="rest")["reason"]
        self.assertIn('on app/Settings.kt:12: "Still not a Switch."', reason)
        self.assertNotIn("Merge conflict", reason)

    def test_rest_follows_pages_to_the_newest_comments(self) -> None:
        self.rest_pull_request(mergeable_state="clean")
        repo = "repos/acme/app"
        page = lambda start, count: [  # noqa: E731
            {"node_id": f"IC{n}", "user": {"login": "chatty"}, "body": f"comment-{n} ok",
             "created_at": f"2026-01-01T00:{n // 60:02d}:{n % 60:02d}Z"}
            for n in range(start, start + count)
        ]
        self.rest_fixture(f"{repo}/issues/7/comments?per_page=100", page(0, 100))
        self.rest_fixture(f"{repo}/issues/7/comments?per_page=100&page=2", [])
        self.run_hook(PR_WATCH_API="rest")  # First look: history.
        self.assertIn("issues/7/comments?per_page=100&page=2", self.calls.read_text())
        self.rest_fixture(f"{repo}/issues/7/comments?per_page=100&page=2", page(100, 2))
        reason = self.run_hook(PR_WATCH_API="rest")["reason"]
        self.assertIn('"comment-100 ok"', reason)
        self.assertIn('"comment-101 ok"', reason)
        self.assertNotIn("comment-99 ", reason)
        # A list longer than the page limit fails the read instead of hiding the tail.
        for number in range(2, 11):
            self.rest_fixture(f"{repo}/issues/7/comments?per_page=100&page={number}", page(number * 100, 100))
        self.assertIsNone(self.run_hook(PR_WATCH_API="rest", payload={"session_id": "s4"}))

    def test_many_seen_comments_are_never_reported_again(self) -> None:
        # Codex review example on #213: 26 resolved threads of 20 comments, over the old 500-id cap.
        pr = pull_request()
        pr["reviewThreads"]["nodes"] = [
            {"isResolved": True, "isOutdated": False, "path": f"app/T{t}.kt", "line": 1,
             "comments": {"nodes": [{"id": f"T{t:02d}C{c:02d}", "author": {"login": "reviewer"},
                                     "body": f"thread{t} comment{c}", "createdAt": "2026-01-01T00:00:00Z"}
                                    for c in range(20)]}}
            for t in range(26)
        ]
        self.respond([pr])
        self.assertNotIn("thread", self.run_hook()["reason"])  # First look: CI only; threads are history.
        for _ in range(3):
            self.assertIsNone(self.run_hook())

    def test_truncated_graphql_page_is_reread_through_rest(self) -> None:
        pr = pull_request()
        pr["reviewThreads"]["pageInfo"] = {"hasPreviousPage": True}
        self.respond([pr])
        self.rest_pull_request(mergeable_state="clean")
        reason = self.run_hook()["reason"]
        self.assertIn("deploy/preview (error)", reason)  # Only the REST fixture has this status.
        self.assertIn("issues/7/comments", self.calls.read_text())
        # When the REST read fails, nothing is reported or recorded.
        (self.root / "rest" / re.sub(r"[^A-Za-z0-9]", "_", "repos/acme/app/pulls/7/reviews?per_page=100")).unlink()
        self.assertIsNone(self.run_hook(payload={"session_id": "s5"}))
        self.assertFalse((self.root / "state" / "s5.json").exists())

    def test_checks_past_the_first_graphql_page_are_reread_through_rest(self) -> None:
        pr = pull_request()
        rollup = pr["commits"]["nodes"][0]["commit"]["statusCheckRollup"]
        rollup["contexts"]["nodes"] = [{"__typename": "CheckRun", "name": "lint", "status": "COMPLETED",
                                        "conclusion": "SUCCESS", "detailsUrl": ""}]
        rollup["contexts"]["pageInfo"] = {"hasNextPage": True}
        self.respond([pr])
        self.rest_pull_request(mergeable_state="clean")
        reason = self.run_hook()["reason"]
        self.assertIn("build (failure) https://ci/1", reason)  # Only on the REST pages.
        self.assertIn("deploy/preview (error)", reason)
        self.assertNotIn("deploy/docs", reason)  # Its newest status passed; the old failure is history.

    def test_rest_statuses_follow_pages(self) -> None:
        self.rest_pull_request(mergeable_state="clean")
        repo = "repos/acme/app"
        self.rest_fixture(f"{repo}/commits/abc1234def/statuses?per_page=100",
                          [{"context": f"ok/{n}", "state": "success", "target_url": ""} for n in range(100)])
        self.rest_fixture(f"{repo}/commits/abc1234def/statuses?per_page=100&page=2",
                          [{"context": "late/check", "state": "failure", "target_url": "https://late/1"}])
        self.assertIn("late/check (failure)", self.run_hook(PR_WATCH_API="rest")["reason"])

    def test_fork_pull_requests_on_the_same_branch_name_are_ignored(self) -> None:
        fork = pull_request(number=99, url="https://github.com/acme/app/pull/99", headRepository={"nameWithOwner": "stranger/app"})
        fork["reviewThreads"]["nodes"][0]["comments"]["nodes"][0]["body"] = "fork-only comment"
        deleted = pull_request(number=98, url="https://github.com/acme/app/pull/98", headRepository=None)
        self.respond([fork, deleted, pull_request(headRepository={"nameWithOwner": "ACME/App"})])
        reason = self.run_hook()["reason"]
        self.assertIn("pull/7", reason)
        self.assertNotIn("pull/99", reason)
        self.assertNotIn("pull/98", reason)
        self.assertNotIn("fork-only", reason)
        # An explicitly listed URL is watched whatever its head repository.
        subprocess.run(["git", "-C", str(self.workspace), "config", "--add", "pr-watch.url",
                        "https://github.com/acme/app/pull/99"], check=True)
        self.respond([fork], explicit=fork)
        self.assertIn("fork-only comment", self.run_hook(payload={"session_id": "s6"})["reason"])

    def test_rest_file_level_comments_are_not_outdated(self) -> None:
        self.rest_pull_request(mergeable_state="clean")
        self.rest_fixture("repos/acme/app/pulls/7/comments?per_page=100", [
            {"id": 5, "node_id": "RC5", "user": {"login": "reviewer"}, "body": "Split this file.",
             "path": "app/Big.kt", "line": None, "subject_type": "file", "created_at": "2026-01-01T00:00:05Z"},
            {"id": 6, "node_id": "RC6", "user": {"login": "reviewer"}, "body": "outdated line note",
             "path": "app/Old.kt", "line": None, "subject_type": "line", "created_at": "2026-01-01T00:00:06Z"},
        ])
        reason = self.run_hook(PR_WATCH_API="rest")["reason"]
        self.assertIn('on app/Big.kt: "Split this file."', reason)
        self.assertNotIn("outdated line note", reason)

    def test_forks_filling_the_discovery_page_fall_back_to_rest(self) -> None:
        forks = [pull_request(number=90 + n, url=f"https://github.com/acme/app/pull/{90 + n}",
                              headRepository={"nameWithOwner": f"fork{n}/app"}) for n in range(5)]
        self.response.write_text(json.dumps({"data": {"branch": {"pullRequests": {
            "pageInfo": {"hasNextPage": True}, "nodes": forks}}}}))
        self.rest_pull_request(mergeable_state="clean")
        reason = self.run_hook()["reason"]
        self.assertIn("https://github.com/acme/app/pull/7", reason)  # Found through REST.
        self.assertNotIn("pull/9", reason)

    def test_only_github_remotes_are_discovered(self) -> None:
        git = ["git", "-C", str(self.workspace), "remote", "set-url", "origin"]
        for remote in ("https://gitlab.com/acme/app.git", "git@gitlab.com:acme/app.git",
                       "ssh://git@bitbucket.org/acme/app.git", "https://github.com.evil.example/acme/app"):
            subprocess.run([*git, remote], check=True)
            self.assertIsNone(self.run_hook(payload={"session_id": remote}), remote)
        self.assertFalse(self.calls.exists())
        for remote in ("git@github.com:acme/app.git", "ssh://git@github.com/acme/app",
                       "https://user@GitHub.com/acme/app.git/"):
            subprocess.run([*git, remote], check=True)
            self.assertIsNotNone(self.run_hook(payload={"session_id": remote}), remote)
        query = json.loads((self.root / "query.json").read_text())
        self.assertEqual((query["variables"]["bOwner"], query["variables"]["bName"]), ("acme", "app"))
        # A GitHub Enterprise or proxied host is opted in by name.
        subprocess.run([*git, "https://git.corp.example/acme/app.git"], check=True)
        self.assertIsNone(self.run_hook(payload={"session_id": "ghe1"}))
        self.assertIsNotNone(self.run_hook(payload={"session_id": "ghe2"}, PR_WATCH_GITHUB_HOSTS="git.corp.example"))
        self.assertIsNotNone(self.run_hook(payload={"session_id": "ghe3"}, GH_HOST="git.corp.example"))

    def test_fork_checkout_finds_the_upstream_pull_request(self) -> None:
        git = ["git", "-C", str(self.workspace), "remote"]
        subprocess.run([*git, "set-url", "origin", "git@github.com:me/app.git"], check=True)
        subprocess.run([*git, "add", "upstream", "https://github.com/acme/app.git"], check=True)
        mine = pull_request(headRepository={"nameWithOwner": "me/app"})
        stranger = pull_request(number=8, url="https://github.com/acme/app/pull/8",
                                headRepository={"nameWithOwner": "stranger/app"})
        stranger["reviewThreads"]["nodes"][0]["comments"]["nodes"][0]["body"] = "stranger comment"
        self.response.write_text(json.dumps({"data": {
            "branch": {"pullRequests": {"nodes": []}},
            "upstream": {"pullRequests": {"nodes": [stranger, mine]}},
        }}))
        reason = self.run_hook()["reason"]
        self.assertIn("https://github.com/acme/app/pull/7", reason)
        self.assertNotIn("stranger comment", reason)
        query = json.loads((self.root / "query.json").read_text())
        self.assertEqual((query["variables"]["uOwner"], query["variables"]["uName"]), ("acme", "app"))
        # REST asks the upstream repository for pull requests whose head is on the fork.
        self.rest_fixture("repos/me/app/pulls?state=open&head=me:agent%2Fsettings&per_page=100", [])
        self.rest_pull_request(mergeable_state="clean")
        self.rest_fixture("repos/acme/app/pulls?state=open&head=me:agent%2Fsettings&per_page=100", [{"number": 7}])
        rest_reason = self.run_hook(PR_WATCH_API="rest", payload={"session_id": "s7"})["reason"]
        self.assertIn("https://github.com/acme/app/pull/7", rest_reason)

    def test_upstream_equal_to_origin_is_searched_once(self) -> None:
        subprocess.run(["git", "-C", str(self.workspace), "remote", "add", "upstream",
                        "git@github.com:ACME/app.git"], check=True)
        self.run_hook()
        self.assertNotIn("uOwner", json.loads((self.root / "query.json").read_text())["variables"])

    def test_rest_merged_and_partial_failure(self) -> None:
        self.rest_pull_request()
        (self.root / "rest" / re.sub(r"[^A-Za-z0-9]", "_", "repos/acme/app/pulls/7/reviews?per_page=100")).unlink()
        self.assertIsNone(self.run_hook(PR_WATCH_API="rest"))  # One missing list fails the whole read...
        self.assertFalse((self.root / "state" / "s1.json").exists())  # ...and records nothing as seen.
        self.rest_pull_request(state="closed", merged=True)
        self.assertIsNone(self.run_hook(PR_WATCH_API="rest", payload={"session_id": "s9"}))
        self.rest_fixture("repos/acme/app/pulls/7", {"message": "Not Found"})
        self.assertIsNone(self.run_hook(PR_WATCH_API="rest", payload={"session_id": "s10"}))


if __name__ == "__main__":
    unittest.main()
