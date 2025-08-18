import sys
import logging
import os
from pathlib import Path

from typing import List
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QComboBox, QSpinBox,
    QFileDialog, QMessageBox, QProgressBar, QSplitter, QGroupBox,
    QFrame, QScrollArea, QGridLayout, QStatusBar, QMenuBar, QAction,
    QToolTip, QTabWidget, QListWidget, QListWidgetItem
)
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QTimer, QPropertyAnimation, QRect
from PyQt5.QtGui import QFont, QPixmap, QPalette, QIcon, QMovie

from ankigen.services import (
    FlashcardGenerationService, 
    GenerationRequest, 
    OutputConfig, 
    GenerationResult
)
from ankigen.workflows.example_workflow import ExampleWorkflow
from ankigen.models.anki_card import AnkiCard
from ankigen.packagers.anki_deck_packager import AnkiDeckPackager

log = logging.getLogger("rich")


class QTextEditLogger(logging.Handler):
    """Custom logging handler that redirects log records to a QTextEdit widget."""
    def __init__(self, parent_text_edit):
        super().__init__()
        self.widget = parent_text_edit
        self.widget.setReadOnly(True)
        self.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

    def emit(self, record):
        msg = self.format(record)
        self.widget.append(msg)


class FlashcardGeneratorWorker(QThread):
    """Worker thread that uses FlashcardGenerationService for flashcard generation."""
    finished = pyqtSignal(object)  # Emits GenerationResult
    error = pyqtSignal(str)        # Emits error messages
    log_message = pyqtSignal(str)  # Emits log messages
    progress = pyqtSignal(int)     # Emits progress percentage

    def __init__(self, request: GenerationRequest, output_config: OutputConfig, parent=None):
        super().__init__(parent)
        self.request = request
        self.output_config = output_config
        self._is_running = True

    def run(self):
        try:
            # Simulate progress updates (in real implementation, you'd hook into the service)
            self.progress.emit(10)
            
            service = FlashcardGenerationService()
            self.progress.emit(30)
            
            result = service.generate_flashcards(self.request, self.output_config)
            self.progress.emit(100)

            if self._is_running:
                self.finished.emit(result)
        except (ValueError, RuntimeError) as e:
            self.error.emit(f"Generation error: {e}")
        except Exception as e:
            self.error.emit(f"Unexpected error: {e}")
        finally:
            self.log_message.emit("Flashcard generation thread finished.")

    def stop(self):
        self._is_running = False


