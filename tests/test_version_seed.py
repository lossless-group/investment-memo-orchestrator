"""
Tests for seeding a new version directory from the previous one.

Without seeding, every guarantee the thesis-frame feature makes is inert:
`write_or_append_research` appends only to a file that already exists, and the
`prose: unchanged` guard checks `existing.exists()`. In a fresh empty directory
both fall through to regeneration — which is precisely what a framed run must
not do, and would have cost ProfileHealth 62.8 KB of clinician research and a
hand-written SAFE transcription on the very first run.
"""

from __future__ import annotations

from pathlib import Path

from src.version_seed import SEEDED_DIRS, previous_version_dir, seed_version


class Frame:
    slug = "test"


def make_version(root: Path, name: str, *, research=("06-opportunity-research.md",),
                 sections=("09-funding-terms.md",), build=True) -> Path:
    d = root / name
    (d / "1-research").mkdir(parents=True, exist_ok=True)
    (d / "2-sections").mkdir(parents=True, exist_ok=True)
    for f in research:
        (d / "1-research" / f).write_text("clinician TAM is 350K physicians")
    for f in sections:
        (d / "2-sections" / f).write_text("hand-written SAFE transcription")
    if build:
        (d / "7-Deal-v.md").write_text("assembled")
        (d / "3-validation.md").write_text("stale scores")
        (d / "exports").mkdir(exist_ok=True)
        (d / "exports" / "x.html").write_text("stale export")
    return d


class TestPreviousVersion:
    def test_finds_the_immediately_prior_version(self, tmp_path):
        make_version(tmp_path, "D-v0.0.1")
        make_version(tmp_path, "D-v0.0.3")
        assert previous_version_dir(tmp_path / "D-v0.0.4").name == "D-v0.0.3"

    def test_sorts_numerically_not_lexically(self, tmp_path):
        """v0.0.10 beats v0.0.9; a string sort gets this backwards."""
        make_version(tmp_path, "D-v0.0.9")
        make_version(tmp_path, "D-v0.0.10")
        assert previous_version_dir(tmp_path / "D-v0.0.11").name == "D-v0.0.10"

    def test_ignores_later_versions(self, tmp_path):
        make_version(tmp_path, "D-v0.0.1")
        make_version(tmp_path, "D-v0.0.9")
        assert previous_version_dir(tmp_path / "D-v0.0.2").name == "D-v0.0.1"

    def test_none_when_first_version(self, tmp_path):
        assert previous_version_dir(tmp_path / "D-v0.0.1") is None


class TestSeeding:
    def test_seeds_the_durable_layers(self, tmp_path):
        make_version(tmp_path, "D-v0.0.3")
        dest = tmp_path / "D-v0.0.4"
        dest.mkdir()
        r = seed_version(dest, frame=Frame())
        assert r.seeded
        assert sorted(r.dirs_copied) == sorted(SEEDED_DIRS)
        assert (dest / "1-research" / "06-opportunity-research.md").exists()
        assert (dest / "2-sections" / "09-funding-terms.md").exists()

    def test_research_content_arrives_so_appends_can_extend_it(self, tmp_path):
        make_version(tmp_path, "D-v0.0.3")
        dest = tmp_path / "D-v0.0.4"
        dest.mkdir()
        seed_version(dest, frame=Frame())
        assert "350K physicians" in (dest / "1-research" / "06-opportunity-research.md").read_text()

    def test_build_outputs_are_not_carried_forward(self, tmp_path):
        """A stale assembled draft or export shipped beside fresh prose is worse
        than no artifact at all."""
        make_version(tmp_path, "D-v0.0.3")
        dest = tmp_path / "D-v0.0.4"
        dest.mkdir()
        seed_version(dest, frame=Frame())
        assert not (dest / "7-Deal-v.md").exists()
        assert not (dest / "3-validation.md").exists()
        assert not (dest / "exports").exists()

    def test_unframed_run_is_untouched(self, tmp_path):
        """An unframed re-run means a clean directory; changing that would
        surprise every existing caller."""
        make_version(tmp_path, "D-v0.0.3")
        dest = tmp_path / "D-v0.0.4"
        dest.mkdir()
        r = seed_version(dest, frame=None)
        assert not r.seeded and "no frame" in r.reason
        assert not (dest / "1-research").exists()

    def test_fresh_disables_seeding(self, tmp_path):
        make_version(tmp_path, "D-v0.0.3")
        dest = tmp_path / "D-v0.0.4"
        dest.mkdir()
        r = seed_version(dest, frame=Frame(), fresh=True)
        assert not r.seeded and "--fresh" in r.reason

    def test_existing_files_are_never_overwritten(self, tmp_path):
        make_version(tmp_path, "D-v0.0.3")
        dest = tmp_path / "D-v0.0.4"
        (dest / "1-research").mkdir(parents=True)
        (dest / "1-research" / "06-opportunity-research.md").write_text("already here")
        seed_version(dest, frame=Frame())
        assert (dest / "1-research" / "06-opportunity-research.md").read_text() == "already here"

    def test_seeding_twice_is_safe(self, tmp_path):
        make_version(tmp_path, "D-v0.0.3")
        dest = tmp_path / "D-v0.0.4"
        dest.mkdir()
        first = seed_version(dest, frame=Frame())
        second = seed_version(dest, frame=Frame())
        assert first.seeded and not second.seeded

    def test_first_version_seeds_nothing(self, tmp_path):
        dest = tmp_path / "D-v0.0.1"
        dest.mkdir()
        r = seed_version(dest, frame=Frame())
        assert not r.seeded and "no previous version" in r.reason
