"""
Visual Collectors — Charts and Imagery

Two collectors that run over slides the stenographer has already transcribed,
isolating the parts of a slide that text cannot carry and cropping each one into
its own image.

**The chart collector** takes anything that plots data — line, bar, scatter,
pie, waterfall, a ruled table of figures. A chart cropped away from its axis
labels, its legend, its units, and its source note is worse than no crop at all,
because it looks complete and is unreadable. So crops are padded outward
deliberately and rejected when the model reports that a key sits outside the
region it drew.

**The imagery collector** takes any visual that helps communicate a concept —
including structured conceptual layouts built from boxes and text: roadmaps,
timelines, process flows, frameworks, matrices, layered architectures. Those are
the easiest to miss, because they do not look like pictures. It reports the
largest coherent unit rather than its parts, and skips pure decoration. A gradient, a
stock photo of a laboratory, an icon beside a bullet, a background texture: none
of these would tell a reader anything the text has not already said, and
collecting them buries the ones that would.

Both read the *rendered slide images the stenographer already produced*. Nothing
re-renders the source PDF, so a collection pass costs one model call per slide
and no page rasterization.

**On bounding boxes.** A vision model estimates regions; it does not measure
them. Coordinates come back normalized and approximate, and a crop drawn tightly
to them will clip an axis label as often as not. Every crop is therefore padded,
clamped, and sanity-checked, and the padding is larger for charts than for
imagery because charts carry more marginal furniture that must survive.
"""

from __future__ import annotations

import base64
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import yaml

from ...llm_provider import complete
AGENT_SIGNATURE = "Claude Code on Opus 5 with Claude Vision"

# Fractions of the region's own size, added to every edge before cropping.
# Charts get more: axis titles, tick labels, legends, and source notes all sit
# outside the plot area a model tends to draw its box around.
CHART_PADDING = 0.06
IMAGERY_PADDING = 0.02

# A crop covering almost none of the slide is a mis-drawn box.
MIN_REGION_AREA = 0.015

# A crop covering nearly the whole slide means one of two opposite things, and
# they cannot be told apart from the box alone: either the detector gave up and
# boxed everything, or the slide genuinely IS one full-bleed diagram. Three
# slides in the first deck were the second case and were rejected as the first.
#
# The count of regions on the slide separates them. One region covering the whole
# slide is a full-bleed visual. One of several covering the whole slide is the
# lazy box the guard was written for.
MAX_REGION_AREA_WHEN_ALONE = 1.0
MAX_REGION_AREA_WHEN_SHARED = 0.92

# Below this many pixels on either edge, a crop is too small to read.
MIN_CROP_PX = 120

# The enum the detector is given. A returned kind outside it means the detector
# reached past the categories it was offered, which in practice has meant
# decoration — "icon" was invented three times for pictograms labelling roadmap
# tracks, all of which the size guard then rejected anyway.
CHART_KINDS = {
    "line", "bar", "column", "stacked_bar", "area", "scatter", "bubble",
    "pie", "donut", "waterfall", "funnel", "heatmap", "table", "mixed",
}
IMAGERY_KINDS = {
    "diagram", "illustration", "screenshot", "photo", "map", "comparison_figure",
    # A statistic set as a visual, and standalone concept icons. Both were
    # excluded at first — icons because they were fragmenting larger diagrams,
    # which turned out to be a granularity problem rather than a category one.
    "fact_callout", "icon", "pictograph",
    # Structured conceptual layouts. These were the largest miss in the first
    # pass: 22 of 38 slides collected nothing, including every roadmap and every
    # strategy-framework slide, because the detector read a diagram built from
    # boxes and text as "just formatted text" rather than as a visual.
    "roadmap", "timeline", "process_flow", "framework", "matrix", "architecture",
}


# =============================================================================
# Result types
# =============================================================================

