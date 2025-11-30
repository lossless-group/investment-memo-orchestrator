"""
Scorecard loader for investment evaluation.

Loads YAML scorecard definitions and provides scoring rubrics for
dimension-based evaluation (e.g., 12Ps framework).
"""

import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field


@dataclass
class ScoringScale:
    """Scoring scale definition."""
    min: int
    max: int
    labels: Dict[int, str]


@dataclass
class PercentileMapping:
    """Maps scores to percentile descriptions."""
    mapping: Dict[int, str]


@dataclass
class EvaluationGuidance:
    """Guidance for evaluating a dimension."""
    questions: List[str] = field(default_factory=list)
    evidence_sources: List[str] = field(default_factory=list)
    red_flags: List[str] = field(default_factory=list)


@dataclass
class ScoringRubric:
    """Rubric for scoring a dimension (1-5 scale)."""
    levels: Dict[int, str]  # score -> description


@dataclass
class DimensionDefinition:
    """Definition of a single scorecard dimension."""
    name: str
    group: str
    number: int
    short_description: str
    full_description: str
    evaluation_guidance: EvaluationGuidance
    scoring_rubric: ScoringRubric


@dataclass
class DimensionGroup:
    """Group of related dimensions."""
    group_id: str
    name: str
    description: str
    dimensions: List[str]  # dimension IDs
    placement: Dict[str, str]  # section, position
    synthesis_of: Optional[List[str]] = None  # for synthesis groups


@dataclass
class ScorecardMetadata:
    """Scorecard metadata."""
    scorecard_id: str
    name: str
    description: str
    version: str
    firm: str
    applicable_types: List[str]
    applicable_modes: List[str]
    date_created: str


@dataclass
class ScorecardDefinition:
    """Complete scorecard definition."""
    metadata: ScorecardMetadata
    scoring: Dict[str, Any]  # scale and percentile mapping
    dimension_groups: List[DimensionGroup]
    dimensions: Dict[str, DimensionDefinition]
    output_format: Dict[str, Any]
    agent_context: Dict[str, Any]


# Cache for loaded scorecards
_scorecard_cache: Dict[str, ScorecardDefinition] = {}


def get_scorecards_dir() -> Path:
    """Get the scorecards directory path."""
    current_file = Path(__file__).resolve()
    project_root = current_file.parent.parent
    return project_root / "templates" / "scorecards"


def load_yaml_file(file_path: Path) -> Dict[str, Any]:
    """Load a YAML file and return its contents."""
    if not file_path.exists():
        raise FileNotFoundError(f"Scorecard file not found: {file_path}")

    with open(file_path, 'r') as f:
        data = yaml.safe_load(f)

    return data


def parse_evaluation_guidance(data: Dict[str, Any]) -> EvaluationGuidance:
    """Parse evaluation guidance from YAML data."""
    return EvaluationGuidance(
        questions=data.get('questions', []),
        evidence_sources=data.get('evidence_sources', []),
        red_flags=data.get('red_flags', [])
    )


def parse_scoring_rubric(data: Dict[str, str]) -> ScoringRubric:
    """Parse scoring rubric from YAML data."""
    # Convert string keys to int
    levels = {int(k): v for k, v in data.items()}
    return ScoringRubric(levels=levels)


def parse_dimension(dim_id: str, data: Dict[str, Any]) -> DimensionDefinition:
    """Parse a dimension definition from YAML data."""
    return DimensionDefinition(
        name=data['name'],
        group=data['group'],
        number=data['number'],
        short_description=data['short_description'],
        full_description=data['full_description'],
        evaluation_guidance=parse_evaluation_guidance(data.get('evaluation_guidance', {})),
        scoring_rubric=parse_scoring_rubric(data.get('scoring_rubric', {}))
    )


def parse_dimension_group(data: Dict[str, Any]) -> DimensionGroup:
    """Parse a dimension group from YAML data."""
    return DimensionGroup(
        group_id=data['group_id'],
        name=data['name'],
        description=data['description'],
        dimensions=data.get('dimensions', []),
        placement=data.get('placement', {}),
        synthesis_of=data.get('synthesis_of')
    )


def parse_metadata(data: Dict[str, Any]) -> ScorecardMetadata:
    """Parse scorecard metadata from YAML data."""
    return ScorecardMetadata(
        scorecard_id=data['scorecard_id'],
        name=data['name'],
        description=data['description'],
        version=data['version'],
        firm=data['firm'],
        applicable_types=data['applicable_types'],
        applicable_modes=data['applicable_modes'],
        date_created=data['date_created']
    )


def parse_scorecard_data(data: Dict[str, Any]) -> ScorecardDefinition:
    """Parse complete scorecard from YAML data."""
    metadata = parse_metadata(data['metadata'])

    dimension_groups = [
        parse_dimension_group(group)
        for group in data.get('dimension_groups', [])
    ]

    dimensions = {
        dim_id: parse_dimension(dim_id, dim_data)
        for dim_id, dim_data in data.get('dimensions', {}).items()
    }

    return ScorecardDefinition(
        metadata=metadata,
        scoring=data.get('scoring', {}),
        dimension_groups=dimension_groups,
        dimensions=dimensions,
        output_format=data.get('output_format', {}),
        agent_context=data.get('agent_context', {})
    )


