"""
Guard on prompt constants that get `.format()`ed.

`PROSE_DETECTION_PROMPT` in table_generator.py embeds a JSON example. Its single
braces are replacement fields to `str.format`, so every call raised
`KeyError('\\n    "tables"')`, was swallowed by a bare `except Exception`, and
logged a warning indistinguishable from "no tabular data found". Prose-table
detection had therefore never once produced a table, and nothing said so.

The bug is invisible by inspection — the prompt reads fine, the call reads fine,
and only their combination fails. So it is tested rather than reviewed: this
walks every module-level string constant that is `.format()`ed anywhere in
`src/`, renders it with the keywords its own call site passes, and fails if it
raises. Adding a JSON example to any prompt will now fail here instead of
silently disabling the agent that uses it.
"""

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"


def _module_level_strings(tree: ast.Module) -> dict[str, str]:
    """`NAME = "..."` at module level, which is where prompts live."""
    out: dict[str, str] = {}
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            out[node.targets[0].id] = node.value.value
    return out


def _format_call_sites(tree: ast.Module, names: dict[str, str]):
    """Every `SOME_CONSTANT.format(...)`, with the kwargs it is given."""
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "format"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in names
        ):
            kwargs = {kw.arg: "PLACEHOLDER" for kw in node.keywords if kw.arg}
            positional = len(node.args)
            yield node.func.value.id, node.lineno, kwargs, positional


def _python_files():
    return sorted(f for f in SRC.rglob("*.py") if "__pycache__" not in f.parts)


def _collect():
    cases = []
    for path in _python_files():
        try:
            tree = ast.parse(path.read_text(errors="replace"))
        except SyntaxError:
            continue
        names = _module_level_strings(tree)
        if not names:
            continue
        for name, lineno, kwargs, positional in _format_call_sites(tree, names):
            cases.append(
                pytest.param(
                    str(path.relative_to(REPO)), name, lineno, names[name],
                    kwargs, positional,
                    id=f"{path.relative_to(SRC)}::{name}:{lineno}",
                )
            )
    return cases


CASES = _collect()


@pytest.mark.skipif(not CASES, reason="no module-level prompt constants are .format()ed")
@pytest.mark.parametrize("path,name,lineno,template,kwargs,positional", CASES)
def test_formatted_prompt_renders(path, name, lineno, template, kwargs, positional):
    """A prompt must survive the .format() its own call site performs."""
    args = ["PLACEHOLDER"] * positional
    try:
        rendered = template.format(*args, **kwargs)
    except (KeyError, IndexError) as e:
        pytest.fail(
            f"{path}:{lineno} — {name}.format() raises {type(e).__name__}({e}).\n"
            f"A literal brace in the template is being read as a replacement "
            f"field; this is almost always a JSON example in a prompt. Either "
            f"double the literal braces, or switch the call site to "
            f'.replace("{{{next(iter(kwargs), "x")}}}", value), which cannot be '
            f"broken by editing the example."
        )
    except ValueError as e:
        pytest.fail(f"{path}:{lineno} — {name}.format() raises ValueError({e}).")

    assert rendered, f"{path}:{lineno} — {name} rendered empty"


def test_the_known_offender_stays_fixed():
    """table_generator's prose detector is the reason this file exists."""
    src = (SRC / "agents" / "table_generator.py").read_text()
    assert "PROSE_DETECTION_PROMPT.format(" not in src, (
        "PROSE_DETECTION_PROMPT contains a JSON example; .format() raises on it. "
        'Use .replace("{content}", content).'
    )
    from src.agents.table_generator import PROSE_DETECTION_PROMPT

    assert "{content}" in PROSE_DETECTION_PROMPT, "the placeholder went missing"
    rendered = PROSE_DETECTION_PROMPT.replace("{content}", "SECTION TEXT")
    assert "SECTION TEXT" in rendered
    assert "{content}" not in rendered
    assert '"tables"' in rendered, "the JSON example must survive substitution"
