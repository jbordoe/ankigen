import os
import logging
import genanki
import random
from typing import List

from ankigen.models.anki_card import AnkiCard
from ankigen.utils.template_manager import render_anki_card_to_html # Import the HTML renderer

log = logging.getLogger("rich")

class AnkiDeckPackager:
    """
    A class to create an Anki deck (.apkg file) from a list of AnkiCard Pydantic objects.
    It renders the cards to HTML using the template_manager and packages them.
    """

    # Unique IDs for your Anki Model and Deck.
    # Keep them consistent for production if you want to update existing models/decks.
    # Use random numbers for development if a new model/deck is desired every time.
    MY_MODEL_ID = 1607392314 + random.randrange(1000000000)
    MY_DECK_ID = 2059400110 + random.randrange(1000000000)

    DEFAULT_ANKI_MODEL_NAME = 'Custom Flashcard Model'
    DEFAULT_ANKI_DECK_NAME = 'Generated Flashcards'
    DEFAULT_TEMPLATE = 'basic'

    ANKI_CSS = """
        /* Basic styling for Anki cards */
        .card {
            font-family: sans-serif;
            font-size: 20px;
            text-align: center;
            color: white;
            background-color: black;
        }
        /* Add any specific Anki styling here if needed,
           but most styling is handled by pico.css and highlight.js in the HTML templates. */
    """

    def __init__(
            self,
            model_id: int = None,
            deck_id: int = None,
            deck_name: str = None,
            template: str = None
    ):
        """
        Initializes the AnkiDeckPackager with optional custom IDs and deck name.
        """
        self.model_id = model_id if model_id is not None else self.MY_MODEL_ID
        self.deck_id = deck_id if deck_id is not None else self.MY_DECK_ID
        self.deck_name = deck_name if deck_name is not None else self.DEFAULT_ANKI_DECK_NAME
        self.template = template if template is not None else self.DEFAULT_TEMPLATE
        self.css = '' if self.template == 'basic' else self.ANKI_CSS

        self._anki_model = self._define_anki_model()
        self._anki_deck = self._define_anki_deck()

    def _define_anki_model(self) -> genanki.Model:
        """
        Defines the Anki Model (card structure and templates).
        """
        return genanki.Model(
            self.model_id,
            self.DEFAULT_ANKI_MODEL_NAME,
            fields=[
                {'name': 'Front'},
                {'name': 'Back'},
            ],
            templates=[
                {
                    'name': 'Card 1',
                    'qfmt': '{{Front}}',
                    'afmt': '{{Back}}',
                },
            ],
            css=self.css
        )

    def _define_anki_deck(self) -> genanki.Deck:
        """
        Defines the Anki Deck (the container for notes).
        """
        return genanki.Deck(
            self.deck_id,
            self.deck_name
        )

    def add_card_to_deck(self, card_obj: AnkiCard) -> None:
        """
        Renders an AnkiCard object to HTML and adds it as a note to the Anki deck.
        """
        front_html = render_anki_card_to_html(card_obj, "front", template=self.template)
        back_html = render_anki_card_to_html(card_obj, "back", template=self.template)

        if not front_html or not back_html:
            log.warning(f"Skipping card due to rendering error for '{card_obj.title or card_obj.front_question_text}'")
            return

        my_note = genanki.Note(
            model=self._anki_model,
            fields=[front_html, back_html]
        )
        self._anki_deck.add_note(my_note)

    def package_deck(self, cards: List[AnkiCard], output_filepath: str) -> None:
        """
        Processes a list of AnkiCard objects, adds them to the deck,
        and saves the deck to an .apkg file.

        Args:
            cards (List[AnkiCard]): A list of AnkiCard Pydantic objects.
            output_filepath (str): The full path including filename for the .apkg file.
        """
        log.info(f"Processing {len(cards)} cards for Anki deck '{self.deck_name}'...")

        # Create output directory if it doesn't exist
        output_dir = os.path.dirname(output_filepath)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
            log.info(f"Created output directory: {output_dir}")

        # Add each card to the deck
        for i, card_obj in enumerate(cards):
            self.add_card_to_deck(card_obj)
            log.debug(f"Added card {i+1}: '{card_obj.title or card_obj.front_question_text}'")

        # Package the Deck
        log.info(f"Packaging Anki deck to: {output_filepath}")
        genanki.Package(self._anki_deck).write_to_file(output_filepath)

        log.info(f"Anki deck '{self.deck_name}' created successfully at {output_filepath}")
