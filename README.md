# AnkiGen: LLM-Powered Anki Flashcard Generator

AnkiGen is a command-line tool that uses LLMs to generate Anki decks on a given topic. It structures the generated content into a rich, customizable format and packages it into an Anki deck (`.apkg`) ready for import.

## Getting Started

### Prerequisites

* Python 3.9+ (or Python 3.7+ with `typing_extensions`)
* A Google API Key (for `gemini-2.0-flash` or `gemini-1.5-pro` LLMs)
* For the GUI: PyQt5 (`pip install PyQt5`)

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

Ensure `GOOGLE_API_KEY` is set as an environment variable.

## Usage

AnkiGen can be used either via its Command-Line Interface (CLI) or through its experimental Graphical User Interface (GUI).

### Command-Line Interface (CLI)

Run the `main.py` script using the `typer` CLI.

#### Generate Flashcards (CLI)

To generate an Anki deck from the command line:

```bash
python ankigen/main.py generate --topic "Advanced Ruby Metaprogramming" --num-cards 5 --template-type basic
```

##### Options:

* `--topic`, `-t`: The main topic for flashcard generation (e.g., "Machine Learning Basics").
* `--num-cards`, `-n`: The number of flashcards to generate.
* `--model`, `-m`: The LLM model name to use (default: `gemini-2.0-flash`).
* `--output`, `-o`: The filename for the generated `.apkg` file (default: `generated_flashcards.apkg`). The file will be saved in `decks/` directory.
* `--deck-name`, `-d`: The name of the Anki deck that appears in Anki (default: Generated Flashcards: [Topic]).
* `--template-type`, `-x`: The type of Anki card template to use ("basic" or "comprehensive").
* `--session-id`, `-s`: A unique ID for this generation session (for resuming). If not provided, a new one will be generated.

#### Resume Generation (CLI)

If, for example, a session crashes or is interrupted, you can resume the workflow by providing the same session ID:

```bash
python ankigen/main.py generate --topic "Advanced Ruby Metaprogramming" --session-id your_session_id_here
```

### Graphical User Interface (GUI) - Work in Progress

AnkiGen also provides a graphical interface for easier interaction, allowing you to input parameters and observe the generation process in real-time.

**Features (WIP):**
* Interactive input for topic, number of cards, and iteration parameters.
* Dropdown selection for different Anki card templates ("basic", "comprehensive").
* Real-time logging output from the generation process.
* One-click Anki deck export.

**How to Run the GUI:**

```bash
python gui_app.py
```

![AnkiGen GUI Screenshot](docs/images/gui.png)
