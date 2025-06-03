# AnkiGen: LLM-Powered Anki Flashcard Generator

AnkiGen is a command-line tool that uses LLMs to generate Anki decks on a given topic. It structures the generated content into a rich, customizable format and packages it into an Anki deck (`.apkg`) ready for import.

## Getting Started

### Prerequisites

* Python 3.9+ (or Python 3.7+ with `typing_extensions`)
* A Google API Key (for `gemini-2.0-flash` or `gemini-1.5-pro` LLMs)

### Installation

1.  `git clone`...
2.  Ensure [`uv`](https://github.com/astral-sh/uv) is installed
3.  Create a virtual environment and install dependencies:
    ```bash
    uv venv           # Creates a .venv directory
    source .venv/bin/activate # On Windows: .venv\Scripts\activate
    uv sync           # Installs dependencies from pyproject.toml
    ```

### Configuration

Ensure `GOOGLE_API_KEY` is set

### Usage

Run the `main.py` script using the `typer` CLI.

#### Generate Flashcards

To generate an Anki deck:

```bash
python ankigen/main.py generate --topic "Advanced Ruby Metaprogramming" --num-cards 5