import os
import logging
import sys
import typer
from typing_extensions import Annotated
import uuid

from rich.logging import RichHandler, Console
from typing import List

from ankigen.agents.flashcard_workflow import FlashcardGenerator, FlashcardState
from ankigen.agents.iterative_flashcard_workflow import IterativeFlashcardGenerator, IterativeFlashcardState
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

app = typer.Typer(
    help="Generate Anki flashcards from a given topic using an LLM.",
    pretty_exceptions_show_locals=False # Hide locals in tracebacks for cleaner output
)

@app.command()
def generate(
    topic: Annotated[
        str,
        typer.Option(
            "--topic", "-t",
            help="The main topic for which to generate flashcards.",
            prompt="Please enter the topic for flashcard generation"
        )
    ],
    num_cards: Annotated[
        int,
        typer.Option(
            "--num-cards", "-n",
            help="The number of flashcards to generate for the topic.",
            min=1,
            max=50 # Set a reasonable max to prevent excessive LLM calls
        )
    ],
    model_name: Annotated[
        str,
        typer.Option(
            "--model", "-m",
            help="The LLM model name to use (e.g., 'gemini-2.0-flash', 'gemini-1.5-pro').",
            show_default=True
        )
    ] = "gemini-2.0-flash", # Default LLM model
    output_filename: Annotated[
        str,
        typer.Option(
            "--output", "-o",
            help="The filename for the generated Anki deck (.apkg).",
            show_default=True
        )
    ] = "generated_flashcards.apkg",
    deck_name: Annotated[
        str,
        typer.Option(
            "--deck-name", "-d",
            help="The name of the Anki deck inside Anki. Defaults to 'Generated Flashcards: [Topic]'.",
            show_default=False
        )
    ] = None, # Will be set based on topic if not provided
   session_id: Annotated[
        str,
        typer.Option(
            "--session-id", "-s",
            help="Unique ID for this generation session (for resuming). If not provided, a new one is generated.",
            show_default=False
        )
    ] = None,
):
    """
    Generates a new Anki deck with flashcards for a specified topic.
    """
    if not os.environ.get("GOOGLE_API_KEY"):
        log.error("GOOGLE_API_KEY environment variable not set. Please set it to your Google Cloud API key.")
        raise typer.Exit(code=1)

    if deck_name is None:
        deck_name = f"Generated Flashcards: {topic}"

    # Generate a new session ID if not provided
    if session_id is None:
        session_id = str(uuid.uuid4())
        log.info(f"No session ID provided. Generating new session ID: {session_id}")
    else:
        log.info(f"Using provided session ID: {session_id} (Attempting to resume workflow)")

    log.info(f"Starting flashcard generation for topic: '{topic}', aiming for {num_cards} cards using model: '{model_name}'.")

#    generator = FlashcardGenerator(llm_model_name=model_name)
#    final_state: FlashcardState = generator.invoke(
#        {
#            "topic": topic,
#            "num_cards": num_cards
#        },
#        session_id=session_id
#    )
    generator = IterativeFlashcardGenerator(llm_model_name=model_name)
    final_state: IterativeFlashcardState = generator.invoke(
        {
            "topic": topic,
            "max_cards": num_cards,
            "max_iterations": 5,
            "cards_per_iteration": 5
        },
        session_id=session_id
    )

    generated_cards: List[AnkiCard] = final_state["all_generated_cards"]
    if not generated_cards:
        log.warning("No flashcards were generated. Exiting.")
        raise typer.Exit(code=1)

#log.info("\n--- All Generated Flashcards (Structured Data) ---")
#for i, card_obj in enumerate(final_state["all_generated_cards"]):
        #    log.info(f"\n--- Card {i+1} (Pydantic Object) ---")
#    print(card_obj.model_dump_json(indent=2))

# --- Create and Package the Anki Deck ---
    deck_name = topic
    deck_output_filepath = os.path.join("decks", output_filename)

    log.info(f"\n--- Creating Anki Deck: '{deck_name}' ---")

    packager = AnkiDeckPackager(deck_name=deck_name)
    packager.package_deck(generated_cards, deck_output_filepath)

    log.info(f"Anki deck generation complete. File saved to: {deck_output_filepath}")

if __name__ == "__main__":
    app()
