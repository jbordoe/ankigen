import os
import logging
import uuid
from typing import List, Optional, Dict, Any
from pathlib import Path
from dataclasses import dataclass

from ankigen.workflows import (
    TopicWorkflow, ModuleWorkflow, SubjectWorkflow,
    IterativeFlashcardGenerator
)
from ankigen.models.anki_card import AnkiCard
from ankigen.packagers.anki_deck_packager import AnkiDeckPackager
from ankigen.packagers.html_preview_packager import HtmlPreviewPackager

log = logging.getLogger("rich")


@dataclass
class GenerationRequest:
    """Request parameters for flashcard generation."""
    topic: str
    num_cards: int
    model_name: str = "gemini-2.0-flash"
    deck_name: Optional[str] = None
    session_id: Optional[str] = None
    workflow: str = "module"
    domain: Optional[str] = None
    template: str = "basic"


@dataclass
class OutputConfig:
    """Configuration for output generation."""
    output_type: str  # "anki" or "preview"
    filename: str = "generated_flashcards.apkg"
    output_dir: Optional[str] = None  # If None, uses default dirs


@dataclass
class GenerationResult:
    """Result of flashcard generation."""
    cards: List[AnkiCard]
    session_id: str
    output_path: str
    deck_name: str
    workflow_used: str


