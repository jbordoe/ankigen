from ankigen.models.anki_card import AnkiCard
from ankigen.models.anki_card import CardMedia
from ankigen.models.anki_card import MultipleChoiceOption
from ankigen.models.anki_card import CollapsibleSection

def test_anki_card_model():
    """Test the AnkiCard model."""
    card = AnkiCard(
        type_="Vocabulary",
        topic="Math",
        subtopic="Arithmetic",
        title="Addition",
        front_question_text="What is the sum of 2 and 3?",
        front_question_context="In mathematics, the sum of two numbers is the result of adding them together.",
        front_question_hint="Try adding the numbers together.",
        front_question_example="The sum of 2 and 3 is **5**.",
        front_question_code="2 + 3",
        front_question_media=CardMedia(image="https://example.com/image.png"),
        front_question_multiple_choice=[
            MultipleChoiceOption(choice_letter="A", text="5", explanation="The sum of 2 and 3 is 5."),
            MultipleChoiceOption(choice_letter="B", text="7", explanation="The sum of 2 and 3 is 7."),
            MultipleChoiceOption(choice_letter="C", text="9", explanation="The sum of 2 and 3 is 9.")
            ],
        back_answer="5",
        back_explanation="The sum of 2 and 3 is 5.",
        back_collapsibles=[
            CollapsibleSection(title="Explanation", content="The sum of 2 and 3 is 5."),
            CollapsibleSection(title="Proof", content="2 + 3 = 5")
            ],
        back_code_solution="def add(a, b):\n    return a + b",
        back_related=["Addition", "Subtraction", "Multiplication"],
        back_mnemonics="Add two numbers together.",
        sources=["https://example.com/math/addition.html"]
    )
    assert card.type_ == "Vocabulary"
    assert card.topic == "Math"
    assert card.subtopic == "Arithmetic"
    assert card.title == "Addition"
    assert card.front_question_text == "What is the sum of 2 and 3?"
    assert card.front_question_context == "In mathematics, the sum of two numbers is the result of adding them together."
    assert card.front_question_hint == "Try adding the numbers together."
    assert card.front_question_example == "The sum of 2 and 3 is **5**."
    assert card.front_question_code == "2 + 3"
    assert card.front_question_media.image == "https://example.com/image.png"
    assert card.front_question_multiple_choice[0].choice_letter == "A"
    assert card.front_question_multiple_choice[0].text == "5"
    assert card.front_question_multiple_choice[0].explanation == "The sum of 2 and 3 is 5."
    assert card.back_answer == "5"
    assert card.back_explanation == "The sum of 2 and 3 is 5."
    assert card.back_collapsibles[0].title == "Explanation"
    assert card.back_collapsibles[0].content == "The sum of 2 and 3 is 5."
    assert card.back_collapsibles[1].title == "Proof"
    assert card.back_collapsibles[1].content == "2 + 3 = 5"
    assert card.back_code_solution == "def add(a, b):\n    return a + b"
    assert card.back_related[0] == "Addition"
    assert card.back_related[1] == "Subtraction"
    assert card.back_related[2] == "Multiplication"
    assert card.back_mnemonics == "Add two numbers together."
    assert card.sources[0] == "https://example.com/math/addition.html"

def test_card_media_model():
    """Test the CardMedia model."""
    media = CardMedia(image="https://example.com/image.png")
    assert media.image == "https://example.com/image.png"
    assert media.audio is None

def test_multiple_choice_option_model():
    """Test the MultipleChoiceOption model."""
    option = MultipleChoiceOption(choice_letter="A", text="5", explanation="The sum of 2 and 3 is 5.")
    assert option.choice_letter == "A"
    assert option.text == "5"
    assert option.explanation == "The sum of 2 and 3 is 5."

def test_collapsible_section_model():
    """Test the CollapsibleSection model."""
    section = CollapsibleSection(title="Explanation", content="The sum of 2 and 3 is 5.")
    assert section.title == "Explanation"
    assert section.content == "The sum of 2 and 3 is 5."

