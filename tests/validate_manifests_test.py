#!/usr/bin/env python3
"""Regression tests for the stdlib manifest schema validator."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import tempfile  # noqa: E402

from validate_manifests import validate_against_schema, validate_agent_tools  # noqa: E402


class ManifestSchemaValidationTest(unittest.TestCase):
    path = Path("fixture.json")
    schema = {
        "type": "object",
        "required": ["name", "schema", "keywords", "author"],
        "properties": {
            "name": {"type": "string", "pattern": "^[a-z-]+$"},
            "schema": {"const": "v1"},
            "keywords": {"type": "array", "items": {"type": "string"}},
            "author": {
                "type": "object",
                "required": ["name"],
                "properties": {"name": {"type": "string"}},
                "additionalProperties": False,
            },
        },
        "additionalProperties": False,
    }
    valid = {
        "name": "compose-preview",
        "schema": "v1",
        "keywords": ["compose", "preview"],
        "author": {"name": "Yuri Schimke"},
    }

    def validate(self, value: object, schema: object | None = None) -> None:
        validate_against_schema(value, schema or self.schema, manifest_path=self.path)

    def assert_invalid(self, value: object, message: str) -> None:
        with self.assertRaisesRegex(ValueError, message):
            self.validate(value)

    def test_accepts_manifest_matching_all_declared_constraints(self) -> None:
        self.validate(self.valid)

    def test_enforces_required_const_pattern_and_additional_properties(self) -> None:
        self.assert_invalid({**self.valid, "author": {}}, "missing required fields: name")
        self.assert_invalid({**self.valid, "schema": "v2"}, "must equal 'v1'")
        self.assert_invalid({**self.valid, "name": "Compose Preview"}, "does not match")
        self.assert_invalid({**self.valid, "unexpected": True}, "additional properties")

    def test_enforces_array_item_and_nested_object_types(self) -> None:
        self.assert_invalid({**self.valid, "keywords": ["compose", 3]}, r"keywords\[1\].*string")
        self.assert_invalid({**self.valid, "author": {"name": 3}}, r"author.name.*string")

    def test_rejects_schema_keywords_the_validator_would_ignore(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported schema keywords.*minLength"):
            self.validate("x", {"type": "string", "minLength": 2})

    def test_const_comparison_preserves_json_types_recursively(self) -> None:
        with self.assertRaisesRegex(ValueError, "must equal 1"):
            self.validate(True, {"const": 1})
        with self.assertRaisesRegex(ValueError, "must equal"):
            self.validate({"x": True}, {"const": {"x": 1}})

        self.validate(1.0, {"const": 1})

    def test_integer_accepts_integral_json_numbers_but_not_boolean_or_fractional_values(self) -> None:
        self.validate(1, {"type": "integer"})
        self.validate(1.0, {"type": "integer"})

        with self.assertRaisesRegex(ValueError, "must have type integer"):
            self.validate(True, {"type": "integer"})
        with self.assertRaisesRegex(ValueError, "must have type integer"):
            self.validate(1.5, {"type": "integer"})
        with self.assertRaisesRegex(ValueError, "must have type integer"):
            self.validate(float("inf"), {"type": "integer"})

    def test_pattern_only_applies_to_string_instances(self) -> None:
        self.validate(3, {"pattern": "x"})
        self.validate({"x": 1}, {"pattern": "x"})

        with self.assertRaisesRegex(ValueError, "does not match"):
            self.validate("other", {"pattern": "^x$"})
        with self.assertRaisesRegex(ValueError, "must have type string"):
            self.validate(3, {"type": "string", "pattern": "x"})

    def test_pattern_uses_ecmascript_anchor_and_ascii_shorthand_semantics(self) -> None:
        self.validate("a", {"pattern": "^a$"})
        with self.assertRaisesRegex(ValueError, "does not match"):
            self.validate("a\n", {"pattern": "^a$"})

        self.validate("1", {"pattern": r"^\d$"})
        with self.assertRaisesRegex(ValueError, "does not match"):
            self.validate("١", {"pattern": r"^\d$"})

    def test_rejects_pattern_constructs_without_portable_ecmascript_semantics(self) -> None:
        for pattern in (
            ".",
            r"\s",
            r"\B",
            r"\-",
            "]",
            "[]]",
            "[^]]",
            "[a]]",
            "(group)",
            "a{1,2}",
            "a++",
            "a*+",
            "a?+",
        ):
            with self.subTest(pattern=pattern):
                with self.assertRaisesRegex(ValueError, "invalid pattern"):
                    self.validate("anything", {"pattern": pattern})

        for pattern, value in (
            ("a*?", "a"),
            ("a+?", "a"),
            ("a??", "a"),
            (r"[\-]", "-"),
            ("[^a]", "b"),
        ):
            with self.subTest(pattern=pattern):
                self.validate(value, {"pattern": pattern})

    def test_rejects_unsupported_keywords_in_unvisited_child_schemas(self) -> None:
        schemas_and_values = [
            (
                {
                    "type": "object",
                    "properties": {"optional": {"type": "string", "minLength": 2}},
                },
                {},
            ),
            ({"type": "array", "items": {"type": "string", "minLength": 2}}, []),
            (
                {
                    "type": "object",
                    "additionalProperties": {"type": "string", "minLength": 2},
                },
                {},
            ),
        ]

        for schema, value in schemas_and_values:
            with self.subTest(schema=schema):
                with self.assertRaisesRegex(ValueError, "unsupported schema keywords.*minLength"):
                    self.validate(value, schema)


class AgentToolNamesTest(unittest.TestCase):
    plugins = [
        {"name": "compose-catalogs", "mcp": [{"name": "compose-preview-catalog", "kind": "http"}]},
        {"name": "compose-preview", "mcp": [{"name": "compose-preview-mcp", "kind": "stdio"}]},
    ]

    def check(self, *tools: str) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "agent.md"
            path.write_text(
                "---\nname: agent\ntools: " + json.dumps(list(tools)) + "\n---\n\nBody\n",
                encoding="utf-8",
            )
            validate_agent_tools(path, self.plugins)

    def test_accepts_advertised_names(self) -> None:
        self.check(
            "Read",
            "mcp__plugin_compose-catalogs_compose-preview-catalog__catalog_render_preview",
            "mcp__plugin_compose-catalogs_compose-preview-catalog__ui_builder_check_design",
            "mcp__plugin_compose-catalogs_compose-preview-catalog__status",
            "mcp__plugin_compose-preview_compose-preview-mcp__render_preview",
        )

    def test_rejects_unprefixed_hosted_catalog_tool(self) -> None:
        with self.assertRaisesRegex(ValueError, "catalog_render_preview"):
            self.check("mcp__plugin_compose-catalogs_compose-preview-catalog__render_preview")

    def test_rejects_tool_the_local_server_lacks(self) -> None:
        with self.assertRaisesRegex(ValueError, "local compose-preview server"):
            self.check("mcp__plugin_compose-preview_compose-preview-mcp__list_previews")
        with self.assertRaisesRegex(ValueError, "local compose-preview server"):
            self.check("mcp__plugin_compose-preview_compose-preview-mcp__catalog_render_preview")

    def test_rejects_unknown_server(self) -> None:
        with self.assertRaisesRegex(ValueError, "no MCP server"):
            self.check("mcp__plugin_compose-preview_other__render_preview")


if __name__ == "__main__":
    unittest.main()
