# Compose Preview VS Code extension in Cursor (2026-11-02)

Source review of `yschimke/compose-preview-vscode` at the clone used for the
marketplace logo copy (`media/icon.png` → `src/assets/compose-preview-logo.png`).
This environment cannot run the VS Code/Cursor GUI; behaviour below is from
package metadata and TypeScript, not a live panel session.

## Compatibility

| Fact | Value |
| --- | --- |
| Marketplace | [Compose Preview](https://marketplace.visualstudio.com/items?itemName=yuri-schimke.compose-preview) (`yuri-schimke.compose-preview`) |
| `engines.vscode` | `^1.115.0` (Cursor hosts a compatible VS Code engine) |
| Role vs agent plugin | Human activity-bar / panel surface; not shipped inside `cursor-install.py` |

## Follow behaviour (code)

- `EditorScope` pins the Kotlin preview source + Gradle module after a successful
  refresh; webview-initiated refresh reuses that scope instead of
  `activeTextEditor` (which is undefined while the webview has focus).
- `onDidChangeActiveTextEditor` / visible-editor changes drive refresh when the
  active file is a preview source; sticky scope avoids blanking when focus moves
  into the panel.
- Closing the last preview-source tab clears stale cards (`previewTabs` /
  open-tab scan); Antigravity-specific host quirks are gated behind
  `isAntigravityHost()` and do not apply to Cursor.

## Practical Cursor setup

1. Install the agent plugin (`cursor-install.py`) for chat render + audit.
2. Install the VS Code extension from Extensions for the human right-hand pane.
3. Same prepared Gradle project / daemon when both hit the same module.

Live confirmation in Cursor Desktop (open panel, switch files, save-refresh)
remains a human gate listed under
[Remaining gates](../cursor.md#remaining-gates-cursor-optimised).