@dataclass
class VisualRegion:
    """One cropped region of a slide, with everything needed to read it alone."""

    slide_index: int
    ordinal: int
    collector: str                    # chart | imagery
    kind: str
    box: Tuple[float, float, float, float]   # normalized, as reported
    alt: str
    detail: Dict[str, Any] = field(default_factory=dict)
    local_path: Optional[str] = None
    cdn_url: Optional[str] = None
    notes: List[str] = field(default_factory=list)

    @property
    def region_id(self) -> str:
        return f"{self.slide_index:02d}-{self.collector}-{self.ordinal:02d}"

    @property
    def status(self) -> str:
        """``collected`` once an image exists on disk, else ``rejected``."""
        return "collected" if self.local_path else "rejected"

    def as_frontmatter(self) -> Dict[str, Any]:
        record = {
            "id": self.region_id,
            # A region with no image is still worth recording — it says something
            # was here that could not be isolated — but it must not read like a
            # usable asset. Without this a reader sees an entry with alt text and
            # a crop box and assumes a file exists.
            "status": self.status,
            "kind": self.kind,
            "alt": self.alt,
            "crop": [round(v, 4) for v in self.box],
            **self.detail,
        }
        if self.local_path:
            record["local"] = self.local_path
        if self.cdn_url:
            record["cdn"] = self.cdn_url
        if self.notes:
            record["notes"] = self.notes
        return record


# =============================================================================
# Detection
# =============================================================================

_DETECTION_PROMPT = """You are cataloguing the visual elements on slide {index} of a
pitch deck, so each can be cropped out and read on its own.

Report every element in one of two categories, and nothing else.

CHARTS — anything that presents data, conventional or not. Line, bar, column,
stacked, area, scatter, bubble, pie, donut, waterfall, funnel, gauge, treemap,
heatmap. Also: any ruled TABLE of values, and any custom or unusual plot a
designer invented for this deck — a hand-drawn curve, an annotated gradient, two
shapes whose relative size encodes a quantity. If the visual's job is to convey
a magnitude, a trend, or a comparison of values, it is a chart even if it
matches no standard chart type. Use kind "table" for tables and "mixed" for
custom forms. For each, the crop box MUST enclose the plot area *together with*
everything needed to read it: chart title, both axis titles, tick labels, the
legend or key, units, and any source or footnote line. If any of those sits
outside your box, widen the box. State in `key_outside_box` whether any element
of the key or axes could not be enclosed.

DECIDING BETWEEN THE TWO — apply this test before anything else. If the visual
contains numbers, or encodes a magnitude, quantity, ranking, or comparison of
values in any way, it is a CHART, not imagery. A ruled table of specifications,
a matrix of checkmarks against criteria, a bespoke plot with no axes: all
charts. Only if the visual conveys structure, sequence, or a concept *without*
quantifying anything is it imagery.

IMAGERY — any visual that helps communicate a concept. Report it whether it is
drawn, photographed, or composed from shapes and text.

This explicitly INCLUDES structured conceptual layouts, which are the most
commonly missed category. A roadmap, a timeline, a phased plan, a process flow,
a framework of named pillars, a two-by-two matrix, a layered architecture, a
funnel, a stack, a set of labelled quadrants, a before-and-after comparison —
all of these are imagery even when built entirely from boxes, arrows, and text
rather than from a picture. If a reader would understand the idea faster by
looking at the arrangement than by reading the words in it, it is imagery.

Also include architecture and flow diagrams, mechanism illustrations, annotated
product screenshots, maps, and photographs presented as evidence.

GRANULARITY — this is the rule most often got wrong. Report the LARGEST coherent
visual unit, never its parts.

**Ask first: is this slide essentially ONE visual?** Many slides are a single
large diagram with a title above it. If so, report exactly ONE region, and let
its box cover the whole visual — up to the entire slide if the diagram bleeds to
the edges. A full-slide box is the correct answer for a full-slide diagram; do
not shrink it to look more precise, and do not split one diagram into the two or
three clusters you can see inside it.

Only if the slide holds genuinely separate visuals — a chart on the left and an
unrelated photograph on the right — report more than one region.

**Extend every box to the visual's true edges.** A box that stops at the dense
middle of a diagram and omits its outer nodes, its surrounding labels, or the
band of text along its base has cut the visual in half. When in doubt, extend
outward to the slide's margins. An over-wide crop is recoverable; a crop missing
a third of the diagram is not.

A roadmap with three tracks, each carrying an icon and a label, is ONE region
enclosing all three tracks, all three icons, the phase headers, and the time
axis. A framework of four pillars is ONE region, not four. Report a sub-element
separately only if it would still make sense cropped away from everything around
it.

ALSO REPORT these, which are easy to overlook:

- **Fact callouts** — a statistic, percentage, or figure set large and styled as
  a visual element rather than as body text, often with a caption beneath it.
  Use kind "fact_callout".
- **Standalone icons, pictographs, and spot illustrations** that stand for a
  concept — a brain, a chip, a vehicle — when they are the slide's way of
  showing an idea rather than ornament beside a bullet. Use kind "icon" or
  "pictograph". These are worth collecting; keep the box generous enough to
  include the label the icon belongs to.

But remember GRANULARITY: an icon that is part of a roadmap, framework, or
diagram belongs inside that visual's box, not in an entry of its own. Report an
icon separately only when it is not part of a larger visual.

DO NOT REPORT pure decoration: background gradients and textures, stock photos
that merely set a mood, logo walls used as ornament, dividers, rules, page
furniture, and headshots on a team slide.

Use exactly one of the listed `kind` values.

Coordinates are normalized to the slide: x0,y0 is the top-left corner as a
fraction of width and height, x1,y1 the bottom-right. Be generous rather than
tight — a clipped axis label makes a chart useless.

Return ONLY this JSON:
{{
  "charts": [
    {{
      "kind": "line|bar|column|stacked_bar|area|scatter|bubble|pie|donut|waterfall|funnel|heatmap|table|mixed",
      "box": [x0, y0, x1, y1],
      "title": "<chart title verbatim, or null>",
      "x_axis": "<x axis title verbatim, or null>",
      "y_axis": "<y axis title verbatim, or null>",
      "units": "<units as printed, or null>",
      "legend": ["<each legend entry verbatim>"],
      "series": ["<each plotted series name verbatim>"],
      "source_note": "<any source/footnote printed with the chart, verbatim, or null>",
      "key_outside_box": <true|false>,
      "reads": "<one sentence: what the chart shows and its direction>",
      "alt": "<one sentence describing it for someone who cannot see it, naming the axes and the headline figure>"
    }}
  ],
  "imagery": [
    {{
      "kind": "diagram|roadmap|timeline|process_flow|framework|matrix|architecture|illustration|screenshot|photo|map|comparison_figure|fact_callout|icon|pictograph",
      "box": [x0, y0, x1, y1],
      "depicts": "<what it shows>",
      "role": "explains_mechanism|shows_product|provides_evidence|establishes_scale|shows_architecture|shows_sequence|organizes_concepts|other",
      "labels": ["<any text labels inside the visual, verbatim>"],
      "alt": "<one sentence describing it for someone who cannot see it>"
    }}
  ],
  "decoration_skipped": <integer count of decorative visuals deliberately not reported>
}}

Return empty arrays if the slide has no charts or no meaningful imagery. Most
slides have neither; that is a normal and correct answer."""


