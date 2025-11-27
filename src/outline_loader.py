"""
Outline loader for investment memo generation.

Loads YAML outline files and converts them to dataclass instances.
Supports custom outlines with inheritance from default outlines.
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List
from functools import lru_cache

from src.schemas.outline_schema import (
    OutlineDefinition,
    OutlineMetadata,
    VocabularyGuide,
    VocabularyCategory,
    VocabularyTerm,
    SectionDefinition,
    SectionVocabulary,
    TargetLength,
    ModeSpecificGuidance,
    FirmPreferences,
    SectionOverride,
)


# Cache loaded outlines for performance
_outline_cache: Dict[str, OutlineDefinition] = {}


def get_templates_dir() -> Path:
    """Get the templates directory path."""
    # Assuming we're in src/ and templates/ is at project root
    current_file = Path(__file__).resolve()
    project_root = current_file.parent.parent
    return project_root / "templates" / "outlines"


def load_yaml_file(file_path: Path) -> Dict[str, Any]:
    """Load a YAML file and return its contents."""
    print(f"📖 Loading outline from: {file_path.name}")

    if not file_path.exists():
        raise FileNotFoundError(f"Outline file not found: {file_path}")

    with open(file_path, 'r') as f:
        data = yaml.safe_load(f)

    return data


def parse_vocabulary_term(term_data: Dict[str, Any]) -> VocabularyTerm:
    """Parse a vocabulary term from YAML data."""
    return VocabularyTerm(
        term=term_data.get('term', ''),
        first_use=term_data.get('first_use'),
        subsequent=term_data.get('subsequent'),
        definition=term_data.get('definition'),
        usage=term_data.get('usage'),
        instead=term_data.get('instead'),
        reason=term_data.get('reason'),
    )


def parse_vocabulary_category(category_data: Dict[str, Any]) -> VocabularyCategory:
    """Parse a vocabulary category from YAML data."""
    preferred = [parse_vocabulary_term(term) for term in category_data.get('preferred', [])]
    avoid = [parse_vocabulary_term(term) for term in category_data.get('avoid', [])]

    return VocabularyCategory(preferred=preferred, avoid=avoid)


def parse_vocabulary(vocab_data: Dict[str, Any]) -> VocabularyGuide:
    """Parse vocabulary section from YAML data."""
    categories = {}
    phrases_to_avoid = {}
    style_rules = {}

    for key, value in vocab_data.items():
        if key == 'phrases_to_avoid':
            phrases_to_avoid = value
        elif key == 'style_rules':
            style_rules = value
        elif isinstance(value, dict) and ('preferred' in value or 'avoid' in value):
            # This is a vocabulary category
            categories[key] = parse_vocabulary_category(value)

    return VocabularyGuide(
        categories=categories,
        phrases_to_avoid=phrases_to_avoid,
        style_rules=style_rules,
    )


def parse_section_vocabulary(vocab_data: Dict[str, Any]) -> SectionVocabulary:
    """Parse section-specific vocabulary from YAML data."""
    return SectionVocabulary(
        preferred_terms=vocab_data.get('preferred_terms', []),
        required_elements=vocab_data.get('required_elements', []),
        avoid=vocab_data.get('avoid', []),
        structure_template=vocab_data.get('structure_template'),
        critical_rules=vocab_data.get('critical_rules'),
        required_format=vocab_data.get('required_format'),
    )


def parse_mode_specific(mode_data: Dict[str, Any]) -> ModeSpecificGuidance:
    """Parse mode-specific guidance from YAML data."""
    return ModeSpecificGuidance(
        emphasis=mode_data.get('emphasis', ''),
        recommendation_options=mode_data.get('recommendation_options'),
        tone=mode_data.get('tone'),
        required_elements=mode_data.get('required_elements'),
        required_analysis=mode_data.get('required_analysis'),
        guiding_questions_add=mode_data.get('guiding_questions_add'),
        rationale_focus=mode_data.get('rationale_focus'),
    )


def flatten_guiding_questions(questions_data: Any) -> List[str]:
    """
    Flatten guiding questions from YAML data.

    Handles both flat lists and nested dictionaries with subsections.
    Examples:
      Flat: ["Question 1", "Question 2"]
      Nested: {thesis_and_focus: ["Q1", "Q2"], right_to_win: ["Q3"]}
    """
    if isinstance(questions_data, list):
        # Already a flat list
        return questions_data
    elif isinstance(questions_data, dict):
        # Nested dict with subsections - flatten into single list
        flat_list = []
        for subsection, questions in questions_data.items():
            if isinstance(questions, list):
                flat_list.extend(questions)
            elif isinstance(questions, str):
                flat_list.append(questions)
        return flat_list
    else:
        return []


def parse_section(section_data: Dict[str, Any]) -> SectionDefinition:
    """Parse a section definition from YAML data."""
    target_length_data = section_data['target_length']
    target_length = TargetLength(
        min_words=target_length_data['min_words'],
        max_words=target_length_data['max_words'],
        ideal_words=target_length_data['ideal_words'],
    )

    section_vocab = parse_section_vocabulary(section_data.get('section_vocabulary', {}))

    mode_specific = {}
    for mode, mode_data in section_data.get('mode_specific', {}).items():
        mode_specific[mode] = parse_mode_specific(mode_data)

    # Flatten nested guiding questions into a single list
    guiding_questions = flatten_guiding_questions(section_data.get('guiding_questions', []))

    return SectionDefinition(
        number=section_data['number'],
        name=section_data['name'],
        filename=section_data['filename'],
        target_length=target_length,
        description=section_data['description'],
        guiding_questions=guiding_questions,
        section_vocabulary=section_vocab,
        mode_specific=mode_specific,
        validation_criteria=section_data.get('validation_criteria', []),
    )


def parse_outline_metadata(metadata: Dict[str, Any]) -> OutlineMetadata:
    """Parse outline metadata from YAML data."""
    return OutlineMetadata(
        outline_type=metadata['outline_type'],
        version=metadata['version'],
        description=metadata['description'],
        compatible_modes=metadata['compatible_modes'],
        date_created=metadata.get('date_created'),
        firm=metadata.get('firm'),
        extends=metadata.get('extends'),
    )


def parse_outline_data(data: Dict[str, Any]) -> OutlineDefinition:
    """Parse complete outline from YAML data."""
    metadata = parse_outline_metadata(data['metadata'])
    vocabulary = parse_vocabulary(data.get('vocabulary', {}))
    sections = [parse_section(section) for section in data['sections']]

    firm_preferences = None
    if 'firm_preferences' in data:
        fp_data = data['firm_preferences']
        firm_preferences = FirmPreferences(
            tone=fp_data.get('tone'),
            recommendation_philosophy=fp_data.get('recommendation_philosophy'),
            emphasis=fp_data.get('emphasis'),
            critical_questions=fp_data.get('critical_questions'),
        )

    section_overrides = None
    if 'section_overrides' in data:
        section_overrides = {}
        for section_name, override_data in data['section_overrides'].items():
            section_overrides[section_name] = SectionOverride(
                target_length=override_data.get('target_length'),
                guiding_questions_add=override_data.get('guiding_questions_add'),
                emphasis=override_data.get('emphasis'),
                minimum_risks=override_data.get('minimum_risks'),
                weight=override_data.get('weight'),
                emphasis_additions=override_data.get('emphasis_additions'),
            )

    return OutlineDefinition(
        metadata=metadata,
        vocabulary=vocabulary,
        sections=sections,
        cross_section_requirements=data.get('cross_section_requirements'),
        firm_preferences=firm_preferences,
        section_overrides=section_overrides,
    )


def merge_outlines(base: OutlineDefinition, custom: OutlineDefinition) -> OutlineDefinition:
    """Merge custom outline with base outline (inheritance)."""
    print(f"🔗 Merging custom outline with base: {base.metadata.outline_type}")

    # Start with base outline sections
    merged_sections = list(base.sections)

    # Apply section overrides if present
    if custom.section_overrides:
        for section in merged_sections:
            section_name_key = section.name.lower().replace(' ', '_').replace('&', '')
            if section_name_key in custom.section_overrides:
                override = custom.section_overrides[section_name_key]

                # Override target length
                if override.target_length and 'ideal_words' in override.target_length:
                    section.target_length.ideal_words = override.target_length['ideal_words']
                    print(f"  ✏️  Override {section.name}: ideal_words = {override.target_length['ideal_words']}")

                # Add guiding questions
                if override.guiding_questions_add:
                    section.guiding_questions.extend(override.guiding_questions_add)
                    print(f"  ➕ Added {len(override.guiding_questions_add)} guiding questions to {section.name}")

    # Merge vocabulary (custom additions + base)
    merged_vocab = base.vocabulary
    # TODO: Implement vocabulary merging if needed

    # Use custom firm preferences if present
    firm_preferences = custom.firm_preferences or base.firm_preferences

    return OutlineDefinition(
        metadata=custom.metadata,  # Use custom metadata
        vocabulary=merged_vocab,
        sections=merged_sections,
        cross_section_requirements=base.cross_section_requirements,
        firm_preferences=firm_preferences,
        section_overrides=custom.section_overrides,
    )


def load_outline(investment_type: str, mode: Optional[str] = None) -> OutlineDefinition:
    """
    Load default outline for the given investment type.

    Args:
        investment_type: "direct" or "fund"
        mode: Optional mode ("consider" or "justify") - not used for default outlines

    Returns:
        OutlineDefinition instance
    """
    templates_dir = get_templates_dir()

    # Map investment type to outline filename
    outline_map = {
        "direct": "direct-investment.yaml",
        "fund": "fund-commitment.yaml",
    }

    if investment_type not in outline_map:
        raise ValueError(f"Unknown investment type: {investment_type}. Must be 'direct' or 'fund'.")

    outline_file = outline_map[investment_type]
    cache_key = f"default_{investment_type}"

    # Check cache
    if cache_key in _outline_cache:
        print(f"✅ Using cached outline: {outline_file}")
        return _outline_cache[cache_key]

    # Load from file
    file_path = templates_dir / outline_file
    data = load_yaml_file(file_path)
    outline = parse_outline_data(data)

    # Cache it
    _outline_cache[cache_key] = outline

    print(f"✅ Loaded outline: {outline.metadata.outline_type} (v{outline.metadata.version})")
    print(f"   📋 {len(outline.sections)} sections defined")

    return outline


def load_custom_outline(outline_name: str, investment_type: str) -> OutlineDefinition:
    """
    Load custom outline with inheritance from base outline.

    Args:
        outline_name: Name of custom outline (e.g., "hypernova-direct-consider" or "lpcommit-emerging-manager")
        investment_type: "direct" or "fund" (for loading base outline)

    Returns:
        OutlineDefinition instance with overrides applied
    """
    templates_dir = get_templates_dir()
    custom_dir = templates_dir / "custom"

    cache_key = f"custom_{outline_name}"

    # Check cache
    if cache_key in _outline_cache:
        print(f"✅ Using cached custom outline: {outline_name}")
        return _outline_cache[cache_key]

    # Load custom outline file - check both main outlines dir and custom dir
    custom_file = custom_dir / f"{outline_name}.yaml"
    main_file = templates_dir / f"{outline_name}.yaml"

    if main_file.exists():
        custom_file = main_file
        print(f"📂 Found outline in main templates/outlines/ directory")
    elif not custom_file.exists():
        raise FileNotFoundError(
            f"Custom outline not found: {outline_name}.yaml\n"
            f"Searched in:\n"
            f"  - {main_file}\n"
            f"  - {custom_file}\n"
            f"Available outlines: {list(templates_dir.glob('*.yaml'))} + {list(custom_dir.glob('*.yaml'))}"
        )

    custom_data = load_yaml_file(custom_file)
    custom_outline = parse_outline_data(custom_data)

    # Load base outline if inheritance is specified
    if custom_outline.metadata.extends:
        print(f"🔄 Custom outline extends base outline")
        base_outline = load_outline(investment_type)
        merged = merge_outlines(base_outline, custom_outline)

        # Cache merged result
        _outline_cache[cache_key] = merged

        print(f"✅ Loaded custom outline: {outline_name} (with inheritance)")
        if merged.firm_preferences:
            print(f"   🏢 Firm: {merged.metadata.firm}")
            if merged.firm_preferences.critical_questions:
                print(f"   ❓ Critical questions: {len(merged.firm_preferences.critical_questions)}")

        return merged
    else:
        # No inheritance, just return custom outline as-is
        _outline_cache[cache_key] = custom_outline

        print(f"✅ Loaded custom outline: {outline_name} (standalone)")
        return custom_outline


def load_outline_for_state(state: Dict[str, Any]) -> OutlineDefinition:
    """
    Load appropriate outline based on state (with support for custom outlines).

    Args:
        state: MemoState dict with investment_type, memo_mode, and optionally outline_name

    Returns:
        OutlineDefinition instance
    """
    investment_type = state.get("investment_type", "direct")
    mode = state.get("memo_mode", "consider")
    custom_outline = state.get("outline_name")  # From company data or CLI

    print("\n" + "="*60)
    print("📚 LOADING MEMO OUTLINE")
    print("="*60)
    print(f"Investment Type: {investment_type}")
    print(f"Mode: {mode}")

    if custom_outline:
        print(f"Custom Outline: {custom_outline}")
        print("-"*60)
        outline = load_custom_outline(custom_outline, investment_type)
    else:
        print("Using: Default outline")
        print("-"*60)
        outline = load_outline(investment_type, mode)

    print("="*60 + "\n")

    return outline


# For backwards compatibility
@lru_cache(maxsize=8)
def get_outline(investment_type: str) -> OutlineDefinition:
    """Get outline (cached). Simple wrapper for load_outline."""
    return load_outline(investment_type)
