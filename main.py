import os
import logging
import sys

from rich.logging import RichHandler, Console
from typing import List

from ankigen.agents.flashcard_workflow import FlashcardGenerator, FlashcardState
from ankigen.packagers.anki_deck_packager import AnkiDeckPackager
from ankigen.models.anki_card import AnkiCard

# Configure rich logging
FORMAT = "%(message)s"
logging.basicConfig(
    level="INFO",
    format=FORMAT,
    datefmt="[%X]",
    handlers=[RichHandler(console=Console(stderr=True))]
)
log = logging.getLogger("rich")

if not os.environ.get("GOOGLE_API_KEY"):
    log.error("GOOGLE_API_KEY environment variable not set. Please set it to your Google Cloud API key.")
    exit(1)

initial_topic = "Advanced Ruby Programming"
num_cards_to_generate = 3

log.info(f"Starting flashcard generation for topic: '{initial_topic}', aiming for {num_cards_to_generate} cards.")

generator = FlashcardGenerator()
final_state: FlashcardState = generator.invoke(
    {
        "topic": initial_topic,
        "num_cards": num_cards_to_generate # Pass num_cards here
    }
)

generated_cards: List[AnkiCard] = final_state["all_generated_cards"]
if not generated_cards:
    log.warning("No flashcards were generated. Exiting.")
    exit(0)

#log.info("\n--- All Generated Flashcards (Structured Data) ---")
#for i, card_obj in enumerate(final_state["all_generated_cards"]):
    #    log.info(f"\n--- Card {i+1} (Pydantic Object) ---")
#    print(card_obj.model_dump_json(indent=2))

# --- Create and Package the Anki Deck ---
deck_name = initial_topic
deck_output_filepath = "decks/Generated Ruby Flashcards.apkg"

log.info(f"\n--- Creating Anki Deck: '{deck_name}' ---")

packager = AnkiDeckPackager(deck_name=deck_name)
packager.package_deck(generated_cards, deck_output_filepath)

log.info(f"Anki deck generation complete. File saved to: {deck_output_filepath}")
