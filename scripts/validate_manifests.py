#!/usr/bin/env python3
"""Validate the repository's generated plugin manifest contracts using Python stdlib."""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

from generate import (
    ANTIGRAVITY_HOOK_MANIFEST,
    ANTIGRAVITY_SCHEMA,
    ASSET_SOURCE_ROOT,
    HOOK_MANIFESTS,
    HOOK_SOURCE_ROOT,
    LICENSE_SOURCE,
    MARKETPLACE_NAME,
    OPENCODE_LEDGER_NAME,
    OPENCODE_ROOT,
    README_SOURCE_ROOT,
    RULES_SOURCE_ROOT,
    RULES_TARGET,
    SKILL_SOURCE_ROOT,
    render_antigravity_hooks,
    render_claude_manifest,
    render_codex_manifest,
    codex_skill_config,
    render_cursor_manifest,
    render_external_marketplace_entries,
    render_gemini_extension,
    render_hooks,
    render_mcp_servers,
    render_opencode_bundle,
    render_registry_server,
    validate_apps,
)


ROOT = Path(__file__).resolve().parents[1]
NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SCHEMA_ANNOTATIONS = {"$schema", "title"}
SCHEMA_ASSERTIONS = {
    "additionalProperties",
    "const",
    "items",
    "pattern",
    "properties",
    "required",
    "type",
}
# The Claude plugin directory blocks a plugin whose README has fewer words outside code blocks.
README_MIN_WORDS = 40
JSON_SCHEMA_TYPES = {"array", "boolean", "integer", "null", "number", "object", "string"}
ECMASCRIPT_PORTABLE_ESCAPES = frozenset("dDwWbfnrtv\\.^$|?*+()[]{}-/")
# The hosted catalog advertises its data tools with a `catalog_` prefix so they never clash with the
# local server's tools (compose-preview-server#1105, `CATALOG_TOOL_NAMES` in ServeCatalogMcp.kt).
# The unprefixed names still dispatch, but a host only offers advertised names, so a subagent
# allowlist that names them grants nothing.
HOSTED_CATALOG_DATA_TOOLS = frozenset(
    {
        "library",
        "list_projects",
        "list_previews",
        "list_data_products",
        "render_preview",
        "render_matrix",
        "list_devices",
        "diff_semantics",
        "get_preview_data",
        "history_list",
        "history_diff",
        "history_read",
    }
)
# Tools the local `compose-preview mcp serve` does not advertise.
LOCAL_SERVER_MISSING_TOOLS = frozenset({"list_previews"})
CLAUDE_MCP_TOOL = re.compile(r"^mcp__plugin_(?P<plugin>[a-z0-9-]+)_(?P<server>[a-z0-9-]+)__(?P<tool>[a-z0-9_]+)$")


def read_json(path: Path) -> object:
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def matches_json_type(value: object, expected: str) -> bool:
    """Return whether a Python JSON value has the requested JSON Schema type."""
    match expected:
        case "object":
            return isinstance(value, dict)
        case "array":
            return isinstance(value, list)
        case "string":
            return isinstance(value, str)
        case "number":
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        case "integer":
            return (
                isinstance(value, int)
                and not isinstance(value, bool)
                or isinstance(value, float)
                and math.isfinite(value)
                and value.is_integer()
            )
        case "boolean":
            return isinstance(value, bool)
        case "null":
            return value is None
        case _:
            raise ValueError(f"unsupported JSON Schema type: {expected}")


def json_values_equal(left: object, right: object) -> bool:
    """Compare JSON values without conflating booleans and numbers as Python does."""
    left_number = isinstance(left, (int, float)) and not isinstance(left, bool)
    right_number = isinstance(right, (int, float)) and not isinstance(right, bool)
    if left_number or right_number:
        return left_number and right_number and left == right
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        assert isinstance(right, dict)
        return left.keys() == right.keys() and all(
            json_values_equal(left[key], right[key]) for key in left
        )
    if isinstance(left, list):
        assert isinstance(right, list)
        return len(left) == len(right) and all(
            json_values_equal(left_item, right_item)
            for left_item, right_item in zip(left, right, strict=True)
        )
    return left == right