class CardPreviewWidget(QWidget):
    """Widget for previewing generated flashcards."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.cards = []
        self.current_index = 0
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        # Header
        header = QLabel("Card Preview")
        header.setObjectName("previewHeader")
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)
        
        # Card display area
        self.card_display = QTextEdit()
        self.card_display.setObjectName("cardPreview")
        self.card_display.setMinimumHeight(200)
        layout.addWidget(self.card_display)
        
        # Navigation controls
        nav_layout = QHBoxLayout()
        self.prev_btn = QPushButton("← Previous")
        self.prev_btn.clicked.connect(self.prev_card)
        self.next_btn = QPushButton("Next →")
        self.next_btn.clicked.connect(self.next_card)
        
        self.card_counter = QLabel("0 / 0")
        self.card_counter.setAlignment(Qt.AlignCenter)
        
        nav_layout.addWidget(self.prev_btn)
        nav_layout.addWidget(self.card_counter)
        nav_layout.addWidget(self.next_btn)
        layout.addLayout(nav_layout)
        
        self.update_navigation()

    def set_cards(self, cards: List[AnkiCard]):
        self.cards = cards
        self.current_index = 0
        self.update_display()
        self.update_navigation()

    def update_display(self):
        if not self.cards:
            self.card_display.setHtml("<p>No cards to preview</p>")
            return
            
        card = self.cards[self.current_index]
        html = f"""
        <div style="background: #1e1e1e; padding: 20px; border-radius: 8px; margin: 10px;">
            <h3 style="color: #03dac6; margin-bottom: 15px;">Front</h3>
            <div style="background: #121212; padding: 15px; border-radius: 4px; margin-bottom: 20px;">
                <p style="font-size: 18px; color: #e1e1e1;">{card.front_question_text}</p>
                {f'<p style="color: #bb86fc; font-size: 14px; margin-top: 10px;"><em>Context: {card.front_question_context}</em></p>' if card.front_question_context else ''}
                {f'<p style="color: #985eff; font-size: 14px;"><strong>Hint:</strong> {card.front_question_hint}</p>' if card.front_question_hint else ''}
            </div>
            
            <h3 style="color: #03dac6; margin-bottom: 15px;">Back</h3>
            <div style="background: #121212; padding: 15px; border-radius: 4px;">
                <p style="font-size: 18px; color: #e1e1e1; font-weight: bold;">{card.back_answer}</p>
                {f'<p style="color: #e1e1e1; font-size: 14px; margin-top: 10px;">{card.back_explanation}</p>' if card.back_explanation else ''}
                {f'<p style="color: #bb86fc; font-size: 12px; margin-top: 10px;"><strong>Related:</strong> {", ".join(card.back_related)}</p>' if card.back_related else ''}
            </div>
            
            <div style="margin-top: 15px;">
                <span style="background: #664b86; color: #e1e1e1; padding: 4px 8px; border-radius: 12px; font-size: 11px;">{card.card_type or 'Unknown'}</span>
                {f'<span style="background: #985eff; color: #000; padding: 4px 8px; border-radius: 12px; font-size: 11px; margin-left: 5px;">{card.difficulty}</span>' if card.difficulty else ''}
            </div>
        </div>
        """
        self.card_display.setHtml(html)

    def update_navigation(self):
        if not self.cards:
            self.card_counter.setText("0 / 0")
            self.prev_btn.setEnabled(False)
            self.next_btn.setEnabled(False)
        else:
            self.card_counter.setText(f"{self.current_index + 1} / {len(self.cards)}")
            self.prev_btn.setEnabled(self.current_index > 0)
            self.next_btn.setEnabled(self.current_index < len(self.cards) - 1)

    def prev_card(self):
        if self.current_index > 0:
            self.current_index -= 1
            self.update_display()
            self.update_navigation()

    def next_card(self):
        if self.current_index < len(self.cards) - 1:
            self.current_index += 1
            self.update_display()
            self.update_navigation()


class StatusWidget(QWidget):
    """Widget showing generation status and statistics."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        # Status header
        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("statusHeader")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Statistics
        stats_group = QGroupBox("Generation Statistics")
        stats_layout = QGridLayout(stats_group)
        
        self.cards_generated_label = QLabel("Cards Generated: 0")
        self.session_id_label = QLabel("Session ID: -")
        self.workflow_label = QLabel("Workflow: -")
        self.domain_label = QLabel("Domain: -")
        
        stats_layout.addWidget(self.cards_generated_label, 0, 0)
        stats_layout.addWidget(self.session_id_label, 0, 1)
        stats_layout.addWidget(self.workflow_label, 1, 0)
        stats_layout.addWidget(self.domain_label, 1, 1)
        
        layout.addWidget(stats_group)
        layout.addStretch()

    def set_status(self, status: str, show_progress: bool = False):
        self.status_label.setText(status)
        self.progress_bar.setVisible(show_progress)

    def set_progress(self, value: int):
        self.progress_bar.setValue(value)

    def update_stats(self, result: GenerationResult = None, domain: str = None):
        if result:
            self.cards_generated_label.setText(f"Cards Generated: {len(result.cards)}")
            self.session_id_label.setText(f"Session ID: {result.session_id[:8]}...")
            self.workflow_label.setText(f"Workflow: {result.workflow_used}")
            
            # Show domain if provided
            if domain:
                display_domain = domain.replace('-', ' → ').title()
                self.domain_label.setText(f"Domain: {display_domain}")
            else:
                self.domain_label.setText("Domain: Zero-shot")
        else:
            self.cards_generated_label.setText("Cards Generated: 0")
            self.session_id_label.setText("Session ID: -")
            self.workflow_label.setText("Workflow: -")
            self.domain_label.setText("Domain: -")


