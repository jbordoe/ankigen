import sys
import logging

from typing import List
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QComboBox, QSpinBox,
    QFileDialog, QMessageBox
)
from PyQt5.QtCore import QThread, pyqtSignal # For threading

from ankigen.services import (
    FlashcardGenerationService, 
    GenerationRequest, 
    OutputConfig, 
    GenerationResult
)
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
class FlashcardGeneratorWorker(QThread):
    """
    Worker thread that uses FlashcardGenerationService for flashcard generation.
    Emits signals for progress updates and completion.
    """
    finished = pyqtSignal(object) # Emits the GenerationResult on completion
    error = pyqtSignal(str)       # Emits error messages
    log_message = pyqtSignal(str) # Emits log messages

    def __init__(self, request: GenerationRequest, output_config: OutputConfig, parent=None):
        super().__init__(parent)
        self.request = request
        self.output_config = output_config
        self._is_running = True

    def run(self):
        try:
            # Initialize service
            service = FlashcardGenerationService()
            
            # Generate flashcards - THIS IS THE LONG-RUNNING CALL
            result = service.generate_flashcards(self.request, self.output_config)

            if self._is_running: # Only emit finished if not stopped prematurely
                self.finished.emit(result)
        except (ValueError, RuntimeError) as e:
            self.error.emit(f"Generation error: {e}")
        except Exception as e:
            self.error.emit(f"Unexpected error: {e}")
        finally:
            self.log_message.emit("Flashcard generation thread finished.")

    def stop(self):
        self._is_running = False
        # Note: More advanced graceful stopping would require workflow-level support


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
        self.template_type_dropdown.addItem("basic")
        self.template_type_dropdown.addItem("comprehensive") 
        right_input_col.addWidget(self.template_type_dropdown)

        # Workflow Type Dropdown
        right_input_col.addWidget(QLabel("Workflow Type:"))
        self.workflow_dropdown = QComboBox()
        self.workflow_dropdown.addItem("module")
        self.workflow_dropdown.addItem("topic")
        self.workflow_dropdown.addItem("subject")
        self.workflow_dropdown.addItem("iterative")
        right_input_col.addWidget(self.workflow_dropdown)

        # Domain Input (optional)
        right_input_col.addWidget(QLabel("Domain (Optional):"))
        self.domain_input = QLineEdit("")
        self.domain_input.setPlaceholderText("e.g., language-vocabulary, programming")
        right_input_col.addWidget(self.domain_input)

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

        # Get values from GUI
        topic = self.topic_input.text()
        num_cards = self.max_cards_spinbox.value()
        template = self.template_type_dropdown.currentText()
        workflow = self.workflow_dropdown.currentText()
        domain = self.domain_input.text().strip() or None
        session_id = self.session_id_input.text().strip() or None

        if not topic.strip():
            QMessageBox.warning(self, "Input Error", "Please enter a topic.")
            self.generate_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            return

        # Create generation request
        request = GenerationRequest(
            topic=topic,
            num_cards=num_cards,
            template=template,
            workflow=workflow,
            domain=domain,
            session_id=session_id
        )
        
        # Create output configuration (generate in memory, not to file)
        output_config = OutputConfig(
            output_type="anki",  # We'll handle the output internally
            filename="temp.apkg"  # Placeholder, won't be used
        )

        log.info(f"Starting generation for topic: '{topic}'")
        log.info(f"Cards: {num_cards}, Workflow: {workflow}, Template: {template}")
        if domain:
            log.info(f"Using domain: {domain}")

        # Instantiate and start the worker thread
        self.generator_thread = FlashcardGeneratorWorker(
            request=request,
            output_config=output_config,
            parent=self
        )
        self.generator_thread.finished.connect(self._generation_finished)
        self.generator_thread.finished.connect(self.generator_thread.deleteLater) # Schedule for deletion
        self.generator_thread.error.connect(self._generation_error)
        # Connect log_message signal from worker to update GUI log
        self.generator_thread.log_message.connect(self.log_output.append)
        self.generator_thread.start() # This calls the run() method in the thread


    def _generation_finished(self, result: GenerationResult):
        """
        Callback when the generation thread finishes.
        """
        log.info("Flashcard generation complete!")
        self.current_generated_cards = result.cards
        log.info(f"Total cards generated: {len(self.current_generated_cards)}")
        log.info(f"Workflow used: {result.workflow_used}")
        log.info(f"Session ID: {result.session_id}")

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
                    template=selected_template_type
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