def compile_json_schema_pattern(pattern: str) -> re.Pattern[str]:
    """Compile the ECMAScript-compatible subset this stdlib validator can prove.

    JSON Schema patterns use ECMA-262 semantics, while Python's regular-expression dialect
    differs in observable ways. Keep the supported subset explicit and fail closed on constructs
    whose behavior cannot be reproduced faithfully. In particular, Python's ``$`` accepts a final
    newline and its Unicode shorthand classes differ from JavaScript's.
    """
    translated: list[str] = []
    in_character_class = False
    character_class_has_member = False
    character_class_at_start = False
    previous_was_quantifier = False
    index = 0
    while index < len(pattern):
        character = pattern[index]
        if character == "\\":
            if index + 1 == len(pattern):
                raise ValueError("trailing escape")
            escaped = pattern[index + 1]
            if escaped in "sS":
                raise ValueError(f"unsupported ECMAScript shorthand: \\{escaped}")
            if escaped == "-" and not in_character_class:
                raise ValueError(
                    "escaped hyphen is only valid inside an ECMAScript character class"
                )
            if escaped not in ECMASCRIPT_PORTABLE_ESCAPES:
                raise ValueError(f"unsupported ECMAScript escape: \\{escaped}")
            translated.extend((character, escaped))
            if in_character_class:
                character_class_has_member = True
                character_class_at_start = False
            previous_was_quantifier = False
            index += 2
            continue
        if in_character_class:
            if character == "[":
                raise ValueError("nested character classes are unsupported")
            if character == "]":
                if not character_class_has_member:
                    raise ValueError("empty character classes are unsupported")
                in_character_class = False
                previous_was_quantifier = False
            elif character == "^" and character_class_at_start:
                character_class_at_start = False
            else:
                character_class_has_member = True
                character_class_at_start = False
            translated.append(character)
            index += 1
            continue
        if character == "[":
            in_character_class = True
            character_class_has_member = False
            character_class_at_start = True
            translated.append(character)
        elif character == "]":
            raise ValueError("unmatched closing character-class bracket")
        elif character == "$":
            translated.append(r"\Z")
        elif character == ".":
            raise ValueError("wildcard '.' has incompatible line-terminator semantics")
        elif character in "(){}":
            raise ValueError(f"unsupported ECMAScript construct: {character}")
        elif character == "+" and previous_was_quantifier:
            raise ValueError("possessive quantifiers are not valid ECMAScript")
        else:
            translated.append(character)
        previous_was_quantifier = character in "*+?"
        index += 1
    if in_character_class:
        raise ValueError("unterminated character class")
    return re.compile("".join(translated), flags=re.ASCII)


