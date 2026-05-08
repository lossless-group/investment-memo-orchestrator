"""Pydantic schemas for the TeamRoster artifact.

Implements the structured-output shape from
context-v/explorations/Crawl-for-Better-Team-Structured-Output.md and
context-v/plans/Team-and-People-Metadata-Ingestion.md.

Used by:
- cli/extract_team_roster.py (writes team-roster.json)
- src/scrapers/team_roster_scraper.py (passes model_json_schema() to Firecrawl)
- Future: cli/improve_team_section.py (consumes the roster)
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator


PhotoSource = Literal[
    "org_site",
    "wikipedia",
    "crunchbase",
    "conference",
    "github_avatar",
    "linkedin_public",
    "other",
]

CrawlerName = Literal["firecrawl", "crawl4ai", "playwright"]


class SocialLinks(BaseModel):
    """Professional-only social profile URLs for a team member.

    Always include: linkedin, x_twitter, bluesky, medium, github, personal_site.
    Conditionally include: youtube, tiktok — only when the channel is a
    branded professional creator presence (not personal/family content).
    Never include: facebook, instagram (excluded by extraction rubric).
    """

    linkedin: HttpUrl | None = None
    x_twitter: HttpUrl | None = None
    bluesky: HttpUrl | None = None
    medium: HttpUrl | None = None
    youtube: HttpUrl | None = None
    tiktok: HttpUrl | None = None
    github: HttpUrl | None = None
    personal_site: HttpUrl | None = None

    @model_validator(mode="before")
    @classmethod
    def _empty_strings_to_none(cls, data: Any) -> Any:
        # Firecrawl/LLM extractors often emit "" for missing optional URL fields.
        # HttpUrl rejects empty strings, so normalize before validation.
        if isinstance(data, dict):
            return {k: (None if v == "" else v) for k, v in data.items()}
        return data


class Photo(BaseModel):
    """A candidate headshot URL with provenance and external-fetch durability.

    `is_externally_stable` means the URL returned 200 + image content-type
    when fetched with no Referer/cookie — i.e. the MemoPop app can embed it.
    """

    url: HttpUrl
    source: PhotoSource
    is_externally_stable: bool = False
    width: int | None = None
    height: int | None = None
    fetched_at: datetime | None = None


class TeamMember(BaseModel):
    name: str
    title: str
    bio_short: str | None = Field(
        default=None, description="One-sentence summary suitable for a card."
    )
    bio_long: str | None = Field(
        default=None, description="Paragraph-length bio for hover/expanded views."
    )
    photo: Photo | None = None
    socials: SocialLinks = Field(default_factory=SocialLinks)
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Extractor confidence in this record (0..1).",
    )
    sources: list[HttpUrl] = Field(
        default_factory=list,
        description="URLs the extractor used to populate this record.",
    )


class TeamRosterExtraction(BaseModel):
    """The subset of TeamRoster that an extractor (Firecrawl) can populate from
    page content. Runtime metadata (crawled_at, crawler, organization,
    organization_url) is set by the caller, not the extractor.
    """

    team_page_url: HttpUrl | None = Field(
        default=None,
        description="The canonical team/people/leadership URL the members were extracted from.",
    )
    members: list[TeamMember] = Field(default_factory=list)


class TeamRoster(BaseModel):
    organization: str
    organization_url: HttpUrl
    team_page_url: HttpUrl | None = None
    members: list[TeamMember] = Field(default_factory=list)
    crawled_at: datetime
    crawler: CrawlerName
    notes: str | None = None