class EnhancedFlashcardApp(QMainWindow):
    """Enhanced GUI with professional polish and better UX."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AnkiGen - AI Flashcard Generator")
        self.setGeometry(100, 100, 1200, 800)
        
        self.current_generated_cards: List[AnkiCard] = []
        self.generator_thread = None
        
        self._init_ui()
        self._setup_menubar()
        self._setup_statusbar()
        self._setup_logging()
        
    def _init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        
        # Create main splitter for resizable panels
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)
        
        # Left panel - Input controls
        left_panel = self._create_input_panel()
        splitter.addWidget(left_panel)
        
        # Right panel - Results and preview
        right_panel = self._create_results_panel()
        splitter.addWidget(right_panel)
        
        # Set splitter sizes (60% input, 40% results)
        splitter.setSizes([720, 480])

    def _create_input_panel(self):
        """Create the left panel with input controls."""
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        panel = QWidget()
        layout = QVBoxLayout(panel)
        
        # Topic Configuration Section
        topic_group = QGroupBox("Topic Configuration")
        topic_layout = QVBoxLayout(topic_group)
        
        topic_layout.addWidget(QLabel("Topic:"))
        self.topic_input = QLineEdit("German A1 vocabulary")
        self.topic_input.setPlaceholderText("Enter the topic for flashcard generation")
        topic_layout.addWidget(self.topic_input)
        
        topic_layout.addWidget(QLabel("Number of Cards:"))
        self.num_cards_spinbox = QSpinBox()
        self.num_cards_spinbox.setRange(1, 50)
        self.num_cards_spinbox.setValue(10)
        topic_layout.addWidget(self.num_cards_spinbox)
        
        layout.addWidget(topic_group)
        
        # Generation Settings Section  
        settings_group = QGroupBox("Generation Settings")
        settings_layout = QGridLayout(settings_group)
        
        settings_layout.addWidget(QLabel("Workflow:"), 0, 0)
        self.workflow_dropdown = QComboBox()
        self.workflow_dropdown.addItems(["module", "topic", "subject", "iterative"])
        self.workflow_dropdown.setToolTip("Choose the generation approach:\n• Module: Break topic into subtopics\n• Topic: Single focused topic\n• Subject: Multi-module approach\n• Iterative: Legacy iterative generation")
        settings_layout.addWidget(self.workflow_dropdown, 0, 1)
        
        settings_layout.addWidget(QLabel("Template:"), 1, 0)
        self.template_dropdown = QComboBox()
        self.template_dropdown.addItems(["basic", "comprehensive"])
        settings_layout.addWidget(self.template_dropdown, 1, 1)
        
        settings_layout.addWidget(QLabel("Domain:"), 2, 0)
        self.domain_dropdown = QComboBox()
        self.domain_dropdown.setEditable(False)
        self.domain_dropdown.setToolTip("Optional: Use few-shot examples from a specific domain")
        
        # Populate domain options
        try:
            domains = ExampleWorkflow.get_available_domains()
            self.domain_dropdown.addItem("None (Zero-shot)", "")  # Default option
            for domain in domains:
                # Create user-friendly display names
                display_name = domain.replace('-', ' → ').title()
                self.domain_dropdown.addItem(display_name, domain)
        except Exception as e:
            log.warning(f"Could not load available domains: {e}")
            self.domain_dropdown.addItem("None (Zero-shot)", "")
        
        settings_layout.addWidget(self.domain_dropdown, 2, 1)
        
        layout.addWidget(settings_group)
        
        # Advanced Options Section
        advanced_group = QGroupBox("Advanced Options")
        advanced_layout = QVBoxLayout(advanced_group)
        
        advanced_layout.addWidget(QLabel("Session ID (Optional):"))
        self.session_id_input = QLineEdit()
        self.session_id_input.setPlaceholderText("Leave empty for new session")
        self.session_id_input.setToolTip("Use existing session ID to resume generation")
        advanced_layout.addWidget(self.session_id_input)
        
        layout.addWidget(advanced_group)
        
        # Control Buttons
        button_layout = QVBoxLayout()
        
        self.generate_button = QPushButton("🎯 Generate Flashcards")
        self.generate_button.setObjectName("primaryButton")
        self.generate_button.clicked.connect(self._start_generation)
        self.generate_button.setMinimumHeight(50)
        button_layout.addWidget(self.generate_button)
        
        # Secondary buttons
        secondary_layout = QHBoxLayout()
        
        self.stop_button = QPushButton("⏹ Stop")
        self.stop_button.clicked.connect(self._stop_generation)
        self.stop_button.setEnabled(False)
        secondary_layout.addWidget(self.stop_button)
        
        self.export_button = QPushButton("💾 Export Deck")
        self.export_button.clicked.connect(self._export_deck)
        self.export_button.setEnabled(False)
        secondary_layout.addWidget(self.export_button)
        
        button_layout.addLayout(secondary_layout)
        layout.addLayout(button_layout)
        
        layout.addStretch()
        scroll_area.setWidget(panel)
        return scroll_area

    def _create_results_panel(self):
        """Create the right panel with results and preview."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        
        # Status widget
        self.status_widget = StatusWidget()
        layout.addWidget(self.status_widget)
        
        # Tab widget for different views
        tab_widget = QTabWidget()
        
        # Card Preview Tab
        self.card_preview = CardPreviewWidget()
        tab_widget.addTab(self.card_preview, "📋 Preview")
        
        # Generation Log Tab
        self.log_output = QTextEdit()
        self.log_output.setObjectName("logOutput")
        tab_widget.addTab(self.log_output, "📝 Log")
        
        layout.addWidget(tab_widget)
        
        return panel

    def _setup_menubar(self):
        """Create a professional menu bar."""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu('&File')
        
        new_action = QAction('&New Generation', self)
        new_action.setShortcut('Ctrl+N')
        new_action.triggered.connect(self._new_generation)
        file_menu.addAction(new_action)
        
        file_menu.addSeparator()
        
        export_action = QAction('&Export Deck...', self)
        export_action.setShortcut('Ctrl+S')
        export_action.triggered.connect(self._export_deck)
        file_menu.addAction(export_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction('E&xit', self)
        exit_action.setShortcut('Ctrl+Q')
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Help menu
        help_menu = menubar.addMenu('&Help')
        
        about_action = QAction('&About', self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _setup_statusbar(self):
        """Create status bar with useful information."""
        status_bar = QStatusBar()
        self.setStatusBar(status_bar)
        status_bar.showMessage("Ready to generate flashcards")

    def _setup_logging(self):
        """Setup logging to redirect to GUI."""
        root_logger = logging.getLogger()
        for handler in list(root_logger.handlers):
            if isinstance(handler, logging.StreamHandler) and hasattr(handler, 'console'):
                root_logger.removeHandler(handler)

        root_logger.setLevel(logging.INFO)
        gui_handler = QTextEditLogger(self.log_output)
        gui_handler.setLevel(logging.INFO)
        root_logger.addHandler(gui_handler)
        
        log.info("Enhanced GUI application started successfully")

    def _start_generation(self):
        """Start flashcard generation with enhanced feedback."""
        if self.generator_thread and self.generator_thread.isRunning():
            QMessageBox.warning(self, "Generation in Progress", 
                              "Flashcard generation is already running.")
            return

        # Validate input
        topic = self.topic_input.text().strip()
        if not topic:
            QMessageBox.warning(self, "Input Required", "Please enter a topic for flashcard generation.")
            self.topic_input.setFocus()
            return

        # Clear previous state
        self.current_generated_cards = []
        self.log_output.clear()
        self.card_preview.set_cards([])
        self.status_widget.update_stats()
        
        # Update UI state
        self._set_generation_state(True)
        
        # Get parameters
        domain_value = self.domain_dropdown.currentData()  # Gets the stored value, not display text
        request = GenerationRequest(
            topic=topic,
            num_cards=self.num_cards_spinbox.value(),
            template=self.template_dropdown.currentText(),
            workflow=self.workflow_dropdown.currentText(),
            domain=domain_value if domain_value else None,
            session_id=self.session_id_input.text().strip() or None
        )
        
        output_config = OutputConfig(
            output_type="anki",
            filename="temp.apkg"
        )

        # Start generation
        self.status_widget.set_status("Generating flashcards...", show_progress=True)
        self.statusBar().showMessage(f"Generating {request.num_cards} cards for '{topic}'...")
        
        self.generator_thread = FlashcardGeneratorWorker(request, output_config, self)
        self.generator_thread.finished.connect(self._generation_finished)
        self.generator_thread.finished.connect(self.generator_thread.deleteLater)
        self.generator_thread.error.connect(self._generation_error)
        self.generator_thread.progress.connect(self.status_widget.set_progress)
        self.generator_thread.log_message.connect(self.log_output.append)
        self.generator_thread.start()

    def _generation_finished(self, result: GenerationResult):
        """Handle successful generation completion."""
        self.current_generated_cards = result.cards
        self.card_preview.set_cards(result.cards)
        
        # Pass domain info to status widget
        domain_value = self.domain_dropdown.currentData()
        self.status_widget.update_stats(result, domain_value)
        self.status_widget.set_status(f"✅ Generated {len(result.cards)} cards successfully!")
        
        self.statusBar().showMessage(
            f"Generated {len(result.cards)} cards using {result.workflow_used} workflow"
        )
        
        self._set_generation_state(False)
        
        if result.cards:
            self.export_button.setEnabled(True)
            # Auto-switch to preview tab
            tab_widget = self.card_preview.parent()
            if hasattr(tab_widget, 'setCurrentWidget'):
                tab_widget.setCurrentWidget(self.card_preview)
        else:
            QMessageBox.information(self, "Generation Complete", 
                                  "No cards were generated. Check the log for details.")

    def _generation_error(self, error_message: str):
        """Handle generation errors."""
        self.status_widget.set_status(f"❌ Error: {error_message}")
        self.statusBar().showMessage("Generation failed - check log for details")
        
        QMessageBox.critical(self, "Generation Error", 
                           f"Failed to generate flashcards:\n\n{error_message}")
        
        self._set_generation_state(False)

    def _stop_generation(self):
        """Stop the generation process."""
        if self.generator_thread and self.generator_thread.isRunning():
            self.generator_thread.stop()
            self.generator_thread.wait(5000)
            
            if self.generator_thread.isRunning():
                self.generator_thread.terminate()
                log.warning("Generation thread forcibly terminated.")
            
            self.status_widget.set_status("⏹ Generation stopped")
            self.statusBar().showMessage("Generation stopped by user")
            self._set_generation_state(False)

    def _export_deck(self):
        """Export the generated deck with enhanced dialog."""
        if not self.current_generated_cards:
            QMessageBox.warning(self, "No Cards", "No cards available to export.")
            return

        # Enhanced file dialog
        topic = self.topic_input.text().replace(' ', '_').replace('.', '')
        template = self.template_dropdown.currentText()
        default_filename = f"{topic}_{template}_flashcards.apkg"
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Anki Deck",
            default_filename,
            "Anki Deck (*.apkg);;All Files (*)"
        )

        if file_path:
            try:
                deck_name = f"{self.topic_input.text()} ({template})"
                packager = AnkiDeckPackager(deck_name=deck_name, template=template)
                packager.package_deck(self.current_generated_cards, file_path)
                
                QMessageBox.information(self, "Export Successful", 
                                      f"Anki deck exported successfully!\n\nLocation: {file_path}")
                
                self.statusBar().showMessage(f"Deck exported to {Path(file_path).name}")
                
            except Exception as e:
                QMessageBox.critical(self, "Export Error", 
                                   f"Failed to export deck:\n\n{str(e)}")

    def _set_generation_state(self, generating: bool):
        """Update UI elements based on generation state."""
        self.generate_button.setEnabled(not generating)
        self.stop_button.setEnabled(generating)
        
        # Disable input controls during generation
        self.topic_input.setEnabled(not generating)
        self.num_cards_spinbox.setEnabled(not generating)
        self.workflow_dropdown.setEnabled(not generating)
        self.template_dropdown.setEnabled(not generating)
        self.domain_dropdown.setEnabled(not generating)
        self.session_id_input.setEnabled(not generating)

    def _new_generation(self):
        """Start a new generation (clear previous state)."""
        self.topic_input.clear()
        self.domain_dropdown.setCurrentIndex(0)  # Reset to "None (Zero-shot)"
        self.session_id_input.clear()
        self.num_cards_spinbox.setValue(10)
        self.workflow_dropdown.setCurrentText("module")
        self.template_dropdown.setCurrentText("basic")
        
        self.current_generated_cards = []
        self.card_preview.set_cards([])
        self.status_widget.update_stats()
        self.log_output.clear()
        
        self.export_button.setEnabled(False)
        self.status_widget.set_status("Ready for new generation")
        self.statusBar().showMessage("Ready to generate flashcards")

    def _show_about(self):
        """Show about dialog."""
        QMessageBox.about(self, "About AnkiGen", 
                         """<h3>AnkiGen - AI Flashcard Generator</h3>
                         <p>Generate high-quality flashcards using AI language models.</p>
                         <p><b>Features:</b></p>
                         <ul>
                         <li>Multiple generation workflows</li>
                         <li>Domain-specific few-shot prompting</li>  
                         <li>Professional card templates</li>
                         <li>Direct Anki integration</li>
                         </ul>
                         <p>Built with Python & PyQt5</p>""")


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    log = logging.getLogger("rich")

    app = QApplication(sys.argv)
    
    # Apply dark theme stylesheet
    try:
        with open("./styles/main_app_qss/main.qss", "r") as f:
            style = f.read()
            # Add custom styles for new components
            additional_styles = """
            #previewHeader {
                font-size: 18px;
                font-weight: bold;
                color: #03dac6;
                padding: 10px;
            }
            
            #cardPreview {
                border: 2px solid #664b86;
                border-radius: 8px;
            }
            
            #statusHeader {
                font-size: 16px;
                font-weight: bold;
                color: #bb86fc;
                padding: 8px;
            }
            
            #primaryButton {
                background-color: #03dac6;
                color: #000000;
                font-size: 16px;
                font-weight: bold;
            }
            
            #primaryButton:hover {
                background-color: #018786;
            }
            
            #logOutput {
                font-family: "Consolas", "Monaco", monospace;
                font-size: 12px;
            }
            """
            app.setStyleSheet(style + additional_styles)
    except FileNotFoundError:
        log.warning("Style sheet not found, using default theme")

    window = EnhancedFlashcardApp()
    window.show()

    sys.exit(app.exec_())