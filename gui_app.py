import sys
import logging

from typing import List
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QComboBox, QSpinBox,
    QFileDialog, QMessageBox
)
from PyQt5.QtCore import QThread, pyqtSignal # For threading

from ankigen.agents.iterative_flashcard_workflow import IterativeFlashcardGenerator, IterativeFlashcardState
from ankigen.models.anki_card import AnkiCard
from ankigen.packagers.anki_deck_packager import AnkiDeckPackager

class QTextEditLogger(logging.Handler):
    """
    A custom logging handler that redirects log records to a QTextEdit widget.
    """
    def __init__(self, parent_text_edit):
        super().__init__()
        self.widget = parent_text_edit
        self.widget.setReadOnly(True)
        self.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

    def emit(self, record):
        msg = self.format(record)
        self.widget.append(msg)

# --- Worker Thread for Flashcard Generation ---
# This class will encapsulate the long-running LLM calls
class FlashcardGeneratorWorker(QThread):
    """
    Worker thread to run the IterativeFlashcardGenerator workflow.
    Emits signals for progress updates and completion.
    """
    finished = pyqtSignal(object) # Emits the final state on completion
    error = pyqtSignal(str)       # Emits error messages
    log_message = pyqtSignal(str) # Emits log messages from the generator

    def __init__(self, topic: str, max_cards: int, cards_per_iteration: int, max_iterations: int):
        super().__init__()
        self.topic = topic
        self.max_cards = max_cards
        self.cards_per_iteration = cards_per_iteration
        self.max_iterations = max_iterations
        self._is_running = True

    def run(self):
        try:
            # Initialize the generator (you might want to pass llm_model_name here)
            generator = IterativeFlashcardGenerator()

            # Set up a logger that emits signals to the GUI
            # This is a bit tricky with existing rich logger, but we can add another handler
            # Or, modify the IterativeFlashcardGenerator to take a logger instance.
            # For simplicity for now, we'll assume the main rich logger.
            # A more robust solution involves modifying generator to accept log handler or emit its own signals.
            # For now, we'll rely on the main app's logging setup.

            initial_state = IterativeFlashcardState(
                topic=self.topic,
                max_cards=self.max_cards,
                cards_per_iteration=self.cards_per_iteration,
                max_iterations=self.max_iterations,
                all_generated_cards=[], # Initial empty lists
                recent_concepts=[],
                llm_completion_status="",
                iteration_count=0,
                overall_process_complete=False
            )

            # Invoke the workflow - THIS IS THE LONG-RUNNING CALL
            # You can add a session_id here if you implement checkpointing in GUI
            final_state = generator.invoke(initial_state)

            if self._is_running: # Only emit finished if not stopped prematurely
                self.finished.emit(final_state)
        except Exception as e:
            self.error.emit(f"Generation error: {e}")
        finally:
            self.log_message.emit("Flashcard generation thread finished.")

    def stop(self):
        self._is_running = False
        # You might need to add logic within IterativeFlashcardGenerator to check this flag
        # and gracefully exit its LangGraph workflow. This is more advanced.


class FlashcardApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Flashcard Generator GUI")
        self.setGeometry(100, 100, 800, 700) # x, y, width, height

        self.current_generated_cards: List[AnkiCard] = [] # Store generated cards
        self.generator_thread = None # Placeholder for the worker thread

        self._init_ui()
        self._setup_logging()

    def _init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # --- Input Section ---
        input_layout = QHBoxLayout()
        main_layout.addLayout(input_layout)

        # Left Column for Inputs
        left_input_col = QVBoxLayout()
        input_layout.addLayout(left_input_col)

        # Topic Input
        left_input_col.addWidget(QLabel("Topic:"))
        self.topic_input = QLineEdit("Python Decorators")
        left_input_col.addWidget(self.topic_input)

        # Max Cards
        left_input_col.addWidget(QLabel("Max Cards:"))
        self.max_cards_spinbox = QSpinBox()
        self.max_cards_spinbox.setRange(1, 1000)
        self.max_cards_spinbox.setValue(10) # Default
        left_input_col.addWidget(self.max_cards_spinbox)

        # Cards Per Iteration
        left_input_col.addWidget(QLabel("Cards Per Iteration:"))
        self.cards_per_iteration_spinbox = QSpinBox()
        self.cards_per_iteration_spinbox.setRange(1, 20)
        self.cards_per_iteration_spinbox.setValue(3) # Default
        left_input_col.addWidget(self.cards_per_iteration_spinbox)

        # Right Column for Inputs
        right_input_col = QVBoxLayout()
        input_layout.addLayout(right_input_col)

        # Max Iterations
        right_input_col.addWidget(QLabel("Max Iterations:"))
        self.max_iterations_spinbox = QSpinBox()
        self.max_iterations_spinbox.setRange(1, 100)
        self.max_iterations_spinbox.setValue(5) # Default
        right_input_col.addWidget(self.max_iterations_spinbox)

        # Template Type Dropdown
        right_input_col.addWidget(QLabel("Template Type:"))
        self.template_type_dropdown = QComboBox()
        self.template_type_dropdown.addItem("comprehensive")
        self.template_type_dropdown.addItem("basic")
        self.template_type_dropdown.setCurrentText("basic") # Set basic as default for testing
        right_input_col.addWidget(self.template_type_dropdown)

        # Placeholder for Session ID/Checkpointing (future)
        right_input_col.addWidget(QLabel("Session ID (Optional):"))
        self.session_id_input = QLineEdit("")
        self.session_id_input.setPlaceholderText("Leave empty for new session")
        right_input_col.addWidget(self.session_id_input)


        # Spacer to push elements to top
        left_input_col.addStretch(1)
        right_input_col.addStretch(1)


        # --- Control Buttons ---
        button_layout = QHBoxLayout()
        main_layout.addLayout(button_layout)

        self.generate_button = QPushButton("Generate Flashcards")
        self.generate_button.clicked.connect(self._start_generation)
        button_layout.addWidget(self.generate_button)

        self.export_button = QPushButton("Export Deck (.apkg)")
        self.export_button.clicked.connect(self._export_deck)
        self.export_button.setEnabled(False) # Disabled until cards are generated
        button_layout.addWidget(self.export_button)

        self.stop_button = QPushButton("Stop Generation")
        self.stop_button.clicked.connect(self._stop_generation)
        self.stop_button.setEnabled(False) # Disabled until generation starts
        button_layout.addWidget(self.stop_button)


        # --- Output Log ---
        main_layout.addWidget(QLabel("Generation Log:"))
        self.log_output = QTextEdit()
        main_layout.addWidget(self.log_output)

        # --- Card Preview (placeholder for now) ---
        # main_layout.addWidget(QLabel("Generated Card Preview:"))
        # self.card_preview_list = QListWidget() # Or a QTextEdit if displaying HTML
        # main_layout.addWidget(self.card_preview_list)


    def _setup_logging(self):
        # Remove existing rich handler from the root logger if it's there,
        # to avoid duplicate output to console.
        root_logger = logging.getLogger()
        for handler in list(root_logger.handlers):
            # Check if it's the rich handler that might be present from the CLI setup
            if isinstance(handler, logging.StreamHandler) and hasattr(handler, 'console'):
                root_logger.removeHandler(handler)

        # Set base logging level (e.g., INFO, DEBUG)
        root_logger.setLevel(logging.INFO)

        # Add our custom QTextEditLogger
        gui_handler = QTextEditLogger(self.log_output)
        gui_handler.setLevel(logging.INFO) # Or DEBUG for more verbosity
        root_logger.addHandler(gui_handler)

        log.info("GUI application started and logging initialized.")


    def _start_generation(self):
        """
        Starts the flashcard generation in a separate thread.
        """
        if self.generator_thread and self.generator_thread.isRunning():
            QMessageBox.warning(self, "Generation in Progress", "Flashcard generation is already running.")
            return

        # Clear previous cards and log
        self.current_generated_cards = []
        self.log_output.clear()
        self.export_button.setEnabled(False)
        self.generate_button.setEnabled(False)
        self.stop_button.setEnabled(True)

        topic = self.topic_input.text()
        max_cards = self.max_cards_spinbox.value()
        cards_per_iteration = self.cards_per_iteration_spinbox.value()
        max_iterations = self.max_iterations_spinbox.value()
        # template_type is used by the AnkiDeckPackager, not directly by the generator's invoke()
        #TODO: We'll need to pass it to the packager later.

        if not topic.strip():
            QMessageBox.warning(self, "Input Error", "Please enter a topic.")
            self.generate_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            return

        log.info(f"Starting generation for topic: '{topic}'")
        log.info(f"Max Cards: {max_cards}, Cards/Iteration: {cards_per_iteration}, Max Iterations: {max_iterations}")

        # Instantiate and start the worker thread
        self.generator_thread = FlashcardGeneratorWorker(
            topic=topic,
            max_cards=max_cards,
            cards_per_iteration=cards_per_iteration,
            max_iterations=max_iterations
        )
        self.generator_thread.finished.connect(self._generation_finished)
        self.generator_thread.error.connect(self._generation_error)
        # Connect log_message signal from worker to update GUI log
        self.generator_thread.log_message.connect(self.log_output.append)
        self.generator_thread.start() # This calls the run() method in the thread


    def _generation_finished(self, final_state: IterativeFlashcardState):
        """
        Callback when the generation thread finishes.
        """
        log.info("Flashcard generation complete!")
        self.current_generated_cards = final_state['all_generated_cards']
        log.info(f"Total cards generated: {len(self.current_generated_cards)}")

        self.generate_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        if self.current_generated_cards:
            self.export_button.setEnabled(True)
        else:
            QMessageBox.information(self, "Generation Complete", "No cards were generated.")


    def _generation_error(self, error_message: str):
        """
        Callback when an error occurs in the generation thread.
        """
        log.error(f"Generation error: {error_message}")
        QMessageBox.critical(self, "Generation Error", error_message)
        self.generate_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.export_button.setEnabled(False)


    def _stop_generation(self):
        """
        Attempts to stop the generation thread.
        Note: Actual graceful stopping depends on the LangGraph workflow's internal logic.
        """
        if self.generator_thread and self.generator_thread.isRunning():
            self.generator_thread.stop() # Set the flag in the worker
            self.generator_thread.wait(5000) # Wait up to 5 seconds for it to finish gracefully
            if self.generator_thread.isRunning():
                self.generator_thread.terminate() # Force terminate if it doesn't stop
                log.warning("Flashcard generation thread forcibly terminated.")
            log.info("Flashcard generation stopped.")
        self.generate_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.export_button.setEnabled(False) # Assume incomplete generation cannot be exported


    def _export_deck(self):
        """
        Prompts the user for a save location and packages the generated cards into an Anki deck.
        """
        if not self.current_generated_cards:
            QMessageBox.warning(self, "No Cards", "No cards have been generated yet to export.")
            return

        # Get the selected template type from the dropdown
        selected_template_type = self.template_type_dropdown.currentText()

        # Prompt user for save file path
        # Default filename could be based on topic and template type
        default_filename = f"{self.topic_input.text().replace(' ', '_').replace('.', '')}_{selected_template_type}_flashcards.apkg"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Anki Deck",
            default_filename, # Default path and filename
            "Anki Deck (*.apkg);;All Files (*)"
        )

        if file_path:
            try:
                # Instantiate AnkiDeckPackager with the selected template type
                packager = AnkiDeckPackager(
                    deck_name=f"{self.topic_input.text()} ({selected_template_type})",
                    template_type=selected_template_type
                )
                packager.package_deck(self.current_generated_cards, file_path)
                QMessageBox.information(self, "Export Successful", f"Anki deck saved to:\n{file_path}")
                log.info(f"Anki deck saved to: {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Failed to export Anki deck: {e}")
                log.error(f"Failed to export Anki deck: {e}")


if __name__ == "__main__":
    # Configure the root logger
    # This must be done BEFORE QApplication is created to ensure logging setup
    # is consistent.
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    log = logging.getLogger("rich") # Re-initialize the rich logger

    app = QApplication(sys.argv)
    window = FlashcardApp()
    window.show()

    with open("./styles/main_app_qss/main.qss", "r") as f:
        _style = f.read()
        app.setStyleSheet(_style)

    sys.exit(app.exec_())