def detect_visuals(image_path: Path, slide_index: int, attempts: int = 2) -> Dict[str, Any]:
    """
    One model call: catalogue every chart and meaningful visual on one slide.

    Both collectors read this single result. Asking twice would cost twice and
    invite two passes to draw different boxes around the same region.

    Malformed responses are repaired before they are retried. The payload is full
    of verbatim strings copied off a slide, and a slide containing quoted text
    invalidates the object it is transcribed into — see ``repair_json``. Retrying
    that is pointless at temperature zero; the retry exists for transport errors
    and truncation.
    """
    last: Dict[str, Any] = {"charts": [], "imagery": [], "error": "not attempted"}
    for attempt in range(1, attempts + 1):
        last = _detect_once(image_path, slide_index)
        if not last.get("error"):
            return last
        if attempt < attempts:
            print(f"(retrying after {last['error'][:44]}) ", end="", flush=True)
    return last


def repair_json(text: str) -> str:
    """
    Escape stray double quotes that appear *inside* JSON string values.

    Verbatim transcription and JSON are in direct tension. A slide reading

        Game-Changing, Disruptive, Jaw-Dropping ("Tell your friends" test)

    is copied faithfully into a string value, and its inner quotes terminate that
    value early and invalidate the whole object. The model is doing exactly what
    it was told; the format cannot carry the result. Retrying does not help — at
    temperature zero it fails identically — so the payload is repaired instead.

    The rule: inside a string, a double quote really ends it only when the next
    non-whitespace character is a structural one. Anything else is a quote the
    slide contained, and gets escaped.
    """
    out: List[str] = []
    in_string = False
    escaped = False

    for i, char in enumerate(text):
        if escaped:
            out.append(char)
            escaped = False
            continue
        if char == "\\":
            out.append(char)
            escaped = True
            continue

        if char == '"':
            if not in_string:
                in_string = True
                out.append(char)
                continue
            nxt = next((c for c in text[i + 1:] if not c.isspace()), "")
            if nxt in {",", ":", "}", "]", ""}:
                in_string = False
                out.append(char)
            else:
                out.append('\\"')   # a quote the slide contained
            continue

        out.append(char)

    return "".join(out)


