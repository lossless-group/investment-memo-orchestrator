"""The plugin: its skill states the method's rules (CONN-PLUG-01), and it is packaged
the way Claude's plugin docs say.

The skill is the one piece of agent-facing text that isn't generated from the
registry, and it governs every run, so each rule the spec lists (§Docs that
aren't generated, plus plan 7's "start with list_deals") is checked here as a
statement in the skill: every needle of a rule must appear in the same sentence
or bullet, so a rule can't pass by having its words scattered across the file.

Packaging follows Claude's *Plugin structure and testing* page
(https://claude.com/docs/plugins/build, checked 2026-10-10): the manifest alone in
``.claude-plugin/plugin.json``, the remote connector in ``.mcp.json`` at the
plugin root with no secrets, skills in ``skills/<name>/SKILL.md`` with the folder
named after the skill, a README of at least 40 words, and no top-level ``bin/``
(which stops claude.ai and Cowork installing the plugin at all).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest
import yaml

from src.connector.config import ConnectorSettings

from .conftest import REPO

PLUGIN = REPO / "plugin"
SKILL = PLUGIN / "skills" / "memopop" / "SKILL.md"
MANIFEST = PLUGIN / ".claude-plugin" / "plugin.json"
MCP_JSON = PLUGIN / ".mcp.json"
README = PLUGIN / "README.md"

#: The connector URL partners enter (spec §Auth). Written out, not derived, so a
#: changed default in the settings fails here too.
CONNECTOR_URL = "https://memopop.didi.sh/mcp"

#: Each rule, and the needles that must all appear in one statement of the skill.
RULES: dict[str, list[str]] = {
    "this is a multi-step pipeline with an artifact trail": [
        r"multi-step",
        r"pipeline",
        r"artifact trail",
    ],
    "start with list_deals": [r"\b(start|begin)\b", r"`list_deals`"],
    "always call next_step and do only what it says": [
        r"\balways\b",
        r"`next_step`",
        r"\bonly what (it|`next_step`) says\b",
    ],
    "show the partner every research file and wait for their approval": [
        r"\bshow\b",
        r"\bpartner\b",
        r"\bevery\b",
        r"\bresearch\b",
        r"\bwait\b",
        r"\bapprov",
    ],
    "submit research with partner_approved: true only once approved": [
        r"`partner_approved: true`",
        r"\b(after|once|until|when)\b",
        r"\bapprov",
    ],
    "on skipped, say so in one line and continue": [
        r"`skipped`",
        r"\bone line\b",
        r"\bcontinue\b",
    ],
    "on down, stop and tell the partner": [
        r"`down`",
        r"\bstop\b",
        r"\btell the partner\b",
    ],
}

#: "Thin": the skill points Claude at next_step, which carries the method. A
#: skill that grows past this is restating step instructions that belong on
#: the server, where they can improve without a plugin release.
MAX_SKILL_WORDS = 450


def _split_frontmatter(text: str) -> tuple[dict, str]:
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    assert match, "SKILL.md must open with YAML frontmatter between --- lines"
    return yaml.safe_load(match.group(1)) or {}, match.group(2)


def statements(body: str) -> list[str]:
    """The skill's body cut into sentences and bullets, whitespace collapsed, lowercased."""
    out: list[str] = []
    for block in re.split(r"\n\s*\n|\n(?=\s*(?:[-*]|\d+\.)\s)", body):
        block = " ".join(block.split())
        out += [s for s in re.split(r"(?<=[.!?])\s+(?=[A-Z`*])", block) if s]
    return [s.lower() for s in out]


def rule_holds(needles: list[str], sentences: list[str]) -> bool:
    return any(all(re.search(n, s) for n in needles) for s in sentences)


def _skill_body() -> str:
    return _split_frontmatter(SKILL.read_text(encoding="utf-8"))[1]


# ------------------------------------------------------------------ CONN-PLUG-01


