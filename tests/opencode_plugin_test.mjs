// Tests for the OpenCode edit reminder (src/opencode/compose-preview.js). Run: node --test tests/
import assert from "node:assert/strict";
import { mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const plugin = await import(path.join(root, "src", "opencode", "compose-preview.js"));

async function setup() {
  const directory = await mkdtemp(path.join(tmpdir(), "compose-preview-opencode-"));
  await writeFile(path.join(directory, "Screen.kt"), "@Composable\nfun Screen() {}\n");
  await writeFile(path.join(directory, "Model.kt"), "data class Model(val id: Int)\n");
  const exports = Object.values(plugin);
  assert.equal(exports.length, 1, "OpenCode loads every export as a plugin");
  const hooks = await exports[0]({ directory });
  const after = async (tool, args, sessionID = "s1") => {
    const output = { title: "", output: "Edit applied.", metadata: {} };
    await hooks["tool.execute.after"]({ tool, sessionID, callID: "c", args }, output);
    return output.output;
  };
  return { directory, after };
}

test("reminds after an edit to a Compose file", async () => {
  const { after } = await setup();
  const result = await after("edit", { filePath: "Screen.kt", oldString: "a", newString: "b" });
  assert.match(result, /^Edit applied\.\n\nCompose UI changed in Screen\.kt\. .*render_preview/s);
});

test("reminds once per file per session", async () => {
  const { directory, after } = await setup();
  await after("write", { filePath: path.join(directory, "Screen.kt"), content: "" });
  assert.equal(await after("edit", { filePath: "Screen.kt" }), "Edit applied.");
  assert.match(await after("edit", { filePath: "Screen.kt" }, "s2"), /Compose UI changed/);
});

test("reads apply_patch targets", async () => {
  const { after } = await setup();
  const patchText = [
    "*** Begin Patch",
    "*** Update File: Model.kt",
    "@@",
    "*** Add File: Screen.kt",
    "+@Composable",
    "*** End Patch",
  ].join("\n");
  assert.match(await after("apply_patch", { patchText }), /changed in Screen\.kt\. /);
});

test("stays silent for other files, tools and failures", async () => {
  const { after } = await setup();
  assert.equal(await after("edit", { filePath: "Model.kt" }), "Edit applied.");
  assert.equal(await after("edit", { filePath: "Missing.kt" }), "Edit applied.");
  assert.equal(await after("edit", { filePath: "notes.md" }), "Edit applied.");
  assert.equal(await after("read", { filePath: "Screen.kt" }), "Edit applied.");
  assert.equal(await after("edit", null), "Edit applied.");
});