def _detect_once(image_path: Path, slide_index: int) -> Dict[str, Any]:
    """One detection attempt."""
    completion = complete(
        _DETECTION_PROMPT.format(index=slide_index),
        images=[image_path],
        max_tokens=4000,
        model=os.getenv("DEFAULT_MODEL"),
    )
    if not completion.ok:
        return {"charts": [], "imagery": [], "error": completion.error or "empty response"}

    try:
        raw = completion.text
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return {"charts": [], "imagery": [], "error": "model returned no JSON"}
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            # Almost always a quote the slide itself contained. Repair rather
            # than retry: the response is correct transcription in an unforgiving
            # container, and a retry reproduces it exactly.
            return json.loads(repair_json(match.group()))
    except Exception as e:
        return {"charts": [], "imagery": [], "error": f"{type(e).__name__}: {e}"}


# =============================================================================
# Cropping
# =============================================================================

def _normalize_box(box: Sequence[float]) -> Optional[Tuple[float, float, float, float]]:
    """Coerce a reported box into a sane normalized rectangle, or reject it."""
    try:
        x0, y0, x1, y1 = (float(v) for v in box)
    except (TypeError, ValueError):
        return None

    # Models occasionally emit percentages instead of fractions.
    if max(x0, y0, x1, y1) > 1.5:
        x0, y0, x1, y1 = (v / 100.0 for v in (x0, y0, x1, y1))

    x0, x1 = sorted((max(0.0, x0), min(1.0, x1)))
    y0, y1 = sorted((max(0.0, y0), min(1.0, y1)))

    if (x1 - x0) <= 0 or (y1 - y0) <= 0:
        return None
    return x0, y0, x1, y1


def crop_region(
    image_path: Path,
    box: Sequence[float],
    out_path: Path,
    padding: float,
    regions_on_slide: int = 1,
) -> Tuple[Optional[Path], List[str]]:
    """
    Crop one region out of a slide image, padded outward.

    Returns the written path and any notes worth recording. Padding is a fraction
    of the region's own size rather than of the slide, so a small chart on a
    large slide still gains room for its labels proportionally.
    """
    from PIL import Image

    notes: List[str] = []
    normalized = _normalize_box(box)
    if normalized is None:
        return None, ["reported crop box was not a usable rectangle"]

    x0, y0, x1, y1 = normalized
    area = (x1 - x0) * (y1 - y0)
    notes_extra: List[str] = []
    if area < MIN_REGION_AREA:
        return None, [f"region covers only {area:.1%} of the slide — likely a mis-drawn box"]

    ceiling = (MAX_REGION_AREA_WHEN_ALONE if regions_on_slide <= 1
               else MAX_REGION_AREA_WHEN_SHARED)
    if area > ceiling:
        return None, [
            f"region covers {area:.0%} of the slide alongside "
            f"{regions_on_slide - 1} other(s) — nothing was isolated"
        ]
    if area > 0.9:
        notes_extra.append("full-bleed visual: the crop is essentially the whole slide")

    pad_x = (x1 - x0) * padding
    pad_y = (y1 - y0) * padding
    px0, py0 = max(0.0, x0 - pad_x), max(0.0, y0 - pad_y)
    px1, py1 = min(1.0, x1 + pad_x), min(1.0, y1 + pad_y)

    with Image.open(image_path) as source:
        width, height = source.size
        left, top = int(px0 * width), int(py0 * height)
        right, bottom = int(px1 * width), int(py1 * height)

        if (right - left) < MIN_CROP_PX or (bottom - top) < MIN_CROP_PX:
            return None, [
                f"crop would be {right - left}x{bottom - top}px — too small to read"
            ]

        out_path.parent.mkdir(parents=True, exist_ok=True)
        source.crop((left, top, right, bottom)).save(
            out_path, "JPEG", quality=90, optimize=True
        )

    return out_path, notes + notes_extra


