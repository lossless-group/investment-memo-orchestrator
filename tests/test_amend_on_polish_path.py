"""
`amend` has to survive the path it actually runs on.

There are two writer paths. `write_single_section` runs only when a section has
no research file; `polish_section_research` runs otherwise, which is almost
always. The amend directive was implemented and tested against the first and
quietly failed on the second, for two reasons that are invisible unless you read
the assembled prompt:

1. The prompt opened "Rewrite the following research into a polished section"
   and put the amend guidance underneath it. Given a contradiction between the
   task framing and a later instruction, the framing wins. ProfileHealth §7 was
   marked amend, was handed its prior prose, and came back at 173 words against
   the 959 it started from — rebuilt from research, not amended.

2. The citation gate measured `research_content` alone. On an amend the
   section's own citations are the ones most worth protecting, since they are
   attached to prose a human may have written, and they were outside the set the
   validator compared against.

These tests read the prompt the function builds rather than mocking a good
answer out of a model, because both defects were in the prompt.
"""

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

import src.agents.writer as writer

RESEARCH = """# Risks — Research

The carrier proposal is under executive review [^prudential].

### Citations

[^prudential]: Profile Health x Prudential LTC proposal.
"""

PRIOR = """## 7. Risks & What Could Go Wrong

Concentration risk sits with a single champion [^sieb]. The cap table shows
28.34% unaccounted [^captable].
"""


@pytest.fixture(scope="module")
def section_def():
    """The real §7 definition from the 12Ps outline.

    A hand-rolled stub drifts from whatever the writer reads next; the outline is
    the contract, so the test uses it.
    """
    from src.outline_loader import load_yaml_file, parse_section

    raw = load_yaml_file(
        Path("io/humain/templates/outlines/direct-early-stage-12Ps.yaml")
    )
    return next(
        parse_section(d) for d in raw["sections"] if d["filename"] == "07-risks.md"
    )


@pytest.fixture
def captured(monkeypatch):
    """Run the polish path with a stubbed model and keep the prompt it built."""
    seen = {}

    def fake_complete_with_retry(prompt, **kwargs):
        seen["prompt"] = prompt
        from src.llm_provider import LLMResponse
        # Echo something citation-complete so the gate passes and we reach the end.
        keys = set(re.findall(r"\[\^([a-zA-Z0-9_]+)\]", prompt))
        body = "## 7. Risks\n\n" + " ".join(f"Claim [^{k}]." for k in sorted(keys))
        body += "\n\n### Citations\n\n" + "\n".join(f"[^{k}]: source." for k in sorted(keys))
        return LLMResponse(text=body, provider="cli")

    monkeypatch.setattr(writer, "complete_with_retry", fake_complete_with_retry)
    monkeypatch.setattr(writer, "load_style_guide", lambda *a, **k: "", raising=False)
    return seen


def _amend_frame(prior_exists=True):
    directive = SimpleNamespace(prose="amend", research="extend", writes=True, researches=True)
    return SimpleNamespace(
        slug="f", name="LTC carrier B2B2C", stance="re-sequencing", premise="carrier first", caveats=[],
        questions={}, evidence=[],
        directive_for=lambda _n: directive,
        note_for=lambda _n: "",
        questions_for=lambda _n: [],
    )


def _run(tmp_path, frame, captured, section_def, prior=PRIOR):
    out = tmp_path / "v1"
    (out / "2-sections").mkdir(parents=True)
    if prior is not None:
        (out / "2-sections" / "07-risks.md").write_text(prior)
    return writer.polish_section_research(
        section_def=section_def,
        research_content=RESEARCH,
        company_name="ProfileHealth",
        memo_mode="consider",
        style_guide="",
        frame=frame,
        output_dir=out,
    )


# --- the task framing ----------------------------------------------------


def test_an_amend_is_asked_for_as_an_amendment(tmp_path, captured, section_def):
    _run(tmp_path, _amend_frame(), captured, section_def)
    prompt = captured["prompt"]
    assert prompt.lstrip().startswith("Amend the existing"), (
        "the opening line is the task; if it says 'rewrite the research' the "
        "model rebuilds instead of amending"
    )
    assert "AMENDMENT, not a regeneration" in prompt
    assert "NEW RESEARCH TO FOLD IN" in prompt, (
        "research presented as the source invites a regeneration"
    )


def test_an_amend_is_never_told_to_shrink(tmp_path, captured, section_def):
    _run(tmp_path, _amend_frame(), captured, section_def)
    assert "at least" in captured["prompt"]
    assert "an amendment adds to what is there" in captured["prompt"]


def test_a_non_amend_keeps_the_original_framing(tmp_path, captured, section_def):
    directive = SimpleNamespace(prose="rewrite", research="extend", writes=True, researches=True)
    frame = SimpleNamespace(slug="f", name="F", stance="s", premise="p", caveats=[],
                            questions={}, evidence=[],
                            directive_for=lambda _n: directive, note_for=lambda _n: "",
                            questions_for=lambda _n: [])
    _run(tmp_path, frame, captured, section_def)
    prompt = captured["prompt"]
    assert prompt.lstrip().startswith("Rewrite the following"), (
        "a rewrite must not see the old prose or it anchors on it"
    )
    assert "PERPLEXITY RESEARCH" in prompt


def test_a_frameless_run_is_unchanged(tmp_path, captured, section_def):
    _run(tmp_path, None, captured, section_def, prior=None)
    assert captured["prompt"].lstrip().startswith("Rewrite the following")


# --- the citation gate ---------------------------------------------------


def test_the_sections_own_citations_enter_the_preservation_set(tmp_path, captured, section_def):
    """The load-bearing one. [^sieb] and [^captable] live in the section, not in
    the research; before this they were outside the gate."""
    _run(tmp_path, _amend_frame(), captured, section_def)
    prompt = captured["prompt"]
    assert "PRESERVE ALL 3 CITATIONS" in prompt, (
        "expected the union of research (1) and prior prose (2)"
    )
    for key in ("sieb", "captable", "prudential"):
        assert key in prompt


def test_a_rewrite_does_not_inherit_the_sections_citations(tmp_path, captured, section_def):
    """A rewrite legitimately discards the old draft, so its citations are not
    a preservation obligation — only the research's are."""
    directive = SimpleNamespace(prose="rewrite", research="extend", writes=True, researches=True)
    frame = SimpleNamespace(slug="f", name="F", stance="s", premise="p", caveats=[],
                            questions={}, evidence=[],
                            directive_for=lambda _n: directive, note_for=lambda _n: "",
                            questions_for=lambda _n: [])
    _run(tmp_path, frame, captured, section_def)
    assert "PRESERVE ALL 1 CITATIONS" in captured["prompt"]


def test_amend_with_no_prior_file_falls_back_to_a_regeneration(tmp_path, captured, section_def):
    """"Leave it alone" cannot mean "leave a hole": with nothing to amend, the
    section is written normally rather than not at all."""
    _run(tmp_path, _amend_frame(), captured, section_def, prior=None)
    assert captured["prompt"].lstrip().startswith("Rewrite the following")
