"""
Dataclass schemas for investment memo outlines.

These schemas correspond to the YAML outline files in templates/outlines/.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any


@dataclass
class OutlineMetadata:
    """Metadata for an outline file."""
    outline_type: str  # "direct_investment" or "fund_commitment"
    version: str
    description: str
    compatible_modes: List[str]
    date_created: Optional[str] = None
    firm: Optional[str] = None  # For custom outlines
    extends: Optional[str] = None  # Path to base outline (for custom outlines)


@dataclass
class VocabularyTerm:
    """A single vocabulary term with usage guidance."""
    term: str
    first_use: Optional[str] = None
    subsequent: Optional[str] = None
    definition: Optional[str] = None
    usage: Optional[str] = None
    instead: Optional[str] = None
    reason: Optional[str] = None


@dataclass
class VocabularyCategory:
    """A category of vocabulary terms (e.g., financial, market, team)."""
    preferred: List[VocabularyTerm] = field(default_factory=list)
    avoid: List[VocabularyTerm] = field(default_factory=list)


@dataclass
class VocabularyGuide:
    """Complete vocabulary guidance for an outline."""
    categories: Dict[str, VocabularyCategory] = field(default_factory=dict)
    phrases_to_avoid: Dict[str, List[Dict[str, str]]] = field(default_factory=dict)
    style_rules: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModeSpecificGuidance:
    """Mode-specific guidance (consider vs justify)."""
    emphasis: str
    recommendation_options: Optional[List[str]] = None
    tone: Optional[str] = None
    required_elements: Optional[List[str]] = None
    required_analysis: Optional[List[str]] = None
    guiding_questions_add: Optional[List[str]] = None
    rationale_focus: Optional[str] = None


@dataclass
class SectionVocabulary:
    """Section-specific vocabulary guidance."""
    preferred_terms: List[str] = field(default_factory=list)
    required_elements: List[str] = field(default_factory=list)
    avoid: List[str] = field(default_factory=list)
    structure_template: Optional[List[str]] = None
    critical_rules: Optional[List[str]] = None
    required_format: Optional[Dict[str, str]] = None


@dataclass
class TargetLength:
    """Target length specifications for a section."""
    min_words: int
    max_words: int
    ideal_words: int


@dataclass
class SectionDefinition:
    """Definition of a single section in the memo."""
    number: int
    name: str
    filename: str
    target_length: TargetLength
    description: str
    guiding_questions: List[str]
    section_vocabulary: SectionVocabulary
    mode_specific: Dict[str, ModeSpecificGuidance]
    validation_criteria: List[str]


@dataclass
class FirmPreferences:
    """Firm-specific preferences (for custom outlines)."""
    tone: Optional[str] = None
    recommendation_philosophy: Optional[str] = None
    emphasis: Optional[List[str]] = None
    critical_questions: Optional[List[str]] = None


@dataclass
class SectionOverride:
    """Override for a specific section in a custom outline."""
    target_length: Optional[Dict[str, int]] = None
    guiding_questions_add: Optional[List[str]] = None
    emphasis: Optional[str] = None
    minimum_risks: Optional[int] = None
    weight: Optional[float] = None
    emphasis_additions: Optional[List[str]] = None


@dataclass
class OutlineDefinition:
    """Complete outline definition for generating investment memos."""
    metadata: OutlineMetadata
    vocabulary: VocabularyGuide
    sections: List[SectionDefinition]
    cross_section_requirements: Optional[Dict[str, Any]] = None
    firm_preferences: Optional[FirmPreferences] = None
    section_overrides: Optional[Dict[str, SectionOverride]] = None

    def get_section_by_number(self, number: int) -> Optional[SectionDefinition]:
        """Get a section by its number."""
        for section in self.sections:
            if section.number == number:
                return section
        return None

    def get_section_by_name(self, name: str) -> Optional[SectionDefinition]:
        """Get a section by its name."""
        for section in self.sections:
            if section.name.lower() == name.lower():
                return section
        return None

    def get_section_filenames(self) -> List[str]:
        """Get list of all section filenames in order."""
        return [section.filename for section in sorted(self.sections, key=lambda s: s.number)]