# =============================================================================
# The two collectors
# =============================================================================

def collect_charts(
    detection: Dict[str, Any],
    slide_index: int,
    image_path: Path,
    out_dir: Path,
) -> List[VisualRegion]:
    """
    Chart collector.

    Everything a chart needs to be read alone is captured alongside the crop:
    the axes, the legend, the units, and the source note. A chart image without
    them is a picture of a shape.
    """
    regions: List[VisualRegion] = []
    total_regions = len(detection.get("charts") or []) + len(detection.get("imagery") or [])

    for ordinal, chart in enumerate(detection.get("charts") or [], start=1):
        region = VisualRegion(
            slide_index=slide_index,
            ordinal=ordinal,
            collector="chart",
            kind=chart.get("kind") or "mixed",
            box=tuple(chart.get("box") or (0, 0, 0, 0)),
            alt=chart.get("alt") or "",
            detail={
                k: v for k, v in (
                    ("title", chart.get("title")),
                    ("x_axis", chart.get("x_axis")),
                    ("y_axis", chart.get("y_axis")),
                    ("units", chart.get("units")),
                    ("legend", chart.get("legend") or None),
                    ("series", chart.get("series") or None),
                    ("source_note", chart.get("source_note")),
                    ("reads", chart.get("reads")),
                ) if v
            },
        )

        # The model was asked whether the key fits inside the box it drew. A
        # "no" is the single most useful signal here, because a chart cropped
        # away from its legend looks complete and cannot be read.
        if chart.get("key_outside_box"):
            region.notes.append(
                "model reported part of the key or axes falls outside this box — "
                "crop widened, but verify against the full slide"
            )

        padding = CHART_PADDING * (2 if chart.get("key_outside_box") else 1)
        path, notes = crop_region(
            image_path, region.box, out_dir / f"{region.region_id}.jpg", padding,
            regions_on_slide=total_regions,
        )
        region.notes.extend(notes)
        if path:
            region.local_path = f"./charts/{path.name}"
        if not region.detail.get("legend") and region.kind not in ("table",):
            region.notes.append("no legend captured — single-series chart, or the key was missed")

        regions.append(region)

    return regions


def collect_imagery(
    detection: Dict[str, Any],
    slide_index: int,
    image_path: Path,
    out_dir: Path,
) -> List[VisualRegion]:
    """
    Imagery collector.

    Only visuals that communicate. What is skipped matters as much as what is
    kept, so the count of deliberately-ignored decoration is carried through to
    the slide record — otherwise "no imagery" and "nothing but decoration" look
    identical afterwards.
    """
    regions: List[VisualRegion] = []
    total_regions = len(detection.get("charts") or []) + len(detection.get("imagery") or [])

    for ordinal, item in enumerate(detection.get("imagery") or [], start=1):
        kind = item.get("kind") or "diagram"
        if kind not in IMAGERY_KINDS:
            print(f"      (skipped '{kind}' — outside the imagery vocabulary)")
            continue

        region = VisualRegion(
            slide_index=slide_index,
            ordinal=ordinal,
            collector="imagery",
            kind=kind,
            box=tuple(item.get("box") or (0, 0, 0, 0)),
            alt=item.get("alt") or "",
            detail={
                k: v for k, v in (
                    ("depicts", item.get("depicts")),
                    ("role", item.get("role")),
                    ("labels", item.get("labels") or None),
                ) if v
            },
        )

        path, notes = crop_region(
            image_path, region.box, out_dir / f"{region.region_id}.jpg", IMAGERY_PADDING,
            regions_on_slide=total_regions,
        )
        region.notes.extend(notes)
        if path:
            region.local_path = f"./imagery/{path.name}"

        regions.append(region)

    return regions


# =============================================================================
# Orchestration
# =============================================================================

