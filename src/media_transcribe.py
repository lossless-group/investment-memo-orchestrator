"""
Turn dataroom video and audio into transcripts the pipeline can actually read.

Video is the one dataroom category the scanner has always reported and never
used — `unsupported file type '.mp4'` — while being, by a wide margin, the
largest thing in the repo. ProfileHealth carried 90 MB across three files that
no agent could open, in plain git rather than LFS because `.gitattributes` never
covered `*.mp4`.

The resolution splits the artifact from its content. The media file stays in
`_zip-originals/`, which is gitignored, so the bytes live locally and never reach
a remote. The transcript is written back into the dataroom beside where the media
used to sit, as a small markdown file that commits cleanly and that
`document_scanner` reads like any other document.

Audio is extracted with ffmpeg to 16 kHz mono — Whisper's native rate, and around
2 MB per ten minutes, which keeps most datarooms under the API's 25 MB per-request
limit without chunking. Longer media is split on time and the segments are joined.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import List, Optional

MEDIA_SUFFIXES = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm", ".mp3", ".wav", ".m4a", ".aac"}

# Whisper's request ceiling is 25 MB. 16 kHz mono PCM-to-mp3 lands near 1 MB per
# 8 minutes, so a 20-minute segment is comfortably inside it with headroom for
# containers that compress worse than expected.
SEGMENT_SECONDS = 20 * 60


@dataclass
class TranscriptResult:
    source: Path
    transcript_path: Optional[Path]
    text: str
    seconds: float
    error: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.text.strip()) and not self.error


def is_media(path: Path) -> bool:
    return path.suffix.lower() in MEDIA_SUFFIXES


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def probe_duration(path: Path) -> float:
    """Media length in seconds; 0.0 when ffprobe can't tell."""
    if not shutil.which("ffprobe"):
        return 0.0
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=60,
        )
        return float(out.stdout.strip() or 0.0)
    except (subprocess.SubprocessError, ValueError):
        return 0.0


def extract_audio(source: Path, dest: Path, *, start: Optional[float] = None,
                  duration: Optional[float] = None) -> bool:
    """16 kHz mono mp3 — Whisper's native rate, and small enough to post."""
    cmd = ["ffmpeg", "-nostdin", "-y", "-loglevel", "error"]
    if start is not None:
        cmd += ["-ss", str(start)]
    cmd += ["-i", str(source)]
    if duration is not None:
        cmd += ["-t", str(duration)]
    cmd += ["-vn", "-ac", "1", "-ar", "16000", "-b:a", "32k", str(dest)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        return result.returncode == 0 and dest.exists() and dest.stat().st_size > 0
    except subprocess.SubprocessError:
        return False


def _transcribe_audio_file(path: Path, model: str) -> str:
    from openai import OpenAI

    client = OpenAI()
    with open(path, "rb") as fh:
        response = client.audio.transcriptions.create(model=model, file=fh)
    return (getattr(response, "text", "") or "").strip()


def transcribe(source: Path, *, model: str = "whisper-1") -> TranscriptResult:
    """Transcribe one media file. Never raises — a failure is reported, not thrown."""
    if not source.exists():
        return TranscriptResult(source, None, "", 0.0, "file not found")
    if not ffmpeg_available():
        return TranscriptResult(source, None, "", 0.0, "ffmpeg not installed")
    if not os.getenv("OPENAI_API_KEY"):
        return TranscriptResult(source, None, "", 0.0, "OPENAI_API_KEY not set")

    seconds = probe_duration(source)
    pieces: List[str] = []

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        starts = [0.0] if seconds <= SEGMENT_SECONDS or seconds == 0.0 else [
            float(s) for s in range(0, int(seconds) + 1, SEGMENT_SECONDS)
        ]
        for i, start in enumerate(starts):
            chunk = tmpdir / f"seg-{i:03d}.mp3"
            ok = extract_audio(
                source, chunk,
                start=None if len(starts) == 1 else start,
                duration=None if len(starts) == 1 else SEGMENT_SECONDS,
            )
            if not ok:
                return TranscriptResult(source, None, "", seconds, "audio extraction failed")
            try:
                pieces.append(_transcribe_audio_file(chunk, model))
            except Exception as exc:  # noqa: BLE001 - transcription must not kill a run
                return TranscriptResult(source, None, "", seconds, f"transcription failed: {exc}")

    return TranscriptResult(source, None, "\n\n".join(p for p in pieces if p).strip(), seconds)


def transcript_path_for(source: Path, dataroom_root: Path) -> Path:
    """
    Where a media file's transcript belongs.

    Media lives under `_zip-originals/media/<subdir>/<name>.mp4`; the transcript
    goes back to `<subdir>/<name>.transcript.md` in the dataroom proper, which is
    where the scanner looks and where the file is small enough to commit.
    """
    parts = source.parts
    subdir = ""
    if "media" in parts:
        after = parts[parts.index("media") + 1:-1]
        subdir = str(Path(*after)) if after else ""
    target_dir = dataroom_root / subdir if subdir else dataroom_root
    return target_dir / f"{source.stem}.transcript.md"


def write_transcript(result: TranscriptResult, destination: Path) -> Path:
    mins = int(result.seconds // 60)
    secs = int(result.seconds % 60)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        f"# {result.source.stem} — Transcript\n\n"
        f"_Machine transcript of `{result.source.name}` "
        f"({mins}m{secs:02d}s), generated {date.today().isoformat()}. "
        f"The source media is kept in `_zip-originals/` and is not committed._\n\n"
        f"---\n\n"
        f"{result.text}\n"
    )
    return destination


def transcribe_dataroom_media(dataroom_root: Path, *, model: str = "whisper-1",
                              overwrite: bool = False) -> List[TranscriptResult]:
    """
    Transcribe every media file parked under `<dataroom>/_zip-originals/media/`.

    Idempotent: an existing transcript is left alone unless `overwrite` is set,
    because transcription costs money and the result does not change.
    """
    media_root = Path(dataroom_root) / "_zip-originals" / "media"
    if not media_root.exists():
        return []

    results: List[TranscriptResult] = []
    for path in sorted(media_root.rglob("*")):
        if not path.is_file() or not is_media(path):
            continue
        destination = transcript_path_for(path, Path(dataroom_root))
        if destination.exists() and not overwrite:
            results.append(TranscriptResult(path, destination, destination.read_text(), 0.0))
            continue
        result = transcribe(path, model=model)
        if result.ok:
            result.transcript_path = write_transcript(result, destination)
        results.append(result)
    return results
