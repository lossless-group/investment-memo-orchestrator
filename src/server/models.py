"""Request and response shapes for the server. Mirrors `generate_memo` kwargs."""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class CreateMemoRequest(BaseModel):
    """Payload accepted by `POST /memos`. Field names mirror `generate_memo()` kwargs."""

    company_name: str = Field(..., min_length=1, description="Name of the company / deal to analyze")
    investment_type: Literal["direct", "fund"] = "direct"
    memo_mode: Literal["consider", "justify"] = "consider"
    firm: Optional[str] = Field(None, description="Firm slug for firm-scoped IO (e.g., 'hypernova')")

    company_url: Optional[str] = None
    company_description: Optional[str] = None
    company_stage: Optional[str] = None
    research_notes: Optional[str] = None

    deck_path: Optional[str] = Field(None, description="Absolute path to a pitch deck PDF")
    dataroom_path: Optional[str] = Field(None, description="Absolute path to a dataroom directory")
    company_trademark_light: Optional[str] = None
    company_trademark_dark: Optional[str] = None

    outline_name: Optional[str] = None
    scorecard_name: Optional[str] = None

    fresh: bool = False
    force_version: Optional[str] = None


class ResumeMemoRequest(BaseModel):
    """Payload accepted by `POST /memos/resume`. Picks up an interrupted run from the
    last on-disk checkpoint detected by `cli/resume_from_interruption.detect_resume_point`."""

    company_name: str = Field(..., min_length=1, description="Deal / company name to resume")
    firm: Optional[str] = Field(None, description="Firm slug for firm-scoped IO")
    version: Optional[str] = Field(
        None, description="Specific version to resume (e.g., 'v0.0.6'). Defaults to latest."
    )


class CreateMemoResponse(BaseModel):
    job_id: str
    status: Literal["queued", "running", "completed", "failed"]


class JobStatus(BaseModel):
    job_id: str
    status: Literal["queued", "running", "completed", "failed"]
    company_name: str
    firm: Optional[str] = None
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    output_dir: Optional[str] = None
    version: Optional[str] = None
    error: Optional[str] = None


class ArtifactInfo(BaseModel):
    path: str
    size: int


class ArtifactList(BaseModel):
    output_dir: Optional[str]
    files: list[ArtifactInfo]