def collect_deck_visuals(
    deck_dir: str | Path,
    *,
    company: str,
    deck_slug: Optional[str] = None,
    charts: bool = True,
    imagery: bool = True,
    upload_to_cdn: bool = False,
    cdn_repo: str = "example-firm/portfolio",
    resume: bool = True,
    max_slides: Optional[int] = None,
    only_slides: Optional[Sequence[int]] = None,
) -> Dict[str, Any]:
    """
    Run both collectors over a deck the stenographer has already transcribed.

    Args:
        deck_dir: The stenographer's output directory for one deck.
        company: Portfolio company name, used in CDN image names.
        charts / imagery: Enable each collector independently. Detection runs
            once regardless; these choose what is cropped and recorded.
        upload_to_cdn: Mirror crops to the CDN.
        resume: Skip slides whose document already records a collection pass.
        max_slides: Stop after this many slides.
        only_slides: Re-examine exactly these slide numbers, ignoring ``resume``
            and leaving every other slide untouched. Detection rules change as
            often as they are corrected, and a rule change is not additive — it
            alters how every slide would be read. Re-running a whole deck to test
            one correction is expensive and slow; this narrows a change to the
            slides whose answers are known, so it can be judged before rollout.
    """
    deck_dir = Path(deck_dir)
    images_dir = deck_dir / "slides"
    if not images_dir.is_dir():
        raise FileNotFoundError(f"no rendered slides at {images_dir}")

    slide_docs = sorted(deck_dir.glob("[0-9]*.md"))
    if not slide_docs:
        raise FileNotFoundError(f"no slide documents in {deck_dir} — run the stenographer first")

    deck_slug = deck_slug or deck_dir.name

    print(f"\n{'=' * 62}\nVISUAL COLLECTORS\n{'=' * 62}")
    print(f"Deck:    {deck_slug}")
    print(f"Slides:  {len(slide_docs)}")
    print(f"Running: {'charts ' if charts else ''}{'imagery' if imagery else ''}\n")

    all_charts: List[VisualRegion] = []
    all_imagery: List[VisualRegion] = []
    skipped_decoration = 0
    examined = 0

    targeted = set(only_slides) if only_slides else None

    for doc in slide_docs[: max_slides or None]:
        index = int(doc.name.split("-")[0])
        if targeted is not None and index not in targeted:
            front, _ = _split_document(doc)
            all_charts += _rehydrate(front.get("charts"), index, "chart")
            all_imagery += _rehydrate(front.get("imagery"), index, "imagery")
            continue
        image_path = images_dir / f"{index:02d}.jpg"
        if not image_path.exists():
            print(f"  [{index:>2}] no rendered image — skipping")
            continue

        front, body = _split_document(doc)
        if resume and targeted is None and front.get("visuals_collected"):
            print(f"  [{index:>2}] already collected — skipping")
            all_charts += _rehydrate(front.get("charts"), index, "chart")
            all_imagery += _rehydrate(front.get("imagery"), index, "imagery")
            continue

        print(f"  [{index:>2}] detecting…", end=" ", flush=True)
        detection = detect_visuals(image_path, index)
        examined += 1

        if detection.get("error"):
            print(f"error: {detection['error'][:60]}")
            continue

        found_charts = collect_charts(detection, index, image_path, deck_dir / "charts") if charts else []
        found_imagery = collect_imagery(detection, index, image_path, deck_dir / "imagery") if imagery else []
        skipped = int(detection.get("decoration_skipped") or 0)
        skipped_decoration += skipped

        all_charts += found_charts
        all_imagery += found_imagery

        summary = []
        if found_charts:
            summary.append(f"{len(found_charts)} chart(s)")
        if found_imagery:
            summary.append(f"{len(found_imagery)} image(s)")
        if skipped:
            summary.append(f"{skipped} decorative skipped")
        print(", ".join(summary) or "nothing to collect")

        _write_back(doc, front, body, found_charts, found_imagery, skipped)

    if upload_to_cdn:
        _upload(all_charts + all_imagery, deck_dir, company, deck_slug, cdn_repo)
        for doc in slide_docs:
            index = int(doc.name.split("-")[0])
            front, body = _split_document(doc)
            regions = [r for r in all_charts + all_imagery if r.slide_index == index]
            if any(r.cdn_url for r in regions):
                _write_back(
                    doc, front, body,
                    [r for r in regions if r.collector == "chart"],
                    [r for r in regions if r.collector == "imagery"],
                    front.get("decoration_skipped", 0),
                )

    index_path = write_visuals_index(deck_dir)

    cropped = sum(1 for r in all_charts + all_imagery if r.local_path)
    flagged = [r for r in all_charts + all_imagery if r.notes and not r.local_path]

    print(f"\n{'=' * 62}")
    print(f"✓ {len(all_charts)} chart(s), {len(all_imagery)} image(s) from {examined} slide(s) examined")
    print(f"  {cropped} cropped, {len(flagged)} rejected, {skipped_decoration} decorative skipped")
    print(f"  index: {index_path.name}")
    for region in flagged[:8]:
        print(f"    ! slide {region.slide_index} {region.collector}: {region.notes[0][:70]}")
    print(f"{'=' * 62}\n")

    return {
        "charts": [r.as_frontmatter() for r in all_charts],
        "imagery": [r.as_frontmatter() for r in all_imagery],
        "decoration_skipped": skipped_decoration,
        "slides_examined": examined,
    }