@pytest.mark.spec("CONN-PLUG-01")
@pytest.mark.parametrize("rule", list(RULES))
def test_the_skill_states_each_rule(rule):
    assert SKILL.is_file(), f"no skill at {SKILL.relative_to(REPO)}"
    sentences = statements(_skill_body())
    assert rule_holds(RULES[rule], sentences), (
        f"The skill doesn't state: {rule}. Every one of {RULES[rule]} must appear in "
        "one sentence or bullet."
    )


#: Every word the rules look for, scattered so no sentence states any rule.
SCATTERED = """MemoPop is a multi-step tool. It is a pipeline. Each step leaves an artifact trail.
Start the app. Call `list_deals` when needed. Always be polite. `next_step` returns a step.
Do only what it says on the label. Show the deck. The partner may like every slide.
Research takes time. Wait a moment. Approval is for later. Set `partner_approved: true`
in the form. A step can be `skipped`. Write one line. Continue later. `down` is an error
kind. Stop for lunch. Tell the partner about the weather."""


def test_the_rule_checker_needs_a_rule_stated_in_one_place():
    """Guard the checker itself: the same words scattered across sentences state no rule."""
    sentences = statements(SCATTERED)
    for rule, needles in RULES.items():
        assert all(any(re.search(n, s) for s in sentences) for n in needles), rule
        assert not rule_holds(needles, sentences), rule


@pytest.mark.spec("CONN-PLUG-01")
def test_the_skill_is_thin_and_named_for_its_folder():
    assert SKILL.is_file(), f"no skill at {SKILL.relative_to(REPO)}"
    meta, body = _split_frontmatter(SKILL.read_text(encoding="utf-8"))
    # Agent Skills spec: name matches the folder, lowercase and hyphens; a description.
    assert meta.get("name") == SKILL.parent.name == "memopop"
    description = str(meta.get("description") or "")
    assert 40 <= len(description) <= 1024, "the description says when to load the skill"
    assert "memo" in description.lower()
    words = len(re.findall(r"\S+", body))
    assert words <= MAX_SKILL_WORDS, f"the skill is {words} words; keep it thin"


# ------------------------------------------------------------------ packaging


def test_the_manifest_has_the_fields_every_app_reads():
    assert MANIFEST.is_file(), "the manifest lives at .claude-plugin/plugin.json"
    assert sorted(p.name for p in MANIFEST.parent.iterdir()) == ["plugin.json"]
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["name"] == "memopop"
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", manifest["name"])
    assert re.fullmatch(r"\d+\.\d+\.\d+", manifest["version"])
    assert manifest["displayName"] and manifest["description"]
    assert manifest["author"]["name"]
    assert manifest.get("license") or (PLUGIN / "LICENSE").is_file()


def test_the_connector_entry_points_at_memopop_with_no_secret():
    raw = MCP_JSON.read_text(encoding="utf-8")
    servers = json.loads(raw)["mcpServers"]
    assert list(servers) == ["memopop"]
    entry = servers["memopop"]
    assert entry == {"type": "http", "url": CONNECTOR_URL}
    assert ConnectorSettings().mcp_url == CONNECTOR_URL
    # Every person who installs the plugin receives this file.
    assert "sk-" not in raw and "authorization" not in raw.lower()


def test_the_plugin_installs_on_every_surface():
    assert not (PLUGIN / "bin").exists(), "a top-level bin/ stops claude.ai installing it"
    assert {p.name for p in (PLUGIN / "skills").iterdir() if p.is_dir()} == {"memopop"}
    readme = README.read_text(encoding="utf-8")
    prose = re.sub(r"```.*?```", "", readme, flags=re.DOTALL)
    assert len(re.findall(r"\b\w[\w'-]*\b", prose)) >= 40, "the directory needs 40+ words"


@pytest.mark.skipif(shutil.which("claude") is None, reason="Claude Code is not installed")
def test_claude_plugin_validate_passes():
    """``claude plugin validate`` is the validator the plugin docs name."""
    result = subprocess.run(
        ["claude", "plugin", "validate", str(PLUGIN)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
