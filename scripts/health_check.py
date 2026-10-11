#!/usr/bin/env python3
"""The live health check (spec §The test suite, layer 10; CONN-LIVE-01).

Walks the short MemoPop flow against a running server, over REST, as
``test-firm`` with its static key, and times every call against its documented
worst case:

  1. ``GET /healthz``
  2. ``list_deals`` (the key works)
  3. ``create_new_deal``: a uniquely named deal, ``Health Check <UTC stamp> <rand>``,
     stage ``health-check``, on the firm's one-section ``health-check`` outline
  4. ``add_materials``: one small inline note
  5. ``next_step`` / ``submit_artifact`` until the deal is done: the materials
     brief, one research step (partner-approved), the sources, one draft, and
     each enhancement (canned text that passes the step's checks; an optional
     step whose checks canned text can't meet, such as the diagram's YAML, is
     skipped with a reason, which exercises the skip path)
  6. ``compile``, then fetch the signed HTML and PDF links it returns (a job
     past the compile budget is followed through ``list_deals``)

There is no archive tool in v1 (no tool deletes anything), so the deal is
*marked* rather than archived: its name starts ``Health Check`` and its stage
is ``health-check``. See docs/operator/deploy.md for pruning them.

Exit status: 0 when every step answered correctly within budget; 1 when a step
failed or was slow (the last line, ``FAIL <step>: <reason>``, names it); 2 for
a usage error such as a missing key. Needs only Python 3.11+ and httpx:

    MEMOPOP_HEALTH_KEY=... uv run --no-project --with httpx python scripts/health_check.py \\
        --base-url https://memopop.didi.sh

Budgets are the ``duration`` each tool documents (src/connector/tools/*.py),
plus ``--allowance`` seconds (default 2) for the network between the checker
and the server. ``--budget name=seconds`` overrides one (tests use it).
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx

DEFAULT_URL = "https://memopop.didi.sh"
KEY_ENV = "MEMOPOP_HEALTH_KEY"

#: Documented worst case per call, in seconds (each tool's ``duration`` field).
BUDGETS: dict[str, float] = {
    "healthz": 1.0,  # a stat of the workspace root
    "list_deals": 5.0,  # "under a second; a firm with hundreds of deals, a few seconds"
    "create_new_deal": 1.0,  # "under a second"
    "add_materials": 5.0,  # "returns within 5 seconds"
    "next_step": 1.0,  # "under a second"
    "submit_artifact": 1.0,  # "under a second"
    "compile": 240.0,  # "past about 200 seconds it returns a job instead" (spec: 240)
    "compile_job": 600.0,  # a compile that went to a job, until list_deals says done
    "compiled": 10.0,  # downloading one signed export
}
MAX_STEPS = 40

_FILLER = (
    "This paragraph was written by the MemoPop health check. It describes no company, "
    "cites no real report, and carries no client data. It exists so that every step of "
    "the memo flow can be exercised end to end on the live server, and timed."
)


class CheckFailed(Exception):
    def __init__(self, step: str, reason: str):
        super().__init__(f"{step}: {reason}")
        self.step = step
        self.reason = reason


@dataclass
class Result:
    step: str
    seconds: float
    budget: float
    ok: bool
    note: str = ""


@dataclass
class Checker:
    base_url: str
    key: str
    template: str
    allowance: float
    budgets: dict[str, float]
    results: list[Result] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.http = httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.key}", "User-Agent": "memopop-health"},
            follow_redirects=False,
        )

    # ------------------------------------------------------------ one timed call

    def call(
        self,
        step: str,
        budget_key: str,
        method: str,
        path: str,
        *,
        json_body: dict | None = None,
        params: dict | None = None,
        expect: tuple[int, ...] = (200,),
        auth: bool = True,
        absolute: bool = False,
    ) -> httpx.Response:
        budget = self.budgets[budget_key]
        limit = budget + self.allowance
        headers = None if auth else {"Authorization": ""}
        started = time.monotonic()
        try:
            if absolute:
                with httpx.Client(follow_redirects=True) as plain:
                    response = plain.request(method, path, timeout=limit + 5)
            else:
                response = self.http.request(
                    method,
                    path,
                    json=json_body,
                    params=params,
                    headers=headers,
                    timeout=limit + 5,
                )
        except httpx.TimeoutException:
            took = time.monotonic() - started
            self._record(step, took, limit, False, "timed out")
            raise CheckFailed(step, f"slow: no answer within {took:.1f}s (budget {limit:.1f}s)")
        except httpx.HTTPError as exc:
            took = time.monotonic() - started
            self._record(step, took, limit, False, "unreachable")
            raise CheckFailed(step, f"unreachable: {exc.__class__.__name__}: {exc}") from None
        took = time.monotonic() - started
        if response.status_code not in expect:
            self._record(step, took, limit, False, f"HTTP {response.status_code}")
            raise CheckFailed(step, f"HTTP {response.status_code}: {_error_text(response)}")
        if took > limit:
            self._record(step, took, limit, False, "slow")
            raise CheckFailed(step, f"slow: {took:.2f}s against a budget of {limit:.2f}s")
        self._record(step, took, limit, True)
        return response

    def _record(self, step: str, took: float, limit: float, ok: bool, note: str = "") -> None:
        result = Result(step, took, limit, ok, note)
        self.results.append(result)
        mark = "ok  " if ok else "FAIL"
        extra = f"  {note}" if note else ""
        print(f"  {mark}  {step:<40} {took:7.3f}s / {limit:6.1f}s{extra}", flush=True)

    # ------------------------------------------------------------ the walk

    def run(self) -> None:
        health = self.call("healthz", "healthz", "GET", "/healthz", auth=False)
        if health.json().get("ok") is not True:
            raise CheckFailed("healthz", f"not ok: {health.text[:200]}")

        self.call("list_deals", "list_deals", "GET", "/v1/deals", params={"limit": 1})

        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        company = f"Health Check {stamp} {secrets.token_hex(3)}"
        body = self.call(
            "create_new_deal",
            "create_new_deal",
            "POST",
            "/v1/deals",
            json_body={"company": company, "stage": "health-check", "template": self.template},
            expect=(201,),
        ).json()
        deal = body["deal"]
        if not body.get("created"):
            raise CheckFailed("create_new_deal", f"'{deal}' already existed; names must be unique")
        print(f"  deal: {deal}", flush=True)

        accepted = self.call(
            "add_materials",
            "add_materials",
            "POST",
            f"/v1/deals/{deal}/materials",
            json_body={
                "items": [{"kind": "notes", "text": "Health check note: " + _FILLER}],
            },
        ).json()["accepted"]
        if [a.get("status") for a in accepted] != ["ready"]:
            raise CheckFailed("add_materials", f"inline text was not ready: {accepted}")

        submitted = self.walk(deal)
        for needed in ("research.section", "draft.section"):
            if needed not in submitted:
                raise CheckFailed("next_step", f"the walk finished without handing out {needed}")

        self.compile(deal)

    def walk(self, deal: str) -> list[str]:
        submitted: list[str] = []
        for _ in range(MAX_STEPS):
            step = self.call(
                "next_step", "next_step", "POST", f"/v1/deals/{deal}/next-step", json_body={}
            ).json()
            if step.get("done"):
                if not step.get("compile_ready"):
                    raise CheckFailed("next_step", f"done but not compile_ready: {step}")
                return submitted
            step_id = step["step_id"]
            label = step_id + (f" [{step['section']}]" if step.get("section") else "")
            checks = (step.get("produces") or {}).get("checks") or {}
            core = step_id in ("research.section", "draft.section")
            body = {"step_id": step_id, "section": step.get("section")}
            if not core and not can_write(checks):
                body.update(skip=True, reason="The health check does not write this artifact.")
            else:
                body.update(content=canned(step_id, checks))
                if step.get("needs_partner"):
                    body["partner_approved"] = True
            response = self.call(
                f"submit_artifact {label}",
                "submit_artifact",
                "POST",
                f"/v1/deals/{deal}/artifacts",
                json_body=body,
                expect=(200, 201),
            )
            if response.json().get("ok") is False:
                raise CheckFailed(f"submit_artifact {label}", _error_text(response))
            submitted.append(step_id)
        raise CheckFailed("next_step", f"still not done after {MAX_STEPS} steps")

    def compile(self, deal: str) -> None:
        response = self.call(
            "compile",
            "compile",
            "POST",
            f"/v1/deals/{deal}/compile",
            json_body={},
        )
        body = response.json()
        if body.get("job_id") and body.get("status") == "running":
            body = self.follow_job(deal, body["job_id"])
        for fmt, marker in (("html", b"<"), ("pdf", b"%PDF")):
            url = body.get(f"{fmt}_url")
            if not url:
                raise CheckFailed("compile", f"no {fmt}_url in {json.dumps(body)[:300]}")
            got = self.call(f"compiled {fmt}", "compiled", "GET", url, absolute=True, auth=False)
            if marker not in got.content[:2048]:
                raise CheckFailed(f"compiled {fmt}", f"the download is not {fmt.upper()}")

    def follow_job(self, deal: str, job_id: str) -> dict:
        deadline = time.monotonic() + self.budgets["compile_job"]
        while time.monotonic() < deadline:
            time.sleep(5)
            deals = self.call(
                "list_deals (compile job)", "list_deals", "GET", "/v1/deals", params={"limit": 100}
            ).json()["deals"]
            row = next((d for d in deals if d["deal"] == deal), None)
            job = (row or {}).get("compile") or {}
            if job.get("job_id") == job_id and job.get("status") == "done":
                return job
            if job.get("job_id") == job_id and job.get("status") not in (None, "running"):
                raise CheckFailed("compile", f"job {job_id} ended {job.get('status')}: {job}")
        raise CheckFailed(
            "compile", f"slow: job {job_id} not done in {self.budgets['compile_job']}s"
        )


# ------------------------------------------------------------------ canned artifacts

_WRITABLE = {
    "not_empty",
    "min_words",
    "max_chars",
    "has_citations",
    "citations_resolve",
    "required_headings",
}


def can_write(checks: dict) -> bool:
    return set(checks) <= _WRITABLE


def canned(step_id: str, checks: dict) -> str:
    """Synthetic text that meets the checks next_step announced for the step."""
    headings = [str(h) for h in checks.get("required_headings") or []]
    title = f"## Health check: {step_id}"
    citations = max(2, int(checks.get("has_citations") or 0) or 0)
    words_needed = int(checks.get("min_words") or 0)
    paragraphs = []
    n = 0
    while True:
        n += 1
        paragraphs.append(f"{_FILLER} [^{(n - 1) % citations + 1}]")
        if n >= citations and len(" ".join(paragraphs).split()) >= words_needed + 10:
            break
    defs = "\n\n".join(
        f"[^{i}]: 2026, Jan 01. [Health check source {i}](https://example.org/health/{i}). "
        "MemoPop. Published: 2026-01-01 | Updated: N/A"
        for i in range(1, citations + 1)
    )
    parts = [*headings, title, *paragraphs, "### Citations", defs]
    return "\n\n".join(parts) + "\n"


# ------------------------------------------------------------------ plumbing


def _error_text(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:300].strip() or "(empty body)"
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict):
        text = f"{error.get('code')}: {error.get('message')}"
        failures = (error.get("details") or {}).get("checks") or []
        failed = [c.get("detail") for c in failures if not c.get("passed")]
        return text + (f" ({'; '.join(map(str, failed))})" if failed else "")
    return json.dumps(body)[:300]


def _budget_overrides(values: list[str]) -> dict[str, float]:
    out: dict[str, float] = {}
    for value in values:
        name, sep, seconds = value.partition("=")
        if not sep or name not in BUDGETS:
            raise SystemExit(f"--budget wants name=seconds with name one of {sorted(BUDGETS)}")
        out[name] = float(seconds)
    return out


def _summary(checker: Checker, failure: CheckFailed | None) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    lines = [
        f"### MemoPop health check: {'FAIL' if failure else 'PASS'} ({checker.base_url})",
        "",
        "| Step | Seconds | Budget | Result |",
        "|---|---:|---:|---|",
    ]
    for r in checker.results:
        lines.append(
            f"| {r.step} | {r.seconds:.3f} | {r.budget:.1f} | {'ok' if r.ok else r.note} |"
        )
    if failure:
        lines += ["", f"**FAIL {failure.step}**: {failure.reason}"]
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--base-url", default=os.environ.get("MEMOPOP_HEALTH_URL", DEFAULT_URL))
    parser.add_argument("--key", default=None, help=f"the firm's static key (or ${KEY_ENV})")
    parser.add_argument("--template", default="health-check")
    parser.add_argument("--allowance", type=float, default=2.0, help="network seconds per call")
    parser.add_argument("--budget", action="append", default=[], metavar="NAME=SECONDS")
    parser.add_argument("--json", dest="json_out", default=None, help="write results here")
    args = parser.parse_args(argv)

    key = args.key or os.environ.get(KEY_ENV, "")
    if not key:
        print(f"usage: set {KEY_ENV} (or pass --key) to test-firm's static key", file=sys.stderr)
        return 2
    budgets = {**BUDGETS, **_budget_overrides(args.budget)}
    base = args.base_url.rstrip("/")
    print(f"MemoPop health check against {base}", flush=True)
    checker = Checker(base, key, args.template, args.allowance, budgets)
    failure: CheckFailed | None = None
    try:
        checker.run()
    except CheckFailed as exc:
        failure = exc
    except Exception as exc:  # an answer the check didn't expect is a failure too
        step = checker.results[-1].step if checker.results else "start"
        failure = CheckFailed(step, f"unexpected answer: {exc.__class__.__name__}: {exc}")
    _summary(checker, failure)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "base_url": base,
                    "ok": failure is None,
                    "failed_step": failure.step if failure else None,
                    "reason": failure.reason if failure else None,
                    "calls": [r.__dict__ for r in checker.results],
                },
                fh,
                indent=2,
            )
    total = sum(r.seconds for r in checker.results)
    if failure:
        print(f"FAIL {failure.step}: {failure.reason}", flush=True)
        return 1
    print(f"PASS {len(checker.results)} calls in {total:.1f}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