def validate_schema_shape(schema: object, *, manifest_path: Path, schema_path: str = "$") -> None:
    """Verify that every node in a vendored schema uses the supported subset."""
    if not isinstance(schema, dict):
        raise ValueError(f"{manifest_path}: schema at {schema_path} must be an object")
    unsupported = set(schema) - SCHEMA_ANNOTATIONS - SCHEMA_ASSERTIONS
    if unsupported:
        names = ", ".join(sorted(unsupported))
        raise ValueError(f"{manifest_path}: unsupported schema keywords at {schema_path}: {names}")

    expected_type = schema.get("type")
    if expected_type is not None:
        if not isinstance(expected_type, str):
            raise ValueError(f"{manifest_path}: schema type at {schema_path} must be a string")
        if expected_type not in JSON_SCHEMA_TYPES:
            raise ValueError(
                f"{manifest_path}: unsupported JSON Schema type at {schema_path}: {expected_type}"
            )

    pattern = schema.get("pattern")
    if pattern is not None:
        if not isinstance(pattern, str):
            raise ValueError(f"{manifest_path}: pattern at {schema_path} must be a string")
        try:
            compile_json_schema_pattern(pattern)
        except (re.error, ValueError) as error:
            raise ValueError(f"{manifest_path}: invalid pattern at {schema_path}: {error}") from error

    required = schema.get("required", [])
    if not isinstance(required, list) or not all(isinstance(field, str) for field in required):
        raise ValueError(f"{manifest_path}: required at {schema_path} must be a string array")

    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        raise ValueError(f"{manifest_path}: properties at {schema_path} must be an object")
    for name, child_schema in properties.items():
        validate_schema_shape(
            child_schema,
            manifest_path=manifest_path,
            schema_path=f"{schema_path}.{name}",
        )

    if "items" in schema:
        validate_schema_shape(
            schema["items"],
            manifest_path=manifest_path,
            schema_path=f"{schema_path}[]",
        )

    additional = schema.get("additionalProperties", True)
    if isinstance(additional, dict):
        validate_schema_shape(
            additional,
            manifest_path=manifest_path,
            schema_path=f"{schema_path}.*",
        )
    elif not isinstance(additional, bool):
        raise ValueError(
            f"{manifest_path}: additionalProperties at {schema_path} must be a boolean or schema"
        )


def _validate_value_against_schema(
    value: object, schema: dict[str, object], *, manifest_path: Path, value_path: str
) -> None:
    expected_type = schema.get("type")
    if isinstance(expected_type, str):
        if not matches_json_type(value, expected_type):
            raise ValueError(f"{manifest_path}: {value_path} must have type {expected_type}")

    if "const" in schema and not json_values_equal(value, schema["const"]):
        raise ValueError(f"{manifest_path}: {value_path} must equal {schema['const']!r}")

    pattern = schema.get("pattern")
    if pattern is not None and isinstance(value, str):
        assert isinstance(pattern, str)
        if compile_json_schema_pattern(pattern).search(value) is None:
            raise ValueError(f"{manifest_path}: {value_path} does not match {pattern!r}")

    if isinstance(value, dict):
        required = schema.get("required", [])
        assert isinstance(required, list)
        missing = [field for field in required if field not in value]
        if missing:
            raise ValueError(
                f"{manifest_path}: {value_path} is missing required fields: {', '.join(missing)}"
            )

        properties = schema.get("properties", {})
        assert isinstance(properties, dict)
        for name, child_schema in properties.items():
            if name in value:
                assert isinstance(child_schema, dict)
                _validate_value_against_schema(
                    value[name],
                    child_schema,
                    manifest_path=manifest_path,
                    value_path=f"{value_path}.{name}",
                )

        additional = schema.get("additionalProperties", True)
        extras = set(value) - set(properties)
        if additional is False and extras:
            names = ", ".join(sorted(extras))
            raise ValueError(f"{manifest_path}: {value_path} has additional properties: {names}")
        if isinstance(additional, dict):
            for name in extras:
                _validate_value_against_schema(
                    value[name],
                    additional,
                    manifest_path=manifest_path,
                    value_path=f"{value_path}.{name}",
                )

    if isinstance(value, list) and "items" in schema:
        item_schema = schema["items"]
        assert isinstance(item_schema, dict)
        for index, item in enumerate(value):
            _validate_value_against_schema(
                item,
                item_schema,
                manifest_path=manifest_path,
                value_path=f"{value_path}[{index}]",
            )


def validate_against_schema(
    value: object, schema: object, *, manifest_path: Path, value_path: str = "$"
) -> None:
    """Validate every assertion keyword used by the vendored manifest schemas.

    This is deliberately a small stdlib validator rather than a partial draft
    implementation. Failing on unknown keywords prevents a future schema edit
    from silently declaring a constraint that CI does not enforce.
    """
    validate_schema_shape(schema, manifest_path=manifest_path, schema_path=value_path)
    assert isinstance(schema, dict)
    _validate_value_against_schema(
        value,
        schema,
        manifest_path=manifest_path,
        value_path=value_path,
    )


