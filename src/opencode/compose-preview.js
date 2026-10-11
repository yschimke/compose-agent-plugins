// Compose Preview edit reminder for OpenCode (agent rule R1; issues #8 and #86).
//
// The OpenCode counterpart of the compose-preview plugin's PostToolUse hook. After an edit to a
// *.kt file that declares a @Composable or @Preview, it appends one line to that edit tool's result:
// render an affected preview and look at it before calling the change done. In the Claude Code
// evals a hook was the one channel agents always saw; skills alone did not stop them from editing
// Compose UI without rendering.
//
// It reminds once per file per session, never blocks, and stays silent when anything about it
// fails. OpenCode treats every export of a plugin file as a plugin, so this file exports one.

import { readFile } from "node:fs/promises";
import path from "node:path";

const EDIT_TOOLS = new Set(["edit", "write", "multiedit", "apply_patch"]);
const PATCH_FILE = /^\*\*\* (?:Add|Update) File: (.+)$/gm;
const COMPOSE_MARKER = /@(Composable|Preview)\b/;
const MAX_SESSIONS = 64;

function editedPaths(tool, args) {
  if (!args || typeof args !== "object") return [];
  if (tool === "apply_patch") {
    const text = typeof args.patchText === "string" ? args.patchText : "";
    return [...text.matchAll(PATCH_FILE)].map((match) => match[1].trim());
  }
  return typeof args.filePath === "string" ? [args.filePath] : [];
}

export const ComposePreviewEditReminder = async ({ directory }) => {
  const remindedBySession = new Map();

  return {
    "tool.execute.after": async (input, output) => {
      try {
        if (!EDIT_TOOLS.has(input.tool) || typeof output?.output !== "string") return;
        let reminded = remindedBySession.get(input.sessionID);
        if (!reminded) {
          if (remindedBySession.size >= MAX_SESSIONS) {
            remindedBySession.delete(remindedBySession.keys().next().value);
          }
          reminded = new Set();
          remindedBySession.set(input.sessionID, reminded);
        }
        const names = [];
        for (const edited of editedPaths(input.tool, input.args)) {
          if (!edited.endsWith(".kt")) continue;
          const file = path.resolve(directory ?? process.cwd(), edited);
          if (reminded.has(file)) continue;
          const source = await readFile(file, "utf8").catch(() => "");
          if (!COMPOSE_MARKER.test(source)) continue;
          reminded.add(file);
          names.push(path.basename(file));
        }
        if (names.length === 0) return;
        output.output +=
          `\n\nCompose UI changed in ${names.join(", ")}. Before calling this change done, render ` +
          "an affected preview with render_preview and look at the result (R1). If rendering " +
          "fails or is unavailable, say so instead.";
      } catch {
        // A reminder must never break an edit.
      }
    },
  };
};
