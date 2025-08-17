from typing import List, Optional
from pydantic import BaseModel, Field

class CardMedia(BaseModel):
    """Represents media elements (image/audio) on the card."""
    image: Optional[str] = Field(None, description="Link to an image file.")
    audio: Optional[str] = Field(None, description="Link to an audio file.")

class MultipleChoiceOption(BaseModel):
    """Represents a single multiple choice option with its explanation."""
    choice_letter: str = Field(description="The letter of the choice (e.g., 'A', 'B').")
    text: str = Field(description="The text of the multiple choice option.")
    explanation: Optional[str] = Field(None, description="An optional explanation for this choice.")

class CollapsibleSection(BaseModel):
    """Represents a collapsible section with a title and content."""
    title: str = Field(description="The title of the collapsible section.")
    content: str = Field(description="The content within the collapsible section.")

class AnkiCard(BaseModel):
    """
    Represents the full structure of an Anki flashcard, designed to match the provided template.
    All fields are optional by default, except for 'front_question_text' and 'back_answer' which are crucial.
    """
    # Card Metadata
    card_type: Optional[str] = Field(None, description="The type of card (e.g., Vocabulary, Concept, Code Snippet, Scenario).")
    topic: Optional[str] = Field(None, description="The main topic this card belongs to.")
    subtopic: Optional[str] = Field(None, description="A more specific subtopic within the main topic.")
    title: Optional[str] = Field(None, description="A unique, descriptive title for this card.")
    difficulty: Optional[str] = Field(None, description="The difficulty level of the card (e.g., easy, medium, hard).")
    tags: Optional[List[str]] = Field(None, description="A list of tags for this card.")

    # Front of the Card (Question Section)
    front_question_text: str = Field(description="The main question text for the front of the card.")
    front_question_context: Optional[str] = Field(None, description="When or where the question is relevant.")
    front_question_hint: Optional[str] = Field(None, description="A helpful clue for the question.")
    front_question_example: Optional[str] = Field(None, description='An example like "Das ist ein **Haus**." or `User.find(id)`.')
    front_question_code: Optional[str] = Field(None, description="Code to analyze or complete for the question.")
    front_question_media: Optional[CardMedia] = Field(None, description="Optional image or audio links for the question.")
    front_question_multiple_choice: Optional[List[MultipleChoiceOption]] = Field(None, description="List of multiple choice options.")

    # Back of the Card (Answer Section)
    back_answer: str = Field(description="The concise correct answer for the back of the card.")
    back_explanation: Optional[str] = Field(None, description="Clarification or deeper reasoning for the answer.")
    back_collapsibles: Optional[List[CollapsibleSection]] = Field(None, description="List of additional collapsible content sections.")
    back_code_solution: Optional[str] = Field(None, description="Complete or correct code snippet for the answer.")
    back_related: Optional[List[str]] = Field(None, description="List of related concepts.")
    back_mnemonics: Optional[str] = Field(None, description="A memory aid or trick.")

    # Card Sources
    sources: Optional[List[str]] = Field(None, description="List of sources for the card content.")