def validate_manifest_schema(manifest: object, schema_file: str, path: Path) -> None:
    validate_against_schema(
        manifest,
        read_json(ROOT / "schemas" / schema_file),
        manifest_path=path,
    )


def validate_skill(path: Path) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    if len(lines) < 3 or lines[0] != "---":
        raise ValueError(f"{path}: missing YAML frontmatter")
    try:
        end = lines.index("---", 1)
    except ValueError as error:
        raise ValueError(f"{path}: unterminated YAML frontmatter") from error
    fields = {}
    for line in lines[1:end]:
        key, separator, value = line.partition(":")
        if separator:
            fields[key.strip()] = value.strip().strip('"')
    name = fields.get("name", "")
    description = fields.get("description", "")
    if not NAME.fullmatch(name) or len(name) > 64:
        raise ValueError(f"{path}: name must be lowercase hyphen-case and at most 64 characters")
    if not description or len(description) > 1024:
        raise ValueError(f"{path}: description must be 1 to 1024 characters")


def agent_tools(path: Path) -> list[str]:
    """The JSON `tools:` list in an agent's frontmatter, or an empty list when it has none."""
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---":
        raise ValueError(f"{path}: missing YAML frontmatter")
    for line in lines[1 : lines.index("---", 1)]:
        if line.startswith("tools:"):
            tools = json.loads(line.partition(":")[2])
            if not isinstance(tools, list) or not all(isinstance(tool, str) for tool in tools):
                raise ValueError(f"{path}: tools must be a JSON list of strings")
            return tools
    return []


def validate_agent_tools(path: Path, plugins: list[dict[str, object]]) -> None:
    """Reject agent MCP tools that name an undeclared server or one a server is known not to advertise.

    This is a denylist of names known to be wrong (the hosted catalog's pre-prefix names, tools the
    local server lacks), not a full allowlist: the servers' tool lists change with each
    compose-preview-server release, which this repository does not pin.
    """
    servers = {
        (plugin["name"], entry["name"]): entry
        for plugin in plugins
        for entry in plugin.get("mcp", [])
    }
    for tool in agent_tools(path):
        if not tool.startswith("mcp__"):
            continue
        match = CLAUDE_MCP_TOOL.fullmatch(tool)
        if match is None:
            raise ValueError(f"{path}: {tool} is not an mcp__plugin_<plugin>_<server>__<tool> name")
        # Plugin and server names may both contain hyphens, so try every split.
        candidates = [
            entry
            for (plugin, server), entry in servers.items()
            if f"{plugin}_{server}" == f"{match['plugin']}_{match['server']}"
        ]
        if not candidates:
            raise ValueError(f"{path}: {tool} names no MCP server declared in src/plugins.json")
        entry, name = candidates[0], match["tool"]
        if entry.get("kind") == "http" and name in HOSTED_CATALOG_DATA_TOOLS:
            raise ValueError(
                f"{path}: {tool} is not advertised; the hosted catalog names it catalog_{name}"
            )
        if entry.get("kind") == "stdio" and (
            name in LOCAL_SERVER_MISSING_TOOLS or name.startswith("catalog_")
        ):
            raise ValueError(f"{path}: {tool} is not a tool of the local compose-preview server")


def readme_words(path: Path) -> int:
    """Count README words outside fenced code blocks, as the plugin directory does."""
    words = 0
    in_fence = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            words += len(line.split())
    return words


def validate_plugin_folder_docs(root: Path, name: str) -> None:
    readme = root / "README.md"
    if not readme.is_file():
        raise ValueError(f"{readme}: missing plugin README")
    if readme.read_bytes() != (README_SOURCE_ROOT / f"{name}.md").read_bytes():
        raise ValueError(f"{readme}: generated copy differs from src/readmes/{name}.md")
    if readme_words(readme) < README_MIN_WORDS:
        raise ValueError(f"{readme}: needs at least {README_MIN_WORDS} words outside code blocks")
    license_file = root / "LICENSE"
    if not license_file.is_file() or license_file.read_bytes() != LICENSE_SOURCE.read_bytes():
        raise ValueError(f"{license_file}: must be a copy of the repository LICENSE")