class FlashcardGenerationService:
    """
    Service class that encapsulates flashcard generation logic.
    Can be used by CLI, GUI, API, or any other interface.
    """
    
    def __init__(self):
        """Initialize the service."""
        self._validate_environment()
    
    def generate_flashcards(
        self, 
        request: GenerationRequest, 
        output_config: OutputConfig
    ) -> GenerationResult:
        """
        Generate flashcards based on request parameters and save to specified output.
        
        Args:
            request: Generation parameters
            output_config: Output configuration
            
        Returns:
            GenerationResult with generated cards and output information
            
        Raises:
            ValueError: If parameters are invalid
            RuntimeError: If generation fails
        """
        # Validate and prepare request
        validated_request = self._prepare_request(request)
        
        # Log generation start
        self._log_generation_start(validated_request)
        
        # Execute workflow
        cards = self._execute_workflow(validated_request)
        
        if not cards:
            raise RuntimeError("No flashcards were generated.")
        
        # Generate output
        output_path = self._generate_output(cards, validated_request, output_config)
        
        return GenerationResult(
            cards=cards,
            session_id=validated_request.session_id,
            output_path=output_path,
            deck_name=validated_request.deck_name,
            workflow_used=validated_request.workflow
        )
    
    def list_available_workflows(self) -> List[str]:
        """Get list of available workflow types."""
        return ["topic", "module", "subject", "iterative"]
    
    def _validate_environment(self) -> None:
        """Validate that required environment variables are set."""
        if not os.environ.get("GOOGLE_API_KEY"):
            raise RuntimeError("GOOGLE_API_KEY environment variable not set. Please set it to your Google Cloud API key.")
    
    def _prepare_request(self, request: GenerationRequest) -> GenerationRequest:
        """Validate and prepare the generation request."""
        # Generate session ID if not provided
        session_id = request.session_id or str(uuid.uuid4())
        
        # Set default deck name if not provided
        deck_name = request.deck_name or f"Generated Flashcards: {request.topic}"
        
        # Validate workflow type
        if request.workflow not in self.list_available_workflows():
            raise ValueError(f"Unknown workflow type: {request.workflow}")
        
        # Validate num_cards range
        if request.num_cards < 1 or request.num_cards > 50:
            raise ValueError("Number of cards must be between 1 and 50")
        
        return GenerationRequest(
            topic=request.topic,
            num_cards=request.num_cards,
            model_name=request.model_name,
            deck_name=deck_name,
            session_id=session_id,
            workflow=request.workflow,
            domain=request.domain,
            template=request.template
        )
    
    def _log_generation_start(self, request: GenerationRequest) -> None:
        """Log the start of generation with parameters."""
        if request.session_id and request.session_id != str(uuid.uuid4()):
            log.info(f"Using provided session ID: {request.session_id} (Attempting to resume workflow)")
        else:
            log.info(f"Generated new session ID: {request.session_id}")
            
        if request.domain:
            log.info(f"Starting flashcard generation for topic: '{request.topic}', aiming for {request.num_cards} cards using model: '{request.model_name}' with '{request.workflow}' workflow and '{request.domain}' examples.")
        else:
            log.info(f"Starting flashcard generation for topic: '{request.topic}', aiming for {request.num_cards} cards using model: '{request.model_name}' with '{request.workflow}' workflow (zero-shot).")
    
    def _execute_workflow(self, request: GenerationRequest) -> List[AnkiCard]:
        """Execute the appropriate workflow based on request parameters."""
        workflow_params = self._get_workflow_params(request)
        generator = self._create_workflow_generator(request)
        
        final_state = generator.invoke(workflow_params, session_id=request.session_id)
        return final_state.get("all_generated_cards", [])
    
    def _get_workflow_params(self, request: GenerationRequest) -> Dict[str, Any]:
        """Get parameters for the specific workflow type."""
        if request.workflow == "topic":
            return {
                "topic": "General",  # Generic module
                "subtopic": request.topic,
                "num_cards": request.num_cards
            }
        elif request.workflow == "module":
            return {
                "topic": request.topic,
                "cards_per_topic": max(2, request.num_cards // 3)  # Distribute cards across topics
            }
        elif request.workflow == "subject":
            return {
                "topic": request.topic,
                "subject_name": request.deck_name,
                "cards_per_module": request.num_cards
            }
        elif request.workflow == "iterative":
            return {
                "topic": request.topic,
                "max_cards": request.num_cards,
                "max_iterations": 5,
                "cards_per_iteration": 5
            }
        else:
            raise ValueError(f"Unknown workflow type: {request.workflow}")
    
    def _create_workflow_generator(self, request: GenerationRequest):
        """Create the appropriate workflow generator."""
        if request.workflow == "topic":
            return TopicWorkflow(llm_model_name=request.model_name, domain=request.domain)
        elif request.workflow == "module":
            return ModuleWorkflow(llm_model_name=request.model_name, domain=request.domain)
        elif request.workflow == "subject":
            return SubjectWorkflow(llm_model_name=request.model_name, domain=request.domain)
        elif request.workflow == "iterative":
            # Note: IterativeFlashcardGenerator doesn't support domain parameter yet
            return IterativeFlashcardGenerator(llm_model_name=request.model_name)
        else:
            raise ValueError(f"Unknown workflow type: {request.workflow}")
    
    def _generate_output(
        self, 
        cards: List[AnkiCard], 
        request: GenerationRequest, 
        output_config: OutputConfig
    ) -> str:
        """Generate the output file (Anki deck or HTML preview)."""
        if output_config.output_type == "preview":
            return self._generate_html_preview(cards, request, output_config)
        elif output_config.output_type == "anki":
            return self._generate_anki_deck(cards, request, output_config)
        else:
            raise ValueError(f"Unknown output type: {output_config.output_type}")
    
    def _generate_html_preview(
        self, 
        cards: List[AnkiCard], 
        request: GenerationRequest, 
        output_config: OutputConfig
    ) -> str:
        """Generate HTML preview file."""
        # Determine output directory
        output_dir = output_config.output_dir or "previews"
        
        # Ensure .html extension
        filename = output_config.filename
        if filename.endswith('.apkg'):
            filename = filename.replace('.apkg', '.html')
        elif not filename.endswith('.html'):
            filename = filename + '.html'
        
        output_path = os.path.join(output_dir, filename)
        
        log.info(f"\n--- Creating HTML Preview: '{request.deck_name}' ---")
        
        preview_packager = HtmlPreviewPackager(title=f"Preview: {request.deck_name}")
        preview_packager.package_preview(cards, output_path)
        
        absolute_path = os.path.abspath(output_path)
        log.info(f"HTML preview generation complete. File saved to: {output_path}")
        log.info(f"Open in browser: file://{absolute_path}")
        
        return output_path
    
    def _generate_anki_deck(
        self, 
        cards: List[AnkiCard], 
        request: GenerationRequest, 
        output_config: OutputConfig
    ) -> str:
        """Generate Anki deck file."""
        # Determine output directory
        output_dir = output_config.output_dir or "decks"
        
        # Ensure .apkg extension
        filename = output_config.filename
        if not filename.endswith('.apkg'):
            filename = filename + '.apkg'
        
        output_path = os.path.join(output_dir, filename)
        
        log.info(f"\n--- Creating Anki Deck: '{request.deck_name}' ---")
        
        packager = AnkiDeckPackager(deck_name=request.deck_name, template=request.template)
        packager.package_deck(cards, output_path)
        
        log.info(f"Anki deck generation complete. File saved to: {output_path}")
        
        return output_path