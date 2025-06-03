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
```

##### Options:

* `--topic`, `-t`: The main topic for flashcard generation (e.g., "Machine Learning Basics").
* `--num-cards`, `-n`: The number of flashcards to generate. Max 50.
* `--model`, `-m`: The LLM model name to use (default: `gemini-2.0-flash`).
* `--output`, `-o`: The filename for the generated .apkg file (default: `generated_flashcards.apkg`). The file will be saved in `decks/` directory.
* `--deck-name`, `-d`: The name of the Anki deck that appears in Anki (default: Generated Flashcards: [Topic]).
* `--session-id`, `-s`: A unique ID for this generation sessioni (for resuming). If not provided, a new one will be generated.

#### Resume Generation

If, for example, a session crashes or is interrupted, you can resume the workflow by providing the same session ID:

```bash
python ankigen/main.py generate --topic "Erlang OTP Best Practices" --num-cards 5 --session-id "my-session-id"
```
