#!/usr/bin/env python3
"""Generate cross-harness plugin manifests from src/plugins.json."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "plugins.json"
SKILL_SOURCE_ROOT = ROOT / "src" / "skills"
# Skills copied from yschimke/skills by scripts/update-skills.py; never edited here.
VENDOR_SKILL_ROOT = ROOT / "src" / "vendor" / "skills"
VENDOR_PROVENANCE = VENDOR_SKILL_ROOT / "provenance.json"
SKILL_ROOTS = (SKILL_SOURCE_ROOT, VENDOR_SKILL_ROOT)
SKILL_IGNORED_PARTS = {"__pycache__", ".DS_Store"}
AGENT_SOURCE_ROOT = ROOT / "src" / "agents"
AGENT_LEDGER_NAME = ".generated-agents.json"
# agents/ is what Antigravity (and Cursor) scan, and Antigravity fails to start an agent whose
# `tools:` names a tool it does not have (#147), so that copy carries only `name` and
# `description`. Claude Code reads its own copy, with the tool allowlist, from the manifest's
# `agents` list, which replaces its default agents/ scan.
PORTABLE_AGENT_DIR = "agents"
CLAUDE_AGENT_DIR = "claude-agents"
PORTABLE_AGENT_FIELDS = ("name", "description")
HOOK_SOURCE_ROOT = ROOT / "src" / "hooks"
ASSET_SOURCE_ROOT = ROOT / "src" / "assets"
ASSET_LEDGER_NAME = ".generated-assets.json"
SIDECAR_SOURCE_ROOT = ROOT / "src" / "sidecars"
SIDECAR_LEDGER_NAME = ".generated-sidecars.json"
SIDECAR_LAUNCHER_NAME = "launch.mjs"
README_SOURCE_ROOT = ROOT / "src" / "readmes"
RULES_SOURCE_ROOT = ROOT / "src" / "rules"
# Antigravity loads a plugin's rules/AGENTS.md on every turn (harness matrix Q6); Claude Code does not.
RULES_TARGET = "rules/AGENTS.md"
OPENCODE_ROOT = ROOT / "opencode"
OPENCODE_SOURCE_ROOT = ROOT / "src" / "opencode"
OPENCODE_LEDGER_NAME = ".generated-opencode.json"
CLAUDE_BASH_RULE = re.compile(r"^Bash\((?P<prefix>[^():*]+):\*\)$")
CLAUDE_PLUGIN_TOOL = re.compile(r"^mcp__plugin_[a-z0-9-]+?_(?P<server>[a-z0-9-]+)__(?P<tool>[a-z0-9_]+)$")
LICENSE_SOURCE = ROOT / "LICENSE"
# Claude Code reads hooks/hooks.json by default. Codex would read that same file,
# so the Codex manifest names its own copy, whose commands pass --harness=codex.
HOOK_MANIFESTS = {"claude": "hooks/hooks.json", "codex": "hooks/codex-hooks.json"}
# Antigravity reads a root hooks.json keyed by plugin name and runs commands
# with cwd set to the plugin folder, so "./scripts/<script>" is portable across
# installed copies and local agy plugin validate runs.
ANTIGRAVITY_HOOK_MANIFEST = "hooks.json"
ANTIGRAVITY_HOOK_EVENTS = ("SessionStart", "Stop")
ANTIGRAVITY_SCHEMA = "https://antigravity.google/schemas/v1/plugin.json"
MCP_REGISTRY_SCHEMA = "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json"
MARKETPLACE_NAME = "compose-agent-plugins"
# Claude Code userConfig options are strict objects; reject anything else here.
USER_CONFIG_FIELDS = {"type", "title", "description", "sensitive", "required", "default"}
USER_CONFIG_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
ENV_NAME = re.compile(r"^[A-Z_][A-Z0-9_]*$")
SKILL_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SEMVER = re.compile(
    r"^(0|[1-9][0-9]*)\."
    r"(0|[1-9][0-9]*)\."
    r"(0|[1-9][0-9]*)"
    r"(?:-(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)(?:\."
    r"(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
APP_ID = re.compile(r"^(?:plugin_asdk_app|asdk_app|connector|templated_apps)_[A-Za-z0-9][A-Za-z0-9_-]*$")
CODEX_INTERFACE_STRINGS = (
    "displayName",
    "shortDescription",
    "longDescription",
    "developerName",
    "category",
)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def require_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def render_codex_manifest(
    *,
    name: str,
    version: str,
    description: str,
    keywords: list[str],
    skills: list[str],
    skills_path: str = "./skills/",
    mcp: list[object],
    apps: dict[str, object],
    interface: object,
    hooks: list[object] | None = None,
    onboarding_skill: object = None,
    owner: str,
    repository: str,
    license_name: str,
) -> dict[str, object]:
    if not isinstance(interface, dict):
        raise ValueError(f"{name}.interface must be an object")
    rendered_interface: dict[str, object] = {
        field: require_string(interface.get(field), f"{name}.interface.{field}")
        for field in CODEX_INTERFACE_STRINGS
    }
    capabilities = interface.get("capabilities")
    if not isinstance(capabilities, list) or not capabilities:
        raise ValueError(f"{name}.interface.capabilities must be a non-empty list of strings")
    rendered_capabilities = [
        require_string(capability, f"{name}.interface.capabilities[{index}]")
        for index, capability in enumerate(capabilities)
    ]
    default_prompt = interface.get("defaultPrompt")
    if not isinstance(default_prompt, list) or not 1 <= len(default_prompt) <= 3:
        raise ValueError(
            f"{name}.interface.defaultPrompt must contain 1 to 3 non-empty strings of at most 128 characters"
        )
    rendered_default_prompt = [
        require_string(prompt, f"{name}.interface.defaultPrompt[{index}]")
        for index, prompt in enumerate(default_prompt)
    ]
    if any(len(prompt) > 128 for prompt in rendered_default_prompt):
        raise ValueError(
            f"{name}.interface.defaultPrompt must contain 1 to 3 non-empty strings of at most 128 characters"
        )
    rendered_interface["capabilities"] = rendered_capabilities
    rendered_interface["defaultPrompt"] = rendered_default_prompt

    manifest: dict[str, object] = {
        "author": {"name": owner},
        "description": description,
        "interface": rendered_interface,
        "keywords": keywords,
        "license": license_name,
        "name": name,
        "repository": repository,
        "version": version,
    }
    if skills:
        manifest["skills"] = skills_path
    if mcp:
        manifest["mcpServers"] = render_mcp_servers(name, mcp, "codex")
    if apps:
        manifest["apps"] = "./.app.json"
    if hooks:
        manifest["hooks"] = f"./{HOOK_MANIFESTS['codex']}"
    if onboarding_skill is not None:
        manifest["extensions"] = {
            "com.openai": {"onboardingSkill": onboarding_skill_path(name, onboarding_skill, skills, skills_path)}
        }
    return manifest


def onboarding_skill_path(plugin_name: str, skill: object, skills: list[str], skills_path: str = "./skills/") -> str:
    """The OpenAI plugin-onboarding skill: run by ChatGPT/Codex right after install.

    It must be one of the plugin's own packaged skills; other harnesses ignore the key.
    """
    name = require_string(skill, f"{plugin_name}.onboardingSkill")
    if name not in skills:
        raise ValueError(f"{plugin_name}.onboardingSkill {name!r} must be one of the plugin's skills")
    return f"{skills_path}{name}/SKILL.md"


def validate_apps(
    plugin_name: str, value: object, mcp: object = None
) -> dict[str, dict[str, object]]:
    if not isinstance(value, dict):
        raise ValueError(f"{plugin_name}.apps must be an object")
    rendered: dict[str, dict[str, object]] = {}
    for name, app in value.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"{plugin_name}.apps keys must be non-empty strings")
        if not isinstance(app, dict):
            raise ValueError(f"{plugin_name}.apps.{name} must be an object")
        unknown = set(app) - {"id", "category", "optional", "required"}
        if unknown:
            raise ValueError(
                f"{plugin_name}.apps.{name} has unsupported fields: {', '.join(sorted(unknown))}"
            )
        app_id = require_string(app.get("id"), f"{plugin_name}.apps.{name}.id")
        if APP_ID.fullmatch(app_id) is None:
            raise ValueError(
                f"{plugin_name}.apps.{name}.id must use a plugin_asdk_app_, asdk_app_, connector_, or "
                "templated_apps_ identifier"
            )
        rendered_app: dict[str, object] = {"id": app_id}
        if "category" in app:
            rendered_app["category"] = require_string(
                app.get("category"), f"{plugin_name}.apps.{name}.category"
            )
        for field in ("optional", "required"):
            if field in app:
                if not isinstance(app[field], bool):
                    raise ValueError(f"{plugin_name}.apps.{name}.{field} must be a boolean")
                rendered_app[field] = app[field]
        rendered[name] = rendered_app
    if mcp is not None:
        if not isinstance(mcp, list):
            raise ValueError(f"{plugin_name}.mcp must be a list")
        mcp_names = {
            require_string(entry.get("name"), f"{plugin_name}.mcp.name")
            for entry in mcp
            if isinstance(entry, dict)
        }
        unmatched = set(rendered) - mcp_names
        if unmatched:
            raise ValueError(
                f"{plugin_name}.apps aliases must match declared MCP server names: "
                f"{', '.join(sorted(unmatched))}"
            )
    return rendered


def codex_skill_config(plugin: dict[str, object]) -> tuple[list[str], str]:
    skills = plugin.get("skills", [])
    selected = plugin.get("codexSkills", skills)
    if (not isinstance(selected, list) or not all(isinstance(s, str) for s in selected)
            or len(set(selected)) != len(selected) or any(s not in skills for s in selected)):
        raise ValueError(f"{plugin['name']}.codexSkills must be a unique subset of skills")
    return selected, "./.codex-plugin/skills/" if "codexSkills" in plugin else "./skills/"


def write_codex_skills(plugin_root: Path, plugin: dict[str, object]) -> None:
    # This directory is wholly generated. Keep removed skills out of Codex discovery.
    import shutil
    target = plugin_root / ".codex-plugin" / "skills"
    if target.exists():
        shutil.rmtree(target)
    if "codexSkills" not in plugin:
        return
    selected, _ = codex_skill_config(plugin)
    for skill in selected:
        write_skill_directory(target / skill, skill)


def skill_source(skill: str) -> Path:
    """A skill's source directory: src/skills/<name>, else the vendored src/vendor/skills/<name>."""
    if not SKILL_NAME.fullmatch(skill):
        raise ValueError(f"invalid skill name: {skill}")
    found = [root / skill for root in SKILL_ROOTS if (root / skill).is_dir()]
    if len(found) > 1:
        raise ValueError(
            f"skill {skill} is in both src/skills/ and src/vendor/skills/; a vendored skill is "
            "never forked here"
        )
    if not found or not (found[0] / "SKILL.md").is_file():
        raise ValueError(
            f"missing shared skill source: src/skills/{skill}/SKILL.md or "
            f"src/vendor/skills/{skill}/SKILL.md"
        )
    return found[0]


