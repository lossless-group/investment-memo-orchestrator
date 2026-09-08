"""
Tests for dataroom media transcription.

Video was the one dataroom category the scanner always reported and never used,
while being the largest thing in the repo — 90 MB across three ProfileHealth
files, in plain git rather than LFS because `.gitattributes` never covered
`*.mp4`. These tests pin the split that resolves it: the media stays in the
gitignored `_zip-originals/`, the transcript goes back into the dataroom where
the scanner reads it.

No network. Transcription itself is stubbed; what is under test is the routing,
the idempotence, and the failure handling.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.media_transcribe import (
    MEDIA_SUFFIXES,
    TranscriptResult,
    is_media,
    transcribe_dataroom_media,
    transcript_path_for,
    write_transcript,
)


class TestMediaDetection:
    def test_video_and_audio_are_media(self):
        for suffix in (".mp4", ".mov", ".mp3", ".wav", ".m4a"):
            assert is_media(Path(f"x{suffix}"))

    def test_documents_are_not(self):
        for suffix in (".pdf", ".docx", ".xlsx", ".md"):
            assert not is_media(Path(f"x{suffix}"))

    def test_detection_is_case_insensitive(self):
        assert is_media(Path("PITCH.MP4"))

    def test_mp4_is_covered(self):
        """The specific format that shipped 90 MB into plain git."""
        assert ".mp4" in MEDIA_SUFFIXES


class TestTranscriptRouting:
    """Media sits in `_zip-originals/media/<subdir>/`; the transcript belongs
    back in `<subdir>/` where the scanner looks."""

    def test_subdirectory_is_preserved(self, tmp_path):
        root = tmp_path / "Dataroom"
        src = root / "_zip-originals" / "media" / "Company Overview" / "Pitch.mp4"
        assert transcript_path_for(src, root) == root / "Company Overview" / "Pitch.transcript.md"

    def test_media_at_the_root_lands_at_the_root(self, tmp_path):
        root = tmp_path / "Dataroom"
        src = root / "_zip-originals" / "media" / "Pitch.mp4"
        assert transcript_path_for(src, root) == root / "Pitch.transcript.md"

    def test_transcript_never_lands_inside_zip_originals(self, tmp_path):
        """A transcript written into the gitignored directory would never be
        committed, which defeats the entire arrangement."""
        root = tmp_path / "Dataroom"
        src = root / "_zip-originals" / "media" / "Product" / "Demo.mp4"
        assert "_zip-originals" not in str(transcript_path_for(src, root))


class TestWriteTranscript:
    def test_header_records_the_source_and_the_arrangement(self, tmp_path):
        result = TranscriptResult(Path("/x/Pitch.mp4"), None, "Hello there.", 292.4)
        dest = write_transcript(result, tmp_path / "Pitch.transcript.md")
        text = dest.read_text()
        assert "Pitch.mp4" in text
        assert "4m52s" in text
        assert "_zip-originals" in text and "not committed" in text
        assert "Hello there." in text

    def test_parent_directories_are_created(self, tmp_path):
        result = TranscriptResult(Path("/x/A.mp4"), None, "text", 10.0)
        dest = write_transcript(result, tmp_path / "deep" / "nested" / "A.transcript.md")
        assert dest.exists()


class TestSweep:
    def _media_tree(self, tmp_path):
        root = tmp_path / "Dataroom"
        media = root / "_zip-originals" / "media" / "Company Overview"
        media.mkdir(parents=True)
        (media / "Pitch.mp4").write_bytes(b"\x00\x01")
        return root

    def test_no_media_directory_is_a_no_op(self, tmp_path):
        assert transcribe_dataroom_media(tmp_path / "Empty") == []

    def test_existing_transcript_is_not_regenerated(self, tmp_path, monkeypatch):
        """Transcription costs money and the result does not change."""
        root = self._media_tree(tmp_path)
        dest = root / "Company Overview" / "Pitch.transcript.md"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("already done")

        called = []
        monkeypatch.setattr("src.media_transcribe.transcribe",
                            lambda *a, **k: called.append(1) or TranscriptResult(Path("x"), None, "", 0.0))
        results = transcribe_dataroom_media(root)
        assert called == []
        assert results[0].text == "already done"

    def test_overwrite_forces_regeneration(self, tmp_path, monkeypatch):
        root = self._media_tree(tmp_path)
        dest = root / "Company Overview" / "Pitch.transcript.md"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("stale")
        monkeypatch.setattr("src.media_transcribe.transcribe",
                            lambda src, **k: TranscriptResult(src, None, "fresh text", 12.0))
        transcribe_dataroom_media(root, overwrite=True)
        assert "fresh text" in dest.read_text()

    def test_failure_is_reported_not_raised(self, tmp_path, monkeypatch):
        root = self._media_tree(tmp_path)
        monkeypatch.setattr("src.media_transcribe.transcribe",
                            lambda src, **k: TranscriptResult(src, None, "", 0.0, "ffmpeg not installed"))
        results = transcribe_dataroom_media(root)
        assert len(results) == 1 and not results[0].ok
        assert results[0].error == "ffmpeg not installed"

    def test_non_media_files_are_skipped(self, tmp_path, monkeypatch):
        root = self._media_tree(tmp_path)
        (root / "_zip-originals" / "media" / "notes.txt").write_text("x")
        monkeypatch.setattr("src.media_transcribe.transcribe",
                            lambda src, **k: TranscriptResult(src, None, "t", 1.0))
        results = transcribe_dataroom_media(root)
        assert all(is_media(r.source) for r in results)


class TestProfileHealthTranscripts:
    """The three files that prompted this. Media gone from git, transcripts in."""

    ROOT = Path("io/humain/deals/ProfileHealth/inputs/ProfileHealth-Dataroom")

    def test_transcripts_exist_and_media_is_parked(self):
        if not self.ROOT.exists():
            pytest.skip("ProfileHealth dataroom not present (private submodule)")
        transcripts = list(self.ROOT.rglob("*.transcript.md"))
        assert len(transcripts) == 3
        assert not list(self.ROOT.glob("*/*.mp4")), "media should live in _zip-originals"

    def test_transcripts_carry_real_content(self):
        if not self.ROOT.exists():
            pytest.skip("ProfileHealth dataroom not present (private submodule)")
        pitch = self.ROOT / "Company Overview" / "5 Minute Pitch.transcript.md"
        assert pitch.exists() and len(pitch.read_text()) > 2000
