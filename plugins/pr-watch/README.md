# PR Watch

Keeps a coding agent driving the pull requests it opens. When the agent stops,
and when a session starts or resumes, a hook asks GitHub about the open pull
requests for the checkout's current branch and reports new review comments,
failed checks and merge conflicts, so the agent handles them instead of
leaving them for you. It is optional and not Compose-specific.

This folder is generated from
[`yschimke/compose-agent-plugins`](https://github.com/yschimke/compose-agent-plugins);
install steps for each harness are in its
[host setup](https://github.com/yschimke/compose-agent-plugins/blob/main/docs/host-setup.md#install-per-host).
How the hooks behave is in its [hooks](https://github.com/yschimke/compose-agent-plugins/blob/main/docs/hooks.md#pr-watch)
doc.

## What it contains

- A Stop hook (`scripts/pr-watch.py`) for Claude Code, Codex and Antigravity.
  It keeps the agent working only when there is something new; it never
  waits for CI that is still running, and it lets the agent stop after three
  blocked turns in a row or when anything about the hook fails.
- A SessionStart hook (`scripts/pr-watch-session-start.sh`) that reports the
  same items as context when a session starts or resumes.
- The `pr-watch` skill: how to handle each kind of item.

It needs `python3`, `git`, and either an authenticated `gh` or a `GH_TOKEN` /
`GITHUB_TOKEN` in the environment hooks run with. It discovers pull requests
only for a GitHub `origin`; list a GitHub Enterprise or proxied host in
`PR_WATCH_GITHUB_HOSTS`. `PR_WATCH=0` turns it off.

## Data it sends

Requests to GitHub (`api.github.com`, or `GITHUB_GRAPHQL_URL` /
`GITHUB_API_URL`) naming the repository and branch of the checkout: one
GraphQL request per hook run, or, where GraphQL is refused, a few REST
requests per pull request. It stores the ids
of comments it has already reported under `~/.local/state/pr-watch/`.

## License

Apache-2.0. See [`LICENSE`](LICENSE).