def skill_files(skill: str) -> dict[str, Path]:
    """Every file of a skill (SKILL.md, references/, scripts/, ...), keyed by relative path."""
    root = skill_source(skill)
    return {
        path.relative_to(root).as_posix(): path
        for path in sorted(root.rglob("*"))
        if path.is_file() and not SKILL_IGNORED_PARTS.intersection(path.relative_to(root).parts)
    }


def is_executable(path: Path) -> bool:
    return bool(path.stat().st_mode & 0o111)


def write_skill_directory(target: Path, skill: str) -> None:
    """Copy a whole skill directory, keeping the executable bit of its scripts."""
    for relative, source in skill_files(skill).items():
        output = target / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(source.read_bytes())
        output.chmod(0o755 if is_executable(source) else 0o644)


def write_skills(plugin_root: Path, skills: list[str]) -> None:
    # skills/ is wholly generated, so a removed skill or file must not linger.
    import shutil
    target = plugin_root / "skills"
    if target.exists():
        shutil.rmtree(target)
    for skill in skills:
        write_skill_directory(target / skill, skill)


def write_agent(plugin_root: Path, agent: str) -> None:
    if not SKILL_NAME.fullmatch(agent):
        raise ValueError(f"invalid agent name: {agent}")
    source = AGENT_SOURCE_ROOT / f"{agent}.md"
    if not source.is_file():
        raise ValueError(f"missing shared agent source: {source.relative_to(ROOT)}")
    text = source.read_text(encoding="utf-8")
    claude = plugin_root / CLAUDE_AGENT_DIR / f"{agent}.md"
    claude.parent.mkdir(parents=True, exist_ok=True)
    claude.write_text(text, encoding="utf-8")
    portable = plugin_root / PORTABLE_AGENT_DIR / f"{agent}.md"
    portable.parent.mkdir(parents=True, exist_ok=True)
    portable.write_text(render_portable_agent(text, source.relative_to(ROOT)), encoding="utf-8")


def render_portable_agent(text: str, source: Path) -> str:
    """The agent without harness-specific frontmatter: tool names differ between harnesses."""
    fields, body = split_frontmatter(text, source)
    lines = ["---"]
    for field in PORTABLE_AGENT_FIELDS:
        lines.append(f"{field}: {require_string(fields.get(field), f'{source}.{field}')}")
    lines.append("---")
    return "\n".join(lines) + "\n" + body


