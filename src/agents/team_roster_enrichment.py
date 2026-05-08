"""Team roster socials enrichment via Firecrawl search.

For each member missing professional socials, run a composite search by
name + organization and dispatch the results by domain. Validates against
the existing `socials_enrichment.is_valid_profile_url` rules; canonicalizes
LinkedIn `/posts/<handle>_...` URLs to `/in/<handle>` so we end up with
profile pages, not post permalinks.

Phase 2 acceptance criterion: a roster is not "extracted" until we've at
least *tried* to find professional socials by name + title.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from firecrawl import Firecrawl

from src.schemas.team_roster import SocialLinks, TeamMember, TeamRoster


# host (lowered, www. stripped) -> (SocialLinks field name, platform key for validator)
_DOMAIN_MAP: dict[str, tuple[str, str]] = {
    "linkedin.com": ("linkedin", "linkedin"),
    "twitter.com": ("x_twitter", "x"),
    "x.com": ("x_twitter", "x"),
    "bsky.app": ("bluesky", "bluesky"),
    "github.com": ("github", "github"),
    "medium.com": ("medium", "medium"),
}

# A LinkedIn post permalink pattern: linkedin.com/posts/<handle>_<rest>.
# We extract <handle> and synthesize the /in/<handle> profile URL.
_LINKEDIN_POST_HANDLE = re.compile(r"linkedin\.com/posts/([a-zA-Z0-9-]+)_", re.IGNORECASE)

_PLATFORMS_TO_FILL = ("linkedin", "x_twitter", "github", "bluesky")

# Per-platform anchored profile-URL patterns. The captured group is the
# *handle* — used downstream for the name-overlap check. These reject
# `/posts/`, `/status/`, `/company/`, `/showcase/`, `/business/`, etc.
_PROFILE_PATTERNS: dict[str, re.Pattern] = {
    "linkedin": re.compile(
        r"^https?://(?:www\.)?linkedin\.com/in/([^/?#]+?)/?$", re.IGNORECASE
    ),
    "x": re.compile(
        r"^https?://(?:www\.)?(?:x|twitter)\.com/([A-Za-z0-9_]{1,30})/?$", re.IGNORECASE
    ),
    "bluesky": re.compile(
        r"^https?://bsky\.app/profile/([^/?#]+?)/?$", re.IGNORECASE
    ),
    "github": re.compile(
        r"^https?://(?:www\.)?github\.com/([A-Za-z0-9][A-Za-z0-9-]{0,38})/?$",
        re.IGNORECASE,
    ),
    "medium": re.compile(
        r"^https?://(?:www\.)?medium\.com/@?([^/?#]+?)/?$", re.IGNORECASE
    ),
}


def _classify_url(url: str) -> tuple[str, str] | None:
    try:
        host = urlparse(url).netloc.lower().removeprefix("www.")
    except ValueError:
        return None
    for domain, mapping in _DOMAIN_MAP.items():
        if host == domain or host.endswith("." + domain):
            return mapping
    return None


def _canonicalize_linkedin(url: str) -> str:
    """Turn /posts/<handle>_... into /in/<handle>. Pass other URLs through."""
    m = _LINKEDIN_POST_HANDLE.search(url)
    if m:
        return f"https://www.linkedin.com/in/{m.group(1)}"
    return url


def _name_tokens(name: str) -> set[str]:
    """Lower-case alphabetic tokens of length ≥3 from a person's name."""
    return {t for t in re.findall(r"[a-z]+", name.lower()) if len(t) >= 3}


def _handle_chars(handle: str) -> str:
    """Lower-case alphanumeric form of a handle, useful for substring checks."""
    return re.sub(r"[^a-z0-9]+", "", handle.lower())


def _name_matches_handle(name: str, handle: str) -> bool:
    """True iff at least one ≥3-char name token appears in the handle.

    Drops false positives like /in/aixventures for "Anthony Goldbloom",
    /in/jonchee for "Krish Ramadurai", /in/techtrek for "Jason McBride".
    """
    handle_norm = _handle_chars(handle)
    return any(tok in handle_norm for tok in _name_tokens(name))


def _profile_handle(url: str, platform: str) -> str | None:
    """If `url` is a valid profile URL for `platform`, return the handle."""
    pattern = _PROFILE_PATTERNS.get(platform)
    if pattern is None:
        return None
    match = pattern.match(url)
    return match.group(1) if match else None


def _is_acceptable(url: str, platform: str, name: str) -> bool:
    """Stricter than socials_enrichment.is_valid_profile_url:
    requires the handle to share at least one ≥3-char token with the name.
    """
    handle = _profile_handle(url, platform)
    if handle is None:
        return False
    return _name_matches_handle(name, handle)


def enrich_member_socials(
    member: TeamMember,
    organization: str,
    fc: Firecrawl,
    *,
    limit: int = 10,
) -> TeamMember:
    """Run one composite search per member and populate any missing socials."""
    member_dict = member.model_dump(mode="json")
    socials_dict = member_dict.get("socials") or {}

    if all(socials_dict.get(f) for f in _PLATFORMS_TO_FILL):
        return member  # nothing to do

    query = (
        f'"{member.name}" "{organization}" '
        f"(linkedin OR twitter OR x.com OR github OR bsky.app)"
    )
    try:
        result = fc.search(query, limit=limit)
    except Exception as e:  # noqa: BLE001
        print(f"  [enrich] search failed for {member.name}: {e}")
        return member

    raw = result.model_dump() if hasattr(result, "model_dump") else result
    web = raw.get("web") or []
    sources_set = set(member_dict.get("sources") or [])

    for item in web:
        url = item.get("url") if isinstance(item, dict) else getattr(item, "url", None)
        if not url:
            continue
        classification = _classify_url(url)
        if classification is None:
            continue
        field, platform = classification
        if socials_dict.get(field):
            continue  # already populated, don't overwrite

        # LinkedIn-specific canonicalization: posts → profile.
        if platform == "linkedin":
            url = _canonicalize_linkedin(url)

        if _is_acceptable(url, platform, member.name):
            socials_dict[field] = url
            sources_set.add(url)

    member_dict["socials"] = socials_dict
    member_dict["sources"] = sorted(sources_set)
    return TeamMember.model_validate(member_dict)


def enrich_roster_socials(roster: TeamRoster, fc: Firecrawl) -> TeamRoster:
    """Enrich every member's socials. One search call per member."""
    enriched = [enrich_member_socials(m, roster.organization, fc) for m in roster.members]
    return roster.model_copy(update={"members": enriched})