# =============================================================================
# Document round-trip
# =============================================================================

def _split_document(path: Path) -> Tuple[Dict[str, Any], str]:
    """Frontmatter dict and the untouched body below it."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}, text
    _, front_text, body = text.split("---", 2)
    try:
        return (yaml.safe_load(front_text) or {}), body
    except yaml.YAMLError:
        return {}, body


def _write_back(
    path: Path,
    front: Dict[str, Any],
    body: str,
    charts: Sequence[VisualRegion],
    imagery: Sequence[VisualRegion],
    skipped: int,
) -> None:
    """
    Record a collection pass in the slide's frontmatter, leaving the body alone.

    The body carries the stenographer's transcription and any human commentary.
    Rewriting a slide document from a partial record is how the resume path once
    destroyed transcriptions; this function only ever touches frontmatter keys it
    owns.
    """
    front = dict(front)

    # Replace both keys unconditionally. Writing only non-empty lists left stale
    # entries behind whenever a region moved between collectors: slide 6's table
    # was correctly reclassified from imagery to chart and then appeared as both,
    # because the old imagery entry was never cleared.
    for key, regions in (("charts", charts), ("imagery", imagery)):
        if regions:
            front[key] = [r.as_frontmatter() for r in regions]
        else:
            front.pop(key, None)
    front["decoration_skipped"] = skipped
    front["visuals_collected"] = True
    front["visuals_collected_with"] = AGENT_SIGNATURE

    rendered = yaml.safe_dump(
        front, sort_keys=False, allow_unicode=True, default_flow_style=False, width=100
    ).rstrip()
    path.write_text(f"---\n{rendered}\n---{body}", encoding="utf-8")


def _rehydrate(entries, slide_index: int, collector: str) -> List[VisualRegion]:
    """Rebuild regions from a slide document already collected, for the summary."""
    regions: List[VisualRegion] = []
    for ordinal, entry in enumerate(entries or [], start=1):
        regions.append(VisualRegion(
            slide_index=slide_index,
            ordinal=ordinal,
            collector=collector,
            kind=entry.get("kind", ""),
            box=tuple(entry.get("crop") or (0, 0, 0, 0)),
            alt=entry.get("alt", ""),
            detail={k: v for k, v in entry.items()
                    if k not in ("id", "kind", "alt", "crop", "local", "cdn", "notes")},
            local_path=entry.get("local"),
            cdn_url=entry.get("cdn"),
        ))
    return regions


def _crop_name(company: str, region: "VisualRegion") -> str:
    """BEM name for one crop: ``MeridianAI__Slide-09-Chart-01--Line``."""
    import re as _re

    def train(value: str) -> str:
        parts = [p for p in _re.split(r"[^A-Za-z0-9]+", value or "") if p]
        return "-".join(p if any(c.isupper() for c in p[1:]) else p.capitalize()
                        for p in parts)

    return (
        f"{train(company)}__Slide-{region.slide_index:02d}-"
        f"{region.collector.capitalize()}-{region.ordinal:02d}--{train(region.kind)}"
    )


def _upload(
    regions: Sequence[VisualRegion],
    deck_dir: Path,
    company: str,
    deck_slug: str,
    cdn_repo: str,
) -> None:
    """Mirror crops to the CDN, in a folder beside the slides themselves."""
    from .slide_cdn import upload_slides

    uploadable = [r for r in regions if r.local_path and r.alt.strip()]
    if not uploadable:
        return

    print(f"\nUploading {len(uploadable)} crop(s)…")
    # Name each crop for the slide it came from and its position on that slide.
    # Two earlier attempts got this wrong: enumerating the upload list named a
    # slide-9 chart "Slide-01", and encoding slide+ordinal into one integer
    # produced "Slide-901", which reads as slide nine hundred and one.
    payload = [
        {
            "index": r.slide_index * 100 + r.ordinal,   # unique key for the result map
            "name": _crop_name(company, r),
            "path": str(deck_dir / r.local_path.lstrip("./")),
            "slide_type": f"{r.collector}-{r.kind}",
            "alt": r.alt,
        }
        for r in uploadable
    ]
    urls = upload_slides(
        payload, company=company, deck_slug=f"{deck_slug}/visuals", repo=cdn_repo
    )
    for region in uploadable:
        key = region.slide_index * 100 + region.ordinal
        if key in urls:
            region.cdn_url = urls[key]
    print(f"   {len(urls)} uploaded")


# =============================================================================
# Deck-level index
# =============================================================================

def write_visuals_index(deck_dir: str | Path) -> Path:
    """
    Write ``visuals.yaml`` — every collected visual in one deck, in one file.

    The collectors record each region in the slide document it came from, which
    is right for reading a slide but wrong for reusing a deck. Anything that
    generates further material from these assets — a one-pager, a memo section, a
    rebuilt deck — needs to answer "what visuals does this deck have" without
    opening thirty-eight files and parsing frontmatter out of each.

    Regenerated from the slide documents rather than accumulated, so it cannot
    drift from them: re-running it after any collection pass produces the current
    truth, and a stale index is impossible by construction.
    """
    deck_dir = Path(deck_dir)
    manifest_path = deck_dir / "visuals.yaml"

    deck_meta: Dict[str, Any] = {}
    deck_yaml = deck_dir / "deck.yaml"
    if deck_yaml.exists():
        deck_meta = yaml.safe_load(deck_yaml.read_text(encoding="utf-8")) or {}

    charts: List[Dict[str, Any]] = []
    imagery: List[Dict[str, Any]] = []
    skipped = 0

    for doc in sorted(deck_dir.glob("[0-9]*.md")):
        front, _ = _split_document(doc)
        index = int(doc.name.split("-")[0])
        skipped += int(front.get("decoration_skipped") or 0)

        for bucket, target in (("charts", charts), ("imagery", imagery)):
            for entry in front.get(bucket) or []:
                target.append({
                    "id": entry.get("id"),
                    "slide": index,
                    "slide_document": doc.name,
                    "slide_type": front.get("slide_type"),
                    "slide_image": front.get("slide_image_cdn") or front.get("slide_image_local"),
                    **{k: v for k, v in entry.items() if k not in ("id",)},
                })

    manifest = {
        "deck_family": deck_meta.get("deck_family") or deck_dir.name,
        "company": deck_meta.get("company"),
        "round": deck_meta.get("round"),
        "deck_variant": deck_meta.get("deck_variant"),
        "deck_version": deck_meta.get("deck_version"),
        "authored_by": deck_meta.get("authored_by"),
        "date_on_deck": deck_meta.get("date_on_deck"),
        "source_file": deck_meta.get("source_file"),
        "counts": {
            "charts": len(charts),
            "imagery": len(imagery),
            "collected": sum(1 for r in charts + imagery if r.get("status") == "collected"),
            "rejected": sum(1 for r in charts + imagery if r.get("status") == "rejected"),
            "decoration_skipped": skipped,
        },
        "kinds": {
            k: sum(1 for r in charts + imagery if r.get("kind") == k)
            for k in sorted({r.get("kind") for r in charts + imagery if r.get("kind")})
        },
        "charts": charts,
        "imagery": imagery,
    }

    manifest_path.write_text(
        yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True, width=100),
        encoding="utf-8",
    )
    return manifest_path