def write_rules(plugin_root: Path, plugin_name: str, rules: object) -> None:
    """Copy src/rules/<rules>.md to the plugin's rules/AGENTS.md, or remove a stale copy."""
    target = plugin_root / RULES_TARGET
    if rules is None:
        target.unlink(missing_ok=True)
        if target.parent.is_dir() and not any(target.parent.iterdir()):
            target.parent.rmdir()
        return
    if not isinstance(rules, str) or not SKILL_NAME.fullmatch(rules):
        raise ValueError(f"{plugin_name}.rules must name a src/rules/<name>.md file")
    source = RULES_SOURCE_ROOT / f"{rules}.md"
    if not source.is_file():
        raise ValueError(f"missing shared rules source: {source.relative_to(ROOT)}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")


def split_frontmatter(text: str, source: Path) -> tuple[dict[str, str], str]:
    """Split a single-line-value YAML frontmatter block from its Markdown body."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"{source}: missing frontmatter")
    end = next((index for index, line in enumerate(lines[1:], 1) if line.strip() == "---"), None)
    if end is None:
        raise ValueError(f"{source}: unterminated frontmatter")
    fields = {}
    for line in lines[1:end]:
        key, separator, value = line.partition(":")
        if separator:
            fields[key.strip()] = value.strip()
    return fields, "".join(lines[end + 1 :])


def render_opencode_agent(agent: str, servers: dict[str, str]) -> str:
    """Translate a Claude Code agent into an OpenCode subagent with the same tool boundary.

    Claude's `Bash(<prefix>:*)` rules become OpenCode bash permissions, and its
    `mcp__plugin_<plugin>_<server>__<tool>` names become `<server>_<tool>` tools, every other tool of
    those servers being switched off. The agent never edits files.
    """
    source = AGENT_SOURCE_ROOT / f"{agent}.md"
    fields, body = split_frontmatter(source.read_text(encoding="utf-8"), source.relative_to(ROOT))
    description = require_string(fields.get("description"), f"{agent}.description")
    tools = json.loads(fields.get("tools", "[]"))
    bash = {"*": "deny"}
    mcp_tools: dict[str, bool] = {f"{server}_*": False for server in sorted(servers)}
    webfetch = "deny"
    for tool in tools:
        rule = CLAUDE_BASH_RULE.fullmatch(tool)
        plugin_tool = CLAUDE_PLUGIN_TOOL.fullmatch(tool)
        if rule:
            bash[f"{rule['prefix']}*"] = "allow"
        elif plugin_tool:
            server = next((name for name in servers if tool.endswith(f"_{name}__{plugin_tool['tool']}")), None)
            if server is None:
                raise ValueError(f"{agent}: {tool} names no OpenCode MCP server")
            mcp_tools[f"{server}_{plugin_tool['tool']}"] = True
        elif tool == "WebFetch":
            webfetch = "allow"
        elif tool not in {"Read", "Glob", "Grep"}:
            raise ValueError(f"{agent}: no OpenCode translation for tool {tool}")
    lines = [
        "---",
        f"description: {json.dumps(description)}",
        "mode: subagent",
        "permission:",
        "  edit: deny",
        f"  webfetch: {webfetch}",
        "  bash:",
        *(f"    {json.dumps(pattern)}: {decision}" for pattern, decision in bash.items()),
        "tools:",
        *(f"  {json.dumps(name)}: {str(enabled).lower()}" for name, enabled in mcp_tools.items()),
        "---",
    ]
    return "\n".join(lines) + "\n" + body


def render_opencode_config(plugins: list[dict[str, object]]) -> dict[str, object]:
    """The opencode.json fragment: every plugin's MCP servers plus read access to rendered PNGs."""
    servers: dict[str, object] = {}
    for plugin in plugins:
        servers.update(render_mcp_servers(plugin["name"], plugin.get("mcp", []), "opencode"))
    return {
        "$schema": "https://opencode.ai/config.json",
        "mcp": {"servers": servers},
        # render_preview writes PNGs to per-server temporary directories outside the project (#105).
        "permission": {"external_directory": {"*/compose-preview-mcp-*": "allow"}},
    }