def main() -> None:
    source = read_json(ROOT / "src" / "plugins.json")
    if not isinstance(source, dict):
        raise ValueError("src/plugins.json must be an object")
    plugins = source["plugins"]
    if not isinstance(plugins, list):
        raise ValueError("src/plugins.json plugins must be a list")

    expected_marketplace = []
    for plugin in plugins:
        name = plugin["name"]
        root = ROOT / "plugins" / name
        expected_skills = {
            root / "skills" / skill / "SKILL.md" for skill in plugin.get("skills", [])
        }
        actual_skills = set(root.glob("skills/*/SKILL.md"))
        if actual_skills != expected_skills:
            unexpected = sorted(str(path.relative_to(ROOT)) for path in actual_skills - expected_skills)
            missing = sorted(str(path.relative_to(ROOT)) for path in expected_skills - actual_skills)
            details = []
            if unexpected:
                details.append(f"unexpected skills: {', '.join(unexpected)}")
            if missing:
                details.append(f"missing skills: {', '.join(missing)}")
            raise ValueError(f"{root}: {'; '.join(details)}")
        antigravity = read_json(root / "plugin.json")
        claude = read_json(root / ".claude-plugin" / "plugin.json")
        codex = read_json(root / ".codex-plugin" / "plugin.json")
        cursor = read_json(root / ".cursor-plugin" / "plugin.json")
        validate_plugin_folder_docs(root, name)
        validate_manifest_schema(antigravity, "antigravity-plugin.schema.json", root / "plugin.json")
        validate_manifest_schema(
            claude, "claude-plugin.schema.json", root / ".claude-plugin" / "plugin.json"
        )
        validate_manifest_schema(
            codex, "codex-plugin.schema.json", root / ".codex-plugin" / "plugin.json"
        )
        expected_antigravity = {
            "$schema": ANTIGRAVITY_SCHEMA,
            "description": plugin["description"],
            "name": name,
        }
        expected_core = {key: plugin[key] for key in ("name", "version", "description")}
        if antigravity != expected_antigravity:
            raise ValueError(f"{root}/plugin.json does not match the Antigravity contract")
        if any(claude.get(key) != value for key, value in expected_core.items()):
            raise ValueError(f"{root}/.claude-plugin/plugin.json does not match the Claude/Codex contract")
        if claude.get("author") != {"name": source["owner"]}:
            raise ValueError(f"{root}/.claude-plugin/plugin.json has an invalid author")
        if claude.get("repository") != source["repository"] or claude.get("license") != source["license"]:
            raise ValueError(f"{root}/.claude-plugin/plugin.json has invalid package metadata")
        if claude.get("keywords") != plugin.get("keywords", []):
            raise ValueError(f"{root}/.claude-plugin/plugin.json has invalid keywords")
        manifest_inputs = {
            "plugin": plugin,
            "user_config": plugin.get("userConfig", {}),
            "owner": source["owner"],
            "repository": source["repository"],
            "license_name": source["license"],
        }
        if claude != render_claude_manifest(**manifest_inputs):
            raise ValueError(f"{root}/.claude-plugin/plugin.json does not match the Claude contract")
        if cursor != render_cursor_manifest(**manifest_inputs):
            raise ValueError(f"{root}/.cursor-plugin/plugin.json does not match the Cursor contract")
        codex_skills, codex_path = codex_skill_config(plugin)
        expected_codex = render_codex_manifest(
            name=name,
            version=plugin["version"],
            description=plugin["description"],
            keywords=plugin.get("keywords", []),
            skills=codex_skills,
            skills_path=codex_path,
            mcp=plugin.get("mcp", []),
            apps=validate_apps(name, plugin.get("apps", {}), plugin.get("mcp", [])),
            interface=plugin.get("interface"),
            hooks=plugin.get("hooks", []),
            onboarding_skill=plugin.get("onboardingSkill"),
            owner=source["owner"],
            repository=source["repository"],
            license_name=source["license"],
        )
        expected_codex_files = {root / codex_path / skill / "SKILL.md" for skill in codex_skills}
        actual_codex_files = set((root / codex_path).glob("*/SKILL.md"))
        if expected_codex_files != actual_codex_files:
            raise ValueError(f"{name}: Codex skills do not match the selected set")
        for path in expected_codex_files:
            if path.read_text() != (SKILL_SOURCE_ROOT / path.parent.name / "SKILL.md").read_text():
                raise ValueError(f"{path}: stale Codex skill copy")
        if codex != expected_codex:
            raise ValueError(f"{root}/.codex-plugin/plugin.json does not match the Codex contract")
        apps = validate_apps(name, plugin.get("apps", {}), plugin.get("mcp", []))
        app_manifest = root / ".app.json"
        if apps:
            if read_json(app_manifest) != {"apps": apps}:
                raise ValueError(f"{app_manifest} does not match the app contract")
        elif app_manifest.exists():
            raise ValueError(f"{root} contains stale app configuration")
        rules_copy = root / RULES_TARGET
        if plugin.get("rules"):
            if rules_copy.read_bytes() != (RULES_SOURCE_ROOT / f"{plugin['rules']}.md").read_bytes():
                raise ValueError(f"{rules_copy}: generated copy differs from src/rules/{plugin['rules']}.md")
        elif rules_copy.exists():
            raise ValueError(f"{root} contains stale rules")
        for agent in plugin.get("agents", []):
            validate_agent_tools(root / "agents" / f"{agent}.md", plugins)
        for skill_path in expected_skills:
            validate_skill(skill_path)
            shared_source = SKILL_SOURCE_ROOT / skill_path.parent.name / "SKILL.md"
            if not shared_source.is_file():
                raise ValueError(
                    f"{skill_path}: missing shared source {shared_source.relative_to(ROOT)}"
                )
            if skill_path.read_bytes() != shared_source.read_bytes():
                raise ValueError(f"{skill_path}: generated copy differs from shared source")
        assets = plugin.get("assets", [])
        if not isinstance(assets, list) or not all(isinstance(asset, str) for asset in assets):
            raise ValueError(f"{name}.assets must be a list of strings")
        for asset in assets:
            generated_asset = root / "assets" / asset
            shared_asset = ASSET_SOURCE_ROOT / asset
            if not generated_asset.is_file():
                raise ValueError(f"{generated_asset}: missing generated asset")
            if not shared_asset.is_file():
                raise ValueError(f"{generated_asset}: missing shared source")
            if generated_asset.read_bytes() != shared_asset.read_bytes():
                raise ValueError(f"{generated_asset}: generated copy differs from shared source")
        hooks = plugin.get("hooks", [])
        antigravity_hooks = render_antigravity_hooks(name, hooks) if hooks else None
        antigravity_hook_manifest = root / ANTIGRAVITY_HOOK_MANIFEST
        if antigravity_hooks:
            if read_json(antigravity_hook_manifest) != antigravity_hooks:
                raise ValueError(f"{antigravity_hook_manifest} does not match the hook contract")
        elif antigravity_hook_manifest.exists():
            raise ValueError(f"{root} contains stale Antigravity hook configuration")
        if hooks:
            for harness, manifest_path in HOOK_MANIFESTS.items():
                hook_manifest = root / manifest_path
                if read_json(hook_manifest) != render_hooks(name, hooks, harness):
                    raise ValueError(f"{hook_manifest} does not match the hook contract")
            for hook in hooks:
                command = hook["command"]
                generated_hook = root / command
                shared_hook = HOOK_SOURCE_ROOT / Path(command).name
                if not generated_hook.is_file():
                    raise ValueError(f"{generated_hook}: missing generated hook script")
                if generated_hook.read_bytes() != shared_hook.read_bytes():
                    raise ValueError(f"{generated_hook}: generated hook differs from shared source")
        elif any((root / path).exists() for path in HOOK_MANIFESTS.values()):
            raise ValueError(f"{root} contains stale hook configuration")
        mcp = plugin.get("mcp", [])
        if mcp:
            antigravity_mcp = read_json(root / "mcp_config.json")
            claude_mcp = read_json(root / ".mcp.json")
            if antigravity_mcp != {
                "mcpServers": render_mcp_servers(name, mcp, "antigravity")
            }:
                raise ValueError(f"{root}/mcp_config.json does not match the MCP contract")
            if claude_mcp != {
                "mcpServers": render_mcp_servers(name, mcp, "claude", plugin.get("userConfig", {}))
            }:
                raise ValueError(f"{root}/.mcp.json does not match the MCP contract")
            claude_headers = [
                value
                for server in claude_mcp["mcpServers"].values()
                for value in server.get("headers", {}).values()
            ]
            if any("${" in value.replace("${user_config.", "") for value in claude_headers):
                raise ValueError(
                    f"{root}/.mcp.json must take credentials from userConfig, not the user's environment"
                )
        elif (root / "mcp_config.json").exists() or (root / ".mcp.json").exists():
            raise ValueError(f"{root} contains stale MCP configuration")
        expected_marketplace.append(
            {"description": plugin["description"], "name": name, "source": f"./plugins/{name}"}
        )

    marketplace = read_json(ROOT / ".claude-plugin" / "marketplace.json")
    if marketplace != {
        "metadata": {"description": source["description"]},
        "name": MARKETPLACE_NAME,
        "owner": {"name": source["owner"]},
        "plugins": expected_marketplace
        + render_external_marketplace_entries(source, {plugin["name"] for plugin in plugins}),
    }:
        raise ValueError(".claude-plugin/marketplace.json does not match the marketplace contract")
    cursor_marketplace = read_json(ROOT / ".cursor-plugin" / "marketplace.json")
    if cursor_marketplace != {
        "metadata": {"description": source["description"]},
        "name": MARKETPLACE_NAME,
        "owner": {"name": source["owner"]},
        "plugins": [
            {**entry, "source": entry["source"].removeprefix("./")} for entry in expected_marketplace
        ],
    }:
        raise ValueError(".cursor-plugin/marketplace.json does not match the marketplace contract")
    if read_json(ROOT / "gemini-extension.json") != render_gemini_extension(source, plugins):
        raise ValueError("gemini-extension.json does not match the Gemini CLI contract")
    if read_json(ROOT / "server.json") != render_registry_server(source, plugins):
        raise ValueError("server.json does not match the MCP Registry contract")
    opencode_files = render_opencode_bundle(source, plugins)
    for relative, content in opencode_files.items():
        if (OPENCODE_ROOT / relative).read_bytes() != content:
            raise ValueError(f"opencode/{relative} does not match its source")
    if read_json(OPENCODE_ROOT / OPENCODE_LEDGER_NAME) != sorted(opencode_files):
        raise ValueError(f"opencode/{OPENCODE_LEDGER_NAME} does not list the generated bundle")
    actual = {
        str(path.relative_to(OPENCODE_ROOT))
        for path in OPENCODE_ROOT.rglob("*")
        if path.is_file() and path.name != OPENCODE_LEDGER_NAME
    }
    if actual != set(opencode_files):
        raise ValueError(f"opencode/ has unexpected files: {sorted(actual - set(opencode_files))}")


if __name__ == "__main__":
    try:
        main()
    except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError) as error:
        print(f"plugin validation failed: {error}", file=sys.stderr)
        raise SystemExit(1)
