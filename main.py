import os
import logging
from rich.logging import RichHandler

from ankigen.agents.flashcard_workflow import FlashcardGenerator, FlashcardState

# Configure rich logging
FORMAT = "%(message)s"
logging.basicConfig(
    level="INFO", format=FORMAT, datefmt="[%X]", handlers=[RichHandler()]
)
log = logging.getLogger("rich")

if not os.environ.get("GOOGLE_API_KEY"):
    log.error("GOOGLE_API_KEY environment variable not set. Please set it to your Google Cloud API key.")
    exit(1)

# --- Initialize and Run the Flashcard Generator ---
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

log.info("\n--- All Generated Flashcards (Structured Data) ---")
for i, card_obj in enumerate(final_state["all_generated_cards"]):
    log.info(f"\n--- Card {i+1} (Pydantic Object) ---")
    print(card_obj.model_dump_json(indent=2))