def find_scorecard_file(scorecard_name: str) -> Path:
    """
    Find scorecard file by name.

    Searches in:
    1. templates/scorecards/{scorecard_name}/{scorecard_name}.yaml
    2. templates/scorecards/{type}/{scorecard_name}.yaml (for type-specific)
    """
    scorecards_dir = get_scorecards_dir()

    # Try direct match in subdirectory
    # e.g., "hypernova-early-stage-12Ps" -> "direct-early-stage-12Ps/hypernova-early-stage-12Ps.yaml"
    for subdir in scorecards_dir.iterdir():
        if subdir.is_dir():
            potential_file = subdir / f"{scorecard_name}.yaml"
            if potential_file.exists():
                return potential_file

    # Try matching directory name pattern
    # e.g., "hypernova-early-stage-12Ps" might be in "direct-early-stage-12Ps/"
    for subdir in scorecards_dir.iterdir():
        if subdir.is_dir():
            # Check all YAML files in directory
            for yaml_file in subdir.glob("*.yaml"):
                if scorecard_name in yaml_file.stem:
                    return yaml_file

    raise FileNotFoundError(
        f"Scorecard not found: {scorecard_name}\n"
        f"Searched in: {scorecards_dir}\n"
        f"Available: {list(scorecards_dir.glob('*/*.yaml'))}"
    )


def load_scorecard(scorecard_name: str) -> ScorecardDefinition:
    """
    Load scorecard by name.

    Args:
        scorecard_name: Name of the scorecard (e.g., "hypernova-early-stage-12Ps")

    Returns:
        ScorecardDefinition instance
    """
    # Check cache
    if scorecard_name in _scorecard_cache:
        print(f"✅ Using cached scorecard: {scorecard_name}")
        return _scorecard_cache[scorecard_name]

    # Find and load file
    file_path = find_scorecard_file(scorecard_name)
    print(f"📊 Loading scorecard from: {file_path.name}")

    data = load_yaml_file(file_path)
    scorecard = parse_scorecard_data(data)

    # Cache it
    _scorecard_cache[scorecard_name] = scorecard

    print(f"✅ Loaded scorecard: {scorecard.metadata.name} (v{scorecard.metadata.version})")
    print(f"   📋 {len(scorecard.dimensions)} dimensions in {len(scorecard.dimension_groups)} groups")

    return scorecard


def get_dimension_rubric(scorecard: ScorecardDefinition, dimension_id: str) -> Dict[int, str]:
    """
    Get scoring rubric for a specific dimension.

    Args:
        scorecard: Loaded scorecard definition
        dimension_id: Dimension identifier (e.g., "persona", "pain")

    Returns:
        Dict mapping score (1-5) to rubric description
    """
    if dimension_id not in scorecard.dimensions:
        raise ValueError(f"Unknown dimension: {dimension_id}")

    return scorecard.dimensions[dimension_id].scoring_rubric.levels


def get_dimension_guidance(scorecard: ScorecardDefinition, dimension_id: str) -> EvaluationGuidance:
    """
    Get evaluation guidance for a specific dimension.

    Args:
        scorecard: Loaded scorecard definition
        dimension_id: Dimension identifier

    Returns:
        EvaluationGuidance with questions, evidence sources, red flags
    """
    if dimension_id not in scorecard.dimensions:
        raise ValueError(f"Unknown dimension: {dimension_id}")

    return scorecard.dimensions[dimension_id].evaluation_guidance


def get_group_dimensions(scorecard: ScorecardDefinition, group_id: str) -> List[DimensionDefinition]:
    """
    Get all dimensions in a group.

    Args:
        scorecard: Loaded scorecard definition
        group_id: Group identifier (e.g., "origins", "opening")

    Returns:
        List of DimensionDefinition objects
    """
    for group in scorecard.dimension_groups:
        if group.group_id == group_id:
            return [
                scorecard.dimensions[dim_id]
                for dim_id in group.dimensions
                if dim_id in scorecard.dimensions
            ]

    raise ValueError(f"Unknown group: {group_id}")


def get_percentile_label(scorecard: ScorecardDefinition, score: int) -> str:
    """
    Get percentile label for a score.

    Args:
        scorecard: Loaded scorecard definition
        score: Score value (1-5)

    Returns:
        Percentile label (e.g., "Top 5%", "Top 10-25%")
    """
    percentile_mapping = scorecard.scoring.get('percentile_mapping', {})
    return percentile_mapping.get(score, f"Score {score}")


def get_score_label(scorecard: ScorecardDefinition, score: int) -> str:
    """
    Get descriptive label for a score.

    Args:
        scorecard: Loaded scorecard definition
        score: Score value (1-5)

    Returns:
        Score label (e.g., "Exceptional", "Above Average")
    """
    scale = scorecard.scoring.get('scale', {})
    labels = scale.get('labels', {})
    return labels.get(score, f"Score {score}")


def load_scorecard_for_state(state: Dict[str, Any]) -> Optional[ScorecardDefinition]:
    """
    Load scorecard based on state configuration.

    Args:
        state: MemoState dict with optional scorecard_name

    Returns:
        ScorecardDefinition if scorecard specified, None otherwise
    """
    scorecard_name = state.get("scorecard_name")

    if not scorecard_name:
        return None

    print("\n" + "="*60)
    print("📊 LOADING SCORECARD")
    print("="*60)
    print(f"Scorecard: {scorecard_name}")
    print("-"*60)

    scorecard = load_scorecard(scorecard_name)

    print("="*60 + "\n")

    return scorecard
