"""
YAML-based correction system for investment memos.

This module handles loading, parsing, and validating correction YAML files
that specify factual corrections, incomplete information, and narrative shaping
for investment memos.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from pathlib import Path
import yaml


@dataclass
class CorrectionObject:
    """Represents a single correction from YAML."""

    type: str  # "inaccurate", "incomplete", "narrative", "mixed"
    inaccurate_info: Optional[str] = None
    correct_info: Optional[str] = None
    incomplete_info: Optional[str] = None
    additional_info: Optional[str] = None
    affected_sections: List[str] = field(default_factory=list)
    section: Optional[str] = None  # For narrative-only corrections
    sources: List[str] = field(default_factory=list)
    narrative_comments: List[str] = field(default_factory=list)
    update_research: bool = False  # Whether to update research artifacts


@dataclass
class CorrectionsConfig:
    """Complete corrections configuration from YAML."""

    company: str
    source_version: str
    output_mode: str  # "new_version" or "in_place"
    date_created: Optional[str] = None
    corrections: List[CorrectionObject] = field(default_factory=list)


def load_corrections_yaml(corrections_file: Path) -> CorrectionsConfig:
    """
    Load and validate corrections YAML file.

    Args:
        corrections_file: Path to corrections YAML file

    Returns:
        CorrectionsConfig object with parsed corrections

    Raises:
        ValueError: If YAML is invalid or missing required fields
        FileNotFoundError: If file doesn't exist
    """
    if not corrections_file.exists():
        raise FileNotFoundError(f"Corrections file not found: {corrections_file}")

    with open(corrections_file) as f:
        data = yaml.safe_load(f)

    # Validate schema
    validate_corrections_schema(data)

    # Parse into CorrectionsConfig
    config = CorrectionsConfig(
        company=data["company"],
        source_version=data["source_version"],
        output_mode=data["output_mode"],
        date_created=data.get("date_created"),
        corrections=parse_corrections(data["corrections"])
    )

    return config


def validate_corrections_schema(data: dict) -> None:
    """
    Validate YAML structure and required fields.

    Args:
        data: Parsed YAML dictionary

    Raises:
        ValueError: If schema is invalid
    """
    # Validate top-level fields
    required_top = ["company", "source_version", "output_mode", "corrections"]
    for field in required_top:
        if field not in data:
            raise ValueError(f"Missing required field: {field}")

    # Validate output_mode
    if data["output_mode"] not in ["new_version", "in_place"]:
        raise ValueError(
            f"Invalid output_mode: {data['output_mode']}. "
            "Must be 'new_version' or 'in_place'"
        )

    # Validate corrections list
    if not isinstance(data["corrections"], list):
        raise ValueError("'corrections' must be a list")

    if len(data["corrections"]) == 0:
        raise ValueError("'corrections' list cannot be empty")

    # Validate each correction
    for i, corr in enumerate(data["corrections"]):
        validate_correction_object(corr, i + 1)


def validate_correction_object(corr: dict, index: int) -> None:
    """
    Validate a single correction object.

    Args:
        corr: Correction dictionary
        index: Correction number (for error messages)

    Raises:
        ValueError: If correction is invalid
    """
    if "type" not in corr:
        raise ValueError(f"Correction {index}: Missing 'type' field")

    corr_type = corr["type"]

    if corr_type == "inaccurate":
        required = ["inaccurate_information", "correct_information", "affected_sections"]
        for field_name in required:
            if field_name not in corr:
                raise ValueError(f"Correction {index} (inaccurate): Missing '{field_name}'")

        if not isinstance(corr["affected_sections"], list) or len(corr["affected_sections"]) == 0:
            raise ValueError(f"Correction {index}: 'affected_sections' must be a non-empty list")

    elif corr_type == "incomplete":
        required = ["incomplete_information", "additional_information", "affected_sections"]
        for field_name in required:
            if field_name not in corr:
                raise ValueError(f"Correction {index} (incomplete): Missing '{field_name}'")

        if not isinstance(corr["affected_sections"], list) or len(corr["affected_sections"]) == 0:
            raise ValueError(f"Correction {index}: 'affected_sections' must be a non-empty list")

    elif corr_type == "narrative":
        required = ["section", "narrative_shaping_comments"]
        for field_name in required:
            if field_name not in corr:
                raise ValueError(f"Correction {index} (narrative): Missing '{field_name}'")

        if not isinstance(corr["narrative_shaping_comments"], list) or len(corr["narrative_shaping_comments"]) == 0:
            raise ValueError(f"Correction {index}: 'narrative_shaping_comments' must be a non-empty list")

    elif corr_type == "mixed":
        required = ["affected_sections"]
        for field_name in required:
            if field_name not in corr:
                raise ValueError(f"Correction {index} (mixed): Missing '{field_name}'")

        if not isinstance(corr["affected_sections"], list) or len(corr["affected_sections"]) == 0:
            raise ValueError(f"Correction {index}: 'affected_sections' must be a non-empty list")

        # Mixed must have at least one of: inaccurate, incomplete, or narrative
        has_inaccurate = "inaccurate_information" in corr and "correct_information" in corr
        has_incomplete = "incomplete_information" in corr and "additional_information" in corr
        has_narrative = "narrative_shaping_comments" in corr and len(corr["narrative_shaping_comments"]) > 0

        if not (has_inaccurate or has_incomplete or has_narrative):
            raise ValueError(
                f"Correction {index} (mixed): Must have at least one of: "
                "inaccurate info, incomplete info, or narrative comments"
            )

    else:
        raise ValueError(
            f"Correction {index}: Invalid type '{corr_type}'. "
            "Must be 'inaccurate', 'incomplete', 'narrative', or 'mixed'"
        )


def parse_corrections(corrections_list: list) -> List[CorrectionObject]:
    """
    Parse validated YAML corrections into CorrectionObject list.

    Args:
        corrections_list: List of correction dictionaries from YAML

    Returns:
        List of CorrectionObject instances
    """
    corrections = []

    for corr in corrections_list:
        corrections.append(CorrectionObject(
            type=corr["type"],
            inaccurate_info=corr.get("inaccurate_information"),
            correct_info=corr.get("correct_information"),
            incomplete_info=corr.get("incomplete_information"),
            additional_info=corr.get("additional_information"),
            affected_sections=corr.get("affected_sections", []),
            section=corr.get("section"),
            sources=corr.get("sources", []),
            narrative_comments=corr.get("narrative_shaping_comments", []),
            update_research=corr.get("update_research", False)
        ))

    return corrections


def get_correction_summary(correction: CorrectionObject) -> str:
    """
    Generate a human-readable summary of a correction.

    Args:
        correction: CorrectionObject to summarize

    Returns:
        String summary of the correction
    """
    if correction.type == "inaccurate":
        return f"Correct inaccurate info in {len(correction.affected_sections)} section(s)"
    elif correction.type == "incomplete":
        return f"Add missing info to {len(correction.affected_sections)} section(s)"
    elif correction.type == "narrative":
        return f"Improve narrative in section: {correction.section}"
    elif correction.type == "mixed":
        parts = []
        if correction.inaccurate_info:
            parts.append("correct inaccuracies")
        if correction.incomplete_info:
            parts.append("add missing info")
        if correction.narrative_comments:
            parts.append("improve narrative")
        return f"{', '.join(parts).capitalize()} in {len(correction.affected_sections)} section(s)"
    return "Unknown correction type"