def render_opencode_bundle(
    source: dict[str, object], plugins: list[dict[str, object]]
) -> dict[str, bytes]:
    """opencode/: the agents, skills and plugins OpenCode loads from its config directory."""
    bundle = source.get("opencode")
    if not isinstance(bundle, dict):
        raise ValueError("opencode must be an object")
    servers = {
        entry["name"]: plugin["name"] for plugin in plugins for entry in plugin.get("mcp", [])
    }
    files: dict[str, bytes] = {}
    for agent in bundle.get("agents", []):
        if not SKILL_NAME.fullmatch(agent):
            raise ValueError(f"invalid agent name: {agent}")
        files[f"agents/{agent}.md"] = render_opencode_agent(agent, servers).encode("utf-8")
    for skill in bundle.get("skills", []):
        if not SKILL_NAME.fullmatch(skill):
            raise ValueError(f"invalid skill name: {skill}")
        for relative, path in skill_files(skill).items():
            files[f"skills/{skill}/{relative}"] = path.read_bytes()
    for plugin in bundle.get("plugins", []):
        if not SKILL_NAME.fullmatch(plugin):
            raise ValueError(f"invalid OpenCode plugin name: {plugin}")
        files[f"plugins/{plugin}.js"] = (OPENCODE_SOURCE_ROOT / f"{plugin}.js").read_bytes()
    files["opencode.json"] = (
        json.dumps(render_opencode_config(plugins), indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    return files


def write_opencode_bundle(source: dict[str, object], plugins: list[dict[str, object]]) -> None:
    files = render_opencode_bundle(source, plugins)
    ledger = OPENCODE_ROOT / OPENCODE_LEDGER_NAME
    previous = json.loads(ledger.read_text(encoding="utf-8")) if ledger.is_file() else []
    for stale in set(previous) - set(files):
        (OPENCODE_ROOT / stale).unlink(missing_ok=True)
    for relative, content in files.items():
        target = OPENCODE_ROOT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    write_json(ledger, sorted(files))


def write_hook(plugin_root: Path, command: str) -> None:
    command_path = Path(command)
    if (
        command_path.is_absolute()
        or ".." in command_path.parts
        or command_path.parts[:1] != ("scripts",)
        or len(command_path.parts) != 2
    ):
        raise ValueError(f"hook command must be a plugin-local script: {command}")
    source = HOOK_SOURCE_ROOT / command_path.name
    if not source.is_file():
        raise ValueError(f"missing shared hook source: {source.relative_to(ROOT)}")
    target = plugin_root / command_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    target.chmod(source.stat().st_mode)


def write_asset(plugin_root: Path, asset: str) -> None:
    asset_path = Path(asset)
    if asset_path.is_absolute() or ".." in asset_path.parts or len(asset_path.parts) != 1:
        raise ValueError(f"asset must be a source-root file name: {asset}")
    source = ASSET_SOURCE_ROOT / asset_path
    if not source.is_file():
        raise ValueError(f"missing shared asset source: {source.relative_to(ROOT)}")
    target = plugin_root / "assets" / asset_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.read_bytes())


def write_sidecar(plugin_root: Path, sidecar: str) -> None:
    if not SKILL_NAME.fullmatch(sidecar):
        raise ValueError(f"invalid sidecar name: {sidecar}")
    source_manifest = SIDECAR_SOURCE_ROOT / sidecar / "sidecar.json"
    if not source_manifest.is_file():
        raise ValueError(f"missing shared sidecar manifest: {source_manifest.relative_to(ROOT)}")
    target_manifest = plugin_root / "sidecars" / sidecar / "sidecar.json"
    write_json(target_manifest, json.loads(source_manifest.read_text(encoding="utf-8")))
    launcher_source = SIDECAR_SOURCE_ROOT / SIDECAR_LAUNCHER_NAME
    if not launcher_source.is_file():
        raise ValueError(f"missing shared sidecar launcher: {launcher_source.relative_to(ROOT)}")
    launcher_target = plugin_root / "sidecars" / SIDECAR_LAUNCHER_NAME
    launcher_target.parent.mkdir(parents=True, exist_ok=True)
    launcher_target.write_text(launcher_source.read_text(encoding="utf-8"), encoding="utf-8")
    launcher_target.chmod(0o755)


def synchronize_generated_sidecars(plugin_root: Path, sidecars: list[str]) -> None:
    import shutil

    sidecars_root = plugin_root / "sidecars"
    ledger = sidecars_root / SIDECAR_LEDGER_NAME
    previous: list[str] = []
    if ledger.is_file():
        value = json.loads(ledger.read_text(encoding="utf-8"))
        if (
            not isinstance(value, dict)
            or not isinstance(value.get("sidecars"), list)
            or not all(isinstance(item, str) for item in value["sidecars"])
        ):
            raise ValueError(f"invalid generated sidecar ledger: {ledger.relative_to(ROOT)}")
        previous = value["sidecars"]
    expected = set(sidecars)
    for item in previous:
        if not SKILL_NAME.fullmatch(item):
            raise ValueError(f"invalid generated sidecar ledger entry: {item!r}")
        if item not in expected:
            stale_dir = sidecars_root / item
            if stale_dir.is_dir():
                shutil.rmtree(stale_dir)
    if sidecars:
        write_json(ledger, {"sidecars": sorted(expected)})
    else:
        ledger.unlink(missing_ok=True)
        (sidecars_root / SIDECAR_LAUNCHER_NAME).unlink(missing_ok=True)
        if sidecars_root.is_dir() and not any(sidecars_root.iterdir()):
            sidecars_root.rmdir()


def write_readme(plugin_root: Path, name: str) -> None:
    """Every plugin folder carries its own README and LICENSE (directory submission rules)."""
    source = README_SOURCE_ROOT / f"{name}.md"
    if not source.is_file():
        raise ValueError(f"missing plugin README source: {source.relative_to(ROOT)}")
    plugin_root.mkdir(parents=True, exist_ok=True)
    (plugin_root / "README.md").write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    (plugin_root / "LICENSE").write_text(LICENSE_SOURCE.read_text(encoding="utf-8"), encoding="utf-8")


def validate_user_config(plugin_name: str, value: object) -> dict[str, dict[str, object]]:
    if not isinstance(value, dict):
        raise ValueError(f"{plugin_name}.userConfig must be an object")
    for key, option in value.items():
        if not isinstance(key, str) or not USER_CONFIG_KEY.fullmatch(key):
            raise ValueError(f"{plugin_name}.userConfig key {key!r} must be an identifier")
        if not isinstance(option, dict):
            raise ValueError(f"{plugin_name}.userConfig.{key} must be an object")
        unknown = set(option) - USER_CONFIG_FIELDS
        if unknown:
            raise ValueError(
                f"{plugin_name}.userConfig.{key} has unsupported fields: {', '.join(sorted(unknown))}"
            )
        if option.get("type") != "string":
            raise ValueError(f"{plugin_name}.userConfig.{key}.type must be string")
        for field in ("title", "description"):
            require_string(option.get(field), f"{plugin_name}.userConfig.{key}.{field}")
        for field in ("sensitive", "required"):
            if field in option and not isinstance(option[field], bool):
                raise ValueError(f"{plugin_name}.userConfig.{key}.{field} must be a boolean")
    return value


HOOK_ROOT = "${CLAUDE_PLUGIN_ROOT}/"


def hook_command(script: str, harness: str) -> str:
    """Quote the expanded plugin root so install paths containing spaces still work."""
    return f'"{HOOK_ROOT}{script}" --harness={harness}'


def hook_script(command: str) -> str | None:
    """Return the plugin-relative script from a generated command, quoted or legacy unquoted."""
    if command.startswith(f'"{HOOK_ROOT}'):
        end = command.find('"', 1)
        return command[len(HOOK_ROOT) + 1 : end] if end > 0 else None
    if command.startswith(HOOK_ROOT):
        return command.removeprefix(HOOK_ROOT).split(" ", 1)[0]
    return None


def render_hooks(plugin_name: str, entries: object, harness: str) -> dict[str, object]:
    """Render one harness's hook manifest; every command names its harness explicitly."""
    if harness not in HOOK_MANIFESTS:
        raise ValueError(f"{plugin_name}.hooks: unsupported hook harness {harness}")
    if not isinstance(entries, list):
        raise ValueError(f"{plugin_name}.hooks must be a list")

    hooks: dict[str, list[dict[str, object]]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError(f"{plugin_name}.hooks entries must be objects")
        event = require_string(entry.get("event"), f"{plugin_name}.hooks.event")
        command = require_string(entry.get("command"), f"{plugin_name}.hooks.command")
        matcher = entry.get("matcher")
        timeout = entry.get("timeout")
        if matcher is not None and (not isinstance(matcher, str) or not matcher):
            raise ValueError(f"{plugin_name}.hooks.{event}.matcher must be a non-empty string")
        if timeout is not None and (
            not isinstance(timeout, int) or isinstance(timeout, bool) or timeout <= 0
        ):
            raise ValueError(f"{plugin_name}.hooks.{event}.timeout must be a positive integer")
        command_path = Path(command)
        if (
            command_path.is_absolute()
            or ".." in command_path.parts
            or command_path.parts[:1] != ("scripts",)
            or len(command_path.parts) != 2
        ):
            raise ValueError(f"{plugin_name}.hooks.command must be a plugin-local script")
        if not (HOOK_SOURCE_ROOT / command_path.name).is_file():
            raise ValueError(
                f"missing shared hook source: {(HOOK_SOURCE_ROOT / command_path.name).relative_to(ROOT)}"
            )
        command_hook: dict[str, object] = {
            "command": hook_command(command, harness),
            "type": "command",
        }
        if timeout is not None:
            command_hook["timeout"] = timeout
        event_hook: dict[str, object] = {"hooks": [command_hook]}
        if matcher is not None:
            event_hook["matcher"] = matcher
        hooks.setdefault(event, []).append(event_hook)
    return {"hooks": hooks}


def render_antigravity_hooks(plugin_name: str, entries: object) -> dict[str, object] | None:
    """Render Antigravity's hooks.json, or None when no hook maps to an Antigravity event."""
    render_hooks(plugin_name, entries, "claude")  # Same validation as the other harnesses.
    assert isinstance(entries, list)
    events: dict[str, list[dict[str, object]]] = {}
    for entry in entries:
        event = entry["event"].strip()
        if event not in ANTIGRAVITY_HOOK_EVENTS:
            continue
        script = f"./{entry['command'].strip()}"
        events.setdefault(event, []).append(
            {"command": f"{script} --harness=antigravity", "type": "command"}
        )
    if not events:
        return None
    return {plugin_name: {"enabled": True, **events}}


def synchronize_generated_agents(plugin_root: Path, agents: list[str], directory: str) -> None:
    agents_root = plugin_root / directory
    ledger = agents_root / AGENT_LEDGER_NAME
    previous: list[str] = []
    if ledger.is_file():
        value = json.loads(ledger.read_text(encoding="utf-8"))
        if (
            not isinstance(value, dict)
            or not isinstance(value.get("agents"), list)
            or not all(isinstance(agent, str) for agent in value["agents"])
        ):
            raise ValueError(f"invalid generated agent ledger: {ledger.relative_to(ROOT)}")
        previous = value["agents"]
    expected = {f"{agent}.md" for agent in agents}
    for agent in previous:
        agent_path = Path(agent)
        if agent_path.is_absolute() or ".." in agent_path.parts or len(agent_path.parts) != 1:
            raise ValueError(f"invalid generated agent ledger entry: {agent!r}")
        if agent not in expected:
            (agents_root / agent_path).unlink(missing_ok=True)
    if agents:
        write_json(ledger, {"agents": sorted(expected)})
    else:
        ledger.unlink(missing_ok=True)


def remove_obsolete_generated_hooks(plugin_root: Path, hooks: list[object]) -> None:
    """Remove only scripts proven to belong to a previously generated hook manifest."""
    expected = {
        Path(hook["command"]).name
        for hook in hooks
        if isinstance(hook, dict) and isinstance(hook.get("command"), str)
    }
    for manifest_path in HOOK_MANIFESTS.values():
        manifest = plugin_root / manifest_path
        if not manifest.is_file():
            continue
        previous = json.loads(manifest.read_text(encoding="utf-8"))
        for event_entries in previous.get("hooks", {}).values():
            if not isinstance(event_entries, list):
                continue
            for event_entry in event_entries:
                if not isinstance(event_entry, dict):
                    continue
                for hook in event_entry.get("hooks", []):
                    if not isinstance(hook, dict):
                        continue
                    command = hook.get("command")
                    script = hook_script(command) if isinstance(command, str) else None
                    if not script or not script.startswith("scripts/"):
                        continue
                    relative = script.removeprefix("scripts/")
                    if not relative or "/" in relative or relative in expected:
                        continue
                    (plugin_root / "scripts" / relative).unlink(missing_ok=True)


def synchronize_generated_assets(plugin_root: Path, assets: list[str]) -> None:
    assets_root = plugin_root / "assets"
    ledger = assets_root / ASSET_LEDGER_NAME
    previous: list[str] = []
    if ledger.is_file():
        value = json.loads(ledger.read_text(encoding="utf-8"))
        if (
            not isinstance(value, dict)
            or not isinstance(value.get("assets"), list)
            or not all(isinstance(asset, str) for asset in value["assets"])
        ):
            raise ValueError(f"invalid generated asset ledger: {ledger.relative_to(ROOT)}")
        previous = value["assets"]
    expected = set(assets)
    for asset in previous:
        asset_path = Path(asset)
        if (
            asset_path.is_absolute()
            or ".." in asset_path.parts
            or len(asset_path.parts) != 1
        ):
            raise ValueError(f"invalid generated asset ledger entry: {asset!r}")
        if asset not in expected:
            (assets_root / asset_path).unlink(missing_ok=True)
    if assets:
        write_json(ledger, {"assets": assets})
    else:
        ledger.unlink(missing_ok=True)


def header_map(plugin_name: str, entry: dict[str, object], field: str, headers: dict[str, str]) -> dict[str, str]:
    """Return a per-header mapping that must name exactly the entry's headers."""
    name = entry.get("name")
    mapping = entry.get(field, {})
    if not isinstance(mapping, dict) or not all(
        isinstance(key, str) and key and isinstance(value, str) and value
        for key, value in mapping.items()
    ):
        raise ValueError(f"{plugin_name}.mcp.{name}.{field} must map header names to non-empty strings")
    if set(mapping) != set(headers):
        raise ValueError(f"{plugin_name}.mcp.{name}.{field} must cover the same headers as headers")
    return mapping


def env_headers(plugin_name: str, entry: dict[str, object], headers: dict[str, str]) -> dict[str, str]:
    mapping = header_map(plugin_name, entry, "envHeaders", headers)
    for header, env in mapping.items():
        if not ENV_NAME.fullmatch(env):
            raise ValueError(
                f"{plugin_name}.mcp.{entry.get('name')}.envHeaders.{header} must be an environment variable name"
            )
    return mapping


def render_mcp_servers(
    plugin_name: str,
    entries: object,
    harness: str,
    user_config: dict[str, dict[str, object]] | None = None,
) -> dict[str, object]:
    if not isinstance(entries, list):
        raise ValueError(f"{plugin_name}.mcp must be a list")

    servers: dict[str, object] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError(f"{plugin_name}.mcp entries must be objects")
        name = require_string(entry.get("name"), f"{plugin_name}.mcp.name")
        kind = require_string(entry.get("kind"), f"{plugin_name}.mcp.{name}.kind")
        if name in servers:
            raise ValueError(f"{plugin_name}.mcp contains duplicate server {name}")
        if kind == "stdio":
            command = require_string(entry.get("command"), f"{plugin_name}.mcp.{name}.command")
            args = entry.get("args", [])
            env = entry.get("env")
            if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
                raise ValueError(f"{plugin_name}.mcp.{name}.args must be a list of strings")
            server: dict[str, object] = {"args": args, "command": command}
            fallback = entry.get("pathFallback")
            if fallback is not None and harness == "claude":
                # Claude Code starts MCP servers with its own PATH, and a SessionStart hook cannot
                # change it, so a CLI only in the installer's bin directory would never launch.
                # Append that directory (unbraced, so Claude does not expand it) and exec.
                fallback = require_string(fallback, f"{plugin_name}.mcp.{name}.pathFallback")
                if "${" in fallback or "'" in fallback:
                    raise ValueError(f"{plugin_name}.mcp.{name}.pathFallback must use unbraced $VARs")
                server = {
                    "args": ["-c", f'PATH="$PATH:{fallback}"; export PATH; exec "$0" "$@"', command, *args],
                    "command": "sh",
                }
            if harness == "opencode":
                server = {"codemode": False, "command": [command, *args], "type": "local"}
            if env is not None:
                if not isinstance(env, dict) or not all(
                    isinstance(key, str) and isinstance(value, str) for key, value in env.items()
                ):
                    raise ValueError(f"{plugin_name}.mcp.{name}.env must map strings to strings")
                server["environment" if harness == "opencode" else "env"] = env
        elif kind == "http":
            url = require_string(entry.get("url"), f"{plugin_name}.mcp.{name}.url")
            headers = entry.get("headers", {})
            if not isinstance(headers, dict) or not all(
                isinstance(key, str) and isinstance(value, str) for key, value in headers.items()
            ):
                raise ValueError(f"{plugin_name}.mcp.{name}.headers must map strings to strings")
            if harness == "antigravity":
                server = {"headers": headers, "serverUrl": url}
            elif harness == "codex":
                server = {
                    "env_http_headers": env_headers(plugin_name, entry, headers),
                    "type": "http",
                    "url": url,
                }
            elif harness == "cursor":
                # Cursor and Gemini CLI expand ${VAR}, but not ${VAR:-default}.
                server = {
                    "headers": {
                        header: f"${{{env}}}"
                        for header, env in env_headers(plugin_name, entry, headers).items()
                    },
                    "type": "http",
                    "url": url,
                }
            elif harness == "gemini":
                server = {
                    "headers": {
                        header: f"${{{env}}}"
                        for header, env in env_headers(plugin_name, entry, headers).items()
                    },
                    "httpUrl": url,
                }
            elif harness == "opencode":
                # OpenCode expands {env:VAR}; it also runs OAuth for a remote server by default.
                server = {
                    "codemode": False,
                    "headers": {
                        header: f"{{env:{env}}}"
                        for header, env in env_headers(plugin_name, entry, headers).items()
                    },
                    "type": "remote",
                    "url": url,
                }
            elif harness == "claude":
                # Credentials come from a sensitive userConfig option, never the user's environment.
                keys = header_map(plugin_name, entry, "userConfigHeaders", headers) if headers else {}
                for header, key in keys.items():
                    if key not in (user_config or {}):
                        raise ValueError(
                            f"{plugin_name}.mcp.{name}.userConfigHeaders.{header} names undeclared userConfig {key}"
                        )
                server = {
                    "headers": {header: f"${{user_config.{key}}}" for header, key in keys.items()},
                    "type": "http",
                    "url": url,
                }
            else:
                raise ValueError(f"{plugin_name}.mcp.{name}: unsupported MCP harness {harness}")
        else:
            raise ValueError(f"{plugin_name}.mcp.{name}.kind must be stdio or http")
        servers[name] = server
    return servers


def render_antigravity_manifest(
    *,
    plugin: dict[str, object],
    owner: str,
    repository: str,
    license_name: str,
) -> dict[str, object]:
    """Render root plugin.json for Antigravity (v1 schema + agy 1.4.x metadata)."""
    name = plugin["name"]
    interface = plugin.get("interface")
    if not isinstance(interface, dict):
        raise ValueError(f"{name}.interface must be an object")
    default_prompt = interface.get("defaultPrompt", [])
    if not isinstance(default_prompt, list):
        raise ValueError(f"{name}.interface.defaultPrompt must be a list of non-empty strings")
    rendered_prompts = [
        require_string(prompt, f"{name}.interface.defaultPrompt[{index}]")
        for index, prompt in enumerate(default_prompt)
    ]
    return {
        "$schema": ANTIGRAVITY_SCHEMA,
        "author": {"name": owner},
        "description": plugin["description"],
        "displayName": require_string(interface.get("displayName"), f"{name}.interface.displayName"),
        "homepage": f"{repository}/tree/main/plugins/{name}",
        "keywords": plugin.get("keywords", []),
        "license": license_name,
        "name": name,
        "repository": repository,
        "suggestedPrompts": rendered_prompts,
        "version": plugin["version"],
    }


def render_claude_manifest(
    *,
    plugin: dict[str, object],
    user_config: dict[str, dict[str, object]],
    owner: str,
    repository: str,
    license_name: str,
) -> dict[str, object]:
    interface = plugin.get("interface")
    manifest: dict[str, object] = {
        "author": {"name": owner},
        "description": plugin["description"],
        "keywords": plugin.get("keywords", []),
        "license": license_name,
        "name": plugin["name"],
        "repository": repository,
        "version": plugin["version"],
    }
    if isinstance(interface, dict) and interface.get("displayName"):
        manifest["displayName"] = require_string(
            interface["displayName"], f"{plugin['name']}.interface.displayName"
        )
    if user_config:
        manifest["userConfig"] = user_config
    agents = plugin.get("agents", [])
    if agents:
        # Replaces the default agents/ scan, which holds the portable copies (#147).
        manifest["agents"] = [f"./{CLAUDE_AGENT_DIR}/{agent}.md" for agent in agents]
    return manifest


def render_cursor_manifest(
    *,
    plugin: dict[str, object],
    user_config: dict[str, dict[str, object]],
    owner: str,
    repository: str,
    license_name: str,
) -> dict[str, object]:
    """Render .cursor-plugin/plugin.json (schema: github.com/cursor/plugins/schemas)."""
    name = plugin["name"]
    interface = plugin.get("interface")
    if not isinstance(interface, dict):
        raise ValueError(f"{name}.interface must be an object")
    manifest: dict[str, object] = {
        "author": {"name": owner},
        "category": "developer-tools",
        "description": plugin["description"],
        "displayName": require_string(interface.get("displayName"), f"{name}.interface.displayName"),
        "homepage": f"{repository}/tree/main/plugins/{name}",
        "keywords": plugin.get("keywords", []),
        "license": license_name,
        "name": name,
        "repository": repository,
        "version": plugin["version"],
    }
    if plugin.get("skills"):
        manifest["skills"] = "./skills/"
    if plugin.get("agents"):
        manifest["agents"] = "./agents/"
    if plugin.get("hooks"):
        # hooks/hooks.json holds Claude Code hooks, which Cursor would otherwise
        # discover by default; its events and payloads differ, so ship none (#59).
        manifest["hooks"] = {"hooks": {}, "version": 1}
    mcp = plugin.get("mcp", [])
    if mcp:
        manifest["mcpServers"] = render_mcp_servers(name, mcp, "cursor")
        variables = cursor_variables(name, mcp, user_config)
        if variables:
            manifest["variables"] = {"properties": variables, "required": [], "type": "object"}
    return manifest


def secret_env_options(
    plugin_name: str, entries: list[object], user_config: dict[str, dict[str, object]]
) -> dict[str, dict[str, object]]:
    """Map each header environment variable to the userConfig option that documents it."""
    options: dict[str, dict[str, object]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("kind") != "http" or not entry.get("headers"):
            continue
        headers = entry["headers"]
        envs = env_headers(plugin_name, entry, headers)
        keys = header_map(plugin_name, entry, "userConfigHeaders", headers)
        for header, env in envs.items():
            option = user_config.get(keys[header])
            if option is None:
                raise ValueError(
                    f"{plugin_name}.mcp.{entry['name']}.userConfigHeaders.{header} names undeclared userConfig {keys[header]}"
                )
            options[env] = option
    return options


def cursor_variables(
    plugin_name: str, entries: list[object], user_config: dict[str, dict[str, object]]
) -> dict[str, object]:
    return {
        env: {"description": option["description"], "title": option["title"], "type": "string"}
        for env, option in secret_env_options(plugin_name, entries, user_config).items()
    }


def render_gemini_extension(source: dict[str, object], plugins: list[dict[str, object]]) -> dict[str, object]:
    """Render the repository-root gemini-extension.json that wraps every listed plugin's servers."""
    config = source.get("gemini")
    if not isinstance(config, dict):
        raise ValueError("gemini must be an object")
    name = require_string(config.get("name"), "gemini.name")
    version = require_string(config.get("version"), "gemini.version")
    if SEMVER.fullmatch(version) is None:
        raise ValueError("gemini.version must use strict semver")
    included = config.get("plugins")
    if not isinstance(included, list) or not included:
        raise ValueError("gemini.plugins must be a non-empty list of plugin names")
    by_name = {plugin["name"]: plugin for plugin in plugins}
    servers: dict[str, object] = {}
    settings: dict[str, dict[str, object]] = {}
    for plugin_name in included:
        plugin = by_name.get(plugin_name)
        if plugin is None:
            raise ValueError(f"gemini.plugins names unknown plugin {plugin_name!r}")
        mcp = plugin.get("mcp", [])
        user_config = plugin.get("userConfig", {})
        for server_name, server in render_mcp_servers(plugin_name, mcp, "gemini").items():
            if server_name in servers:
                raise ValueError(f"gemini: duplicate MCP server {server_name}")
            servers[server_name] = server
        settings.update(secret_env_options(plugin_name, mcp, user_config))
    extension: dict[str, object] = {
        "description": require_string(config.get("description"), "gemini.description"),
        "mcpServers": servers,
        "name": name,
        "version": version,
    }
    if settings:
        # Gemini CLI passes only declared variables to MCP servers and header expansion.
        extension["settings"] = [
            {
                "description": option["description"],
                "envVar": env,
                "name": option["title"],
                "sensitive": bool(option.get("sensitive", False)),
            }
            for env, option in settings.items()
        ]
    return extension


def render_registry_server(source: dict[str, object], plugins: list[dict[str, object]]) -> dict[str, object]:
    """Render server.json for the Official MCP Registry from the plugin's remote server entry."""
    config = source.get("registry")
    if not isinstance(config, dict):
        raise ValueError("registry must be an object")
    plugin_name = require_string(config.get("plugin"), "registry.plugin")
    server_name = require_string(config.get("server"), "registry.server")
    plugin = next((plugin for plugin in plugins if plugin["name"] == plugin_name), None)
    if plugin is None:
        raise ValueError(f"registry.plugin names unknown plugin {plugin_name!r}")
    entry = next(
        (
            entry
            for entry in plugin.get("mcp", [])
            if isinstance(entry, dict) and entry.get("name") == server_name
        ),
        None,
    )
    if entry is None or entry.get("kind") != "http":
        raise ValueError(f"registry.server must name an http MCP server of {plugin_name}")
    description = require_string(config.get("description"), "registry.description")
    if len(description) > 100:
        raise ValueError("registry.description must be at most 100 characters")
    user_config = plugin.get("userConfig", {})
    keys = header_map(plugin_name, entry, "userConfigHeaders", entry.get("headers", {}))
    remote: dict[str, object] = {"type": "streamable-http", "url": entry["url"]}
    if keys:
        remote["headers"] = [
            {
                "description": user_config[key]["description"],
                "isRequired": bool(user_config[key].get("required", False)),
                "isSecret": bool(user_config[key].get("sensitive", False)),
                "name": header,
            }
            for header, key in keys.items()
        ]
    return {
        "$schema": MCP_REGISTRY_SCHEMA,
        "description": description,
        "name": require_string(config.get("name"), "registry.name"),
        "remotes": [remote],
        "repository": {
            "source": "github",
            "url": require_string(config.get("repository"), "registry.repository"),
        },
        "title": require_string(config.get("title"), "registry.title"),
        "version": require_string(config.get("version"), "registry.version"),
    }


def render_external_marketplace_entries(source: dict, local_names: set[str]) -> list[dict]:
    """Marketplace entries for plugins that live in another repository.

    Claude Code and Codex both install a `git-subdir` source, so one marketplace can list the
    canonical skill bundles from yschimke/skills next to the wiring plugins built here. Cursor's
    marketplace is left to local plugins until a smoke test covers that source type.
    """
    external = source.get("externalPlugins", [])
    if not isinstance(external, list):
        raise ValueError("externalPlugins must be a list")
    entries = []
    for plugin in external:
        if not isinstance(plugin, dict):
            raise ValueError("each external plugin must be an object")
        name = require_string(plugin.get("name"), "externalPlugins.name")
        if name in local_names:
            raise ValueError(f"duplicate plugin name: {name}")
        local_names.add(name)
        url = require_string(plugin.get("url"), f"{name}.url")
        if not url.startswith("https://github.com/") or not url.endswith(".git"):
            raise ValueError(f"{name}.url must be an https://github.com/... .git URL")
        path = require_string(plugin.get("path"), f"{name}.path")
        if path.startswith("/") or ".." in path.split("/"):
            raise ValueError(f"{name}.path must be a relative path inside the repository")
        entry_source = {"source": "git-subdir", "url": url, "path": path}
        ref = plugin.get("ref")
        if ref is not None:
            entry_source["ref"] = require_string(ref, f"{name}.ref")
        entries.append(
            {
                "description": require_string(plugin.get("description"), f"{name}.description"),
                "name": name,
                "source": entry_source,
            }
        )
    return entries


def main() -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    repository = require_string(source.get("repository"), "repository")
    license_name = require_string(source.get("license"), "license")
    owner = require_string(source.get("owner"), "owner")
    marketplace_description = require_string(source.get("description"), "description")
    plugins = source.get("plugins")
    if not isinstance(plugins, list) or not plugins:
        raise ValueError("plugins must be a non-empty list")

    marketplace_plugins = []
    cursor_marketplace_plugins = []
    names: set[str] = set()
    for plugin in plugins:
        if not isinstance(plugin, dict):
            raise ValueError("each plugin must be an object")
        name = require_string(plugin.get("name"), "plugin.name")
        version = require_string(plugin.get("version"), f"{name}.version")
        if SEMVER.fullmatch(version) is None:
            raise ValueError(f"{name}.version must use strict semver")
        description = require_string(plugin.get("description"), f"{name}.description")
        keywords = plugin.get("keywords", [])
        skills = plugin.get("skills", [])
        agents = plugin.get("agents", [])
        sidecars = plugin.get("sidecars", [])
        hooks = plugin.get("hooks", [])
        assets = plugin.get("assets", [])
        mcp = plugin.get("mcp", [])
        apps = validate_apps(name, plugin.get("apps", {}), mcp)
        interface = plugin.get("interface")
        user_config = validate_user_config(name, plugin.get("userConfig", {}))
        if name in names:
            raise ValueError(f"duplicate plugin name: {name}")
        if not isinstance(keywords, list) or not all(isinstance(word, str) for word in keywords):
            raise ValueError(f"{name}.keywords must be a list of strings")
        if not isinstance(skills, list) or not all(isinstance(skill, str) for skill in skills):
            raise ValueError(f"{name}.skills must be a list of strings")
        if not isinstance(agents, list) or not all(isinstance(agent, str) for agent in agents):
            raise ValueError(f"{name}.agents must be a list of strings")
        if not isinstance(sidecars, list) or not all(isinstance(sidecar, str) for sidecar in sidecars):
            raise ValueError(f"{name}.sidecars must be a list of strings")
        if not isinstance(hooks, list):
            raise ValueError(f"{name}.hooks must be a list")
        if not isinstance(assets, list) or not all(isinstance(asset, str) for asset in assets):
            raise ValueError(f"{name}.assets must be a list of strings")
        names.add(name)

        root = ROOT / "plugins" / name
        write_readme(root, name)
        write_skills(root, skills)
        codex_skills, codex_skills_path = codex_skill_config(plugin)
        write_codex_skills(root, plugin)
        write_rules(root, name, plugin.get("rules"))
        for directory in (PORTABLE_AGENT_DIR, CLAUDE_AGENT_DIR):
            synchronize_generated_agents(root, agents, directory)
        for agent in agents:
            write_agent(root, agent)
        synchronize_generated_sidecars(root, sidecars)
        for sidecar in sidecars:
            write_sidecar(root, sidecar)
        remove_obsolete_generated_hooks(root, hooks)
        synchronize_generated_assets(root, assets)
        for asset in assets:
            write_asset(root, asset)
        for harness, manifest_path in HOOK_MANIFESTS.items():
            if hooks:
                write_json(root / manifest_path, render_hooks(name, hooks, harness))
            else:
                (root / manifest_path).unlink(missing_ok=True)
        antigravity_hooks = render_antigravity_hooks(name, hooks) if hooks else None
        if antigravity_hooks:
            write_json(root / ANTIGRAVITY_HOOK_MANIFEST, antigravity_hooks)
        else:
            (root / ANTIGRAVITY_HOOK_MANIFEST).unlink(missing_ok=True)
        for hook in hooks:
            write_hook(root, hook["command"])
        write_json(
            root / "plugin.json",
            render_antigravity_manifest(
                plugin=plugin,
                owner=owner,
                repository=repository,
                license_name=license_name,
            ),
        )
        write_json(
            root / ".claude-plugin" / "plugin.json",
            render_claude_manifest(
                plugin=plugin,
                user_config=user_config,
                owner=owner,
                repository=repository,
                license_name=license_name,
            ),
        )
        write_json(
            root / ".cursor-plugin" / "plugin.json",
            render_cursor_manifest(
                plugin=plugin,
                user_config=user_config,
                owner=owner,
                repository=repository,
                license_name=license_name,
            ),
        )
        write_json(
            root / ".codex-plugin" / "plugin.json",
            render_codex_manifest(
                name=name,
                version=version,
                description=description,
                keywords=keywords,
                skills=codex_skills,
                skills_path=codex_skills_path,
                mcp=mcp,
                apps=apps,
                interface=interface,
                hooks=hooks,
                onboarding_skill=plugin.get("onboardingSkill"),
                owner=owner,
                repository=repository,
                license_name=license_name,
            ),
        )
        marketplace_plugins.append(
            {"description": description, "name": name, "source": f"./plugins/{name}"}
        )
        cursor_marketplace_plugins.append(
            {"description": description, "name": name, "source": f"plugins/{name}"}
        )
        if mcp:
            write_json(
                root / "mcp_config.json",
                {"mcpServers": render_mcp_servers(name, mcp, "antigravity")},
            )
            write_json(
                root / ".mcp.json",
                {"mcpServers": render_mcp_servers(name, mcp, "claude", user_config)},
            )
        else:
            (root / "mcp_config.json").unlink(missing_ok=True)
            (root / ".mcp.json").unlink(missing_ok=True)
        if apps:
            write_json(root / ".app.json", {"apps": apps})
        else:
            (root / ".app.json").unlink(missing_ok=True)

    write_json(
        ROOT / ".claude-plugin" / "marketplace.json",
        {
            "metadata": {"description": marketplace_description},
            "name": MARKETPLACE_NAME,
            "owner": {"name": owner},
            "plugins": marketplace_plugins + render_external_marketplace_entries(source, names),
        },
    )
    write_json(
        ROOT / ".cursor-plugin" / "marketplace.json",
        {
            "metadata": {"description": marketplace_description},
            "name": MARKETPLACE_NAME,
            "owner": {"name": owner},
            "plugins": cursor_marketplace_plugins,
        },
    )
    # Gemini CLI reads gemini-extension.json only from the repository root, so the
    # repository ships one extension that wraps the servers of the listed plugins.
    write_json(ROOT / "gemini-extension.json", render_gemini_extension(source, plugins))
    write_json(ROOT / "server.json", render_registry_server(source, plugins))
    write_opencode_bundle(source, plugins)


if __name__ == "__main__":
    main()
