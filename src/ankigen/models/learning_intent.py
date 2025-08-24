from typing import List, Optional, Dict
from dataclasses import dataclass
from enum import Enum


class DifficultyLevel(Enum):
    """Standardized difficulty levels for learning content."""
    BEGINNER = "beginner"
    ELEMENTARY = "elementary" 
    INTERMEDIATE = "intermediate"
    UPPER_INTERMEDIATE = "upper_intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


class TimeConstraint(Enum):
    """Time-based learning preferences."""
    QUICK_REVIEW = "quick_review"      # 5-15 cards, essential only
    STANDARD = "standard"              # 10-30 cards, balanced coverage
    COMPREHENSIVE = "comprehensive"    # 30-100+ cards, thorough coverage
    INTENSIVE = "intensive"            # 50-200+ cards, deep learning


@dataclass
class LearningIntent:
    """Represents the user's learning intent parsed from natural language."""
    
    # Core intent
    topic: str
    raw_input: str  # Original user input for reference
    
    # Inferred parameters
    domain: Optional[str] = None
    estimated_cards: int = 10
    focus_areas: Optional[List[str]] = None  # ["vocabulary", "grammar", "concepts"]
    difficulty_level: Optional[DifficultyLevel] = None
    time_constraint: Optional[TimeConstraint] = None
    
    # Context clues
    subject_area: Optional[str] = None  # "language", "programming", "science"
    specific_skills: Optional[List[str]] = None  # ["speaking", "writing", "debugging"]
    use_case: Optional[str] = None  # "travel", "business", "academic", "hobby"
    
    # Parsing confidence
    confidence_score: float = 0.0  # 0.0 to 1.0


@dataclass
class FocusAreaBreakdown:
    """Represents how cards should be distributed across focus areas."""
    area_name: str
    card_count: int
    percentage: int
    description: str


@dataclass
class GenerationPlan:
    """Concrete plan for generating flashcards based on learning intent."""
    
    # Generation parameters
    total_cards: int
    workflow: str
    template: str
    domain: Optional[str]
    
    # Content breakdown
    breakdown: List[FocusAreaBreakdown]
    
    # Explanations for user
    reasoning: str
    confidence_explanation: str
    
    # Original intent reference
    original_intent: LearningIntent
    
    def get_breakdown_dict(self) -> Dict[str, int]:
        """Convert breakdown to simple dict format for easy consumption."""
        return {area.area_name: area.card_count for area in self.breakdown}
    
    def get_breakdown_summary(self) -> str:
        """Generate human-readable breakdown summary."""
        lines = []
        for area in self.breakdown:
            lines.append(f"• {area.area_name.title()} ({area.card_count} cards) - {area.percentage}%")
        return "\n".join(lines)


@dataclass
class ParsedComponents:
    """Intermediate representation of parsed natural language components."""
    
    # Extracted entities
    subjects: List[str] = None  # ["German", "vocabulary", "grammar"]
    levels: List[str] = None    # ["A2", "beginner", "intermediate"]
    contexts: List[str] = None  # ["travel", "business", "academic"]
    quantities: List[str] = None # ["20 cards", "quick review", "comprehensive"]
    skills: List[str] = None    # ["speaking", "listening", "writing"]
    
    # Confidence scores for each component
    subject_confidence: float = 0.0
    level_confidence: float = 0.0
    context_confidence: float = 0.0
    quantity_confidence: float = 0.0