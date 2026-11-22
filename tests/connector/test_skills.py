"""The method served from the server (CONN-SKL-01 to CONN-SKL-04).

Partners who add the connector by URL get no plugin skill, and Claude only
loads MemoPop's tools (which start deferred) when the request names MemoPop.
So the server carries the method itself: instructions that lead with editing
finished memos, small skills served by ``list_skills`` and ``get_skill``, and
MCP prompts that name MemoPop and a skill.
"""

from __future__ import annotations

import re

import pytest
import yaml

from src.connector.mcp_app import INSTRUCTIONS

from .conftest import REPO, call, key_headers

SKILLS_DIR = REPO / "src" / "connector" / "skills"

#: The six skills the plan's first set names (Plan 9's routing).
FIRST_SET = {
    "fix-a-source-or-citation",
    "rewrite-a-section-from-its-research",
    "edit-wording",
    "just-edit-the-memo",
    "change-the-outline-for-this-memo",
    "compile-and-check-the-site",
}

#: The four entry prompts, by title, from the spec's "How partners get the method".
PROMPT_TITLES = {
    "Edit a memo",
    "Fix a citation",
    "Change the outline for this memo",
    "Check the memo on the site",
}


def _skill_files() -> dict[str, dict]:
    """Every skill file's frontmatter, keyed by file stem, read straight from disk."""
    out = {}
    for path in sorted(SKILLS_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        assert text.startswith("---\n"), f"{path.name}: no frontmatter"
        front = yaml.safe_load(text.split("---\n", 2)[1])
        out[path.stem] = front
    return out


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]


# ------------------------------------------------------------------ CONN-SKL-01


@pytest.mark.spec("CONN-SKL-01")
def test_instructions_lead_with_editing_and_name_list_skills_and_whoami(mcp):
    served = mcp.initialize()["instructions"]
    assert served == INSTRUCTIONS

    first = _sentences(served)[0]
    assert first.startswith("MemoPop holds this firm's finished investment memos"), first
    second = _sentences(served)[1]
    assert re.search(r"\bchange\b", second) and "citation" in second, second
    # Editing comes before the step-by-step method for new memos.
    assert served.index("finished") < served.index("next_step")

    sentence = next((s for s in _sentences(served) if "list_skills" in s), None)
    assert sentence is not None, "instructions don't name list_skills"

    sentence = next((s for s in _sentences(served) if "whoami" in s), None)
    assert sentence is not None, "instructions don't mention whoami"
    assert re.search(r"more than one firm", sentence), sentence


# ------------------------------------------------------------------ CONN-SKL-02


@pytest.mark.spec("CONN-SKL-02")
def test_list_skills_lists_every_skill_file_with_name_and_description(ws, client, mcp):
    files = _skill_files()
    assert FIRST_SET <= set(files), f"missing skills: {FIRST_SET - set(files)}"
    for stem, front in files.items():
        assert front.get("name") == stem, f"{stem}: frontmatter name differs from file name"
        description = (front.get("description") or "").strip()
        assert description, f"{stem}: no description"
        assert "\n" not in description, f"{stem}: description is more than one line"

    expected = [{"name": n, "description": f["description"].strip()} for n, f in files.items()]

    body = call(ws, "list_skills")
    assert body["ok"] is True
    assert sorted(body["skills"], key=lambda s: s["name"]) == expected

    rest = client.get("/v1/skills", headers=key_headers())
    assert rest.status_code == 200
    assert rest.json() == body

    result = mcp.call("list_skills")
    assert result.get("isError") is not True
    assert result["structuredContent"] == body


# ------------------------------------------------------------------ CONN-SKL-03


@pytest.mark.spec("CONN-SKL-03")
def test_get_skill_returns_the_playbook_and_unknown_is_not_found(ws, client, mcp):
    files = _skill_files()
    for name in files:
        body = call(ws, "get_skill", name=name)
        assert body["ok"] is True
        assert body["name"] == name
        assert body["description"] == files[name]["description"].strip()
        source = (SKILLS_DIR / f"{name}.md").read_text(encoding="utf-8")
        playbook = source.split("---\n", 2)[2].strip()
        assert playbook, f"{name}: empty playbook"
        assert body["text"].strip() == playbook
        # Each playbook ends by saying which tool to call.
        last = body["text"].strip().splitlines()[-1]
        assert re.search(r"`[a-z_]+`", last), f"{name}: last line names no tool: {last!r}"

    rest = client.get("/v1/skills/edit-wording", headers=key_headers())
    assert rest.status_code == 200
    assert rest.json() == call(ws, "get_skill", name="edit-wording")

    from src.connector.errors import ConnectorError

    with pytest.raises(ConnectorError) as raised:
        call(ws, "get_skill", name="write-a-poem")
    err = raised.value
    assert err.code == "skill_not_found"
    assert err.kind == "invalid"
    assert sorted(err.details["available"]) == sorted(files)

    rest = client.get("/v1/skills/write-a-poem", headers=key_headers())
    assert rest.status_code == 404
    assert rest.json()["error"]["code"] == "skill_not_found"
    assert sorted(rest.json()["error"]["details"]["available"]) == sorted(files)

    result = mcp.call("get_skill", {"name": "write-a-poem"})
    assert result["isError"] is True
    assert result["structuredContent"]["error"]["code"] == "skill_not_found"
    text = result["content"][0]["text"]
    for name in files:
        assert name in text, f"the not-found text doesn't list {name}"


# ------------------------------------------------------------------ CONN-SKL-04


@pytest.mark.spec("CONN-SKL-04")
def test_prompts_list_returns_the_four_entry_prompts_naming_memopop_and_a_skill(mcp):
    capabilities = mcp.initialize()["capabilities"]
    assert "prompts" in capabilities

    prompts = mcp.rpc("prompts/list")["prompts"]
    assert {p.get("title") for p in prompts} == PROMPT_TITLES
    skills = set(_skill_files())
    for prompt in prompts:
        assert prompt["description"].strip(), prompt["name"]
        got = mcp.rpc("prompts/get", {"name": prompt["name"], "arguments": {}})
        texts = [m["content"]["text"] for m in got["messages"] if m["role"] == "user"]
        assert texts, prompt["name"]
        text = "\n".join(texts)
        assert "MemoPop" in text, f"{prompt['name']}: doesn't name MemoPop"
        named = re.findall(r"get_skill\b[^`\n]*`([a-z0-9-]+)`", text)
        assert named, f"{prompt['name']}: names no skill to load with get_skill"
        for name in named:
            assert name in skills, f"{prompt['name']}: names unknown skill {name}"

    # What the partner types rides along, and an unknown prompt is an error.
    first = prompts[0]["name"]
    got = mcp.rpc(
        "prompts/get",
        {"name": first, "arguments": {"request": "the Acme memo's market section"}},
    )
    assert "the Acme memo's market section" in got["messages"][0]["content"]["text"]
    response = mcp.post("prompts/get", {"name": "no-such-prompt"})
    assert "error" in response.json()
