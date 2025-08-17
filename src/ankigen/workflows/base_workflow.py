import logging
import os
import sqlite3
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, TypedDict, List

from langchain_core.output_parsers import JsonOutputParser
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.sqlite import SqliteSaver

from ankigen.models.anki_card import AnkiCard

log = logging.getLogger("rich")


class BaseState(TypedDict):
    """Base state fields common to all workflows."""
    topic: str
    all_generated_cards: List[AnkiCard]
    overall_process_complete: bool


class BaseWorkflow(ABC):
    """
    Abstract base class for all AnkiGen workflows.
    Provides common functionality for LLM interaction, checkpointing, and workflow compilation.
    """
    
    def __init__(self, llm_model_name: str = "gemini-2.0-flash", checkpoint_db: str = "checkpoints/ankigen_graph.sqlite"):
        """
        Initialize the base workflow with common components.
        
        Args:
            llm_model_name: The LLM model to use for generation
            checkpoint_db: Path to the SQLite database for checkpointing
        """
        self.llm = ChatGoogleGenerativeAI(model=llm_model_name, temperature=0.7)
        self.anki_card_parser = JsonOutputParser(pydantic_object=AnkiCard)
        self.checkpoint_db = checkpoint_db
        self.checkpointer = self._setup_checkpointer()
        self.workflow = self._compile_workflow()
    
    def _setup_checkpointer(self) -> SqliteSaver:
        """Set up SQLite checkpointing for workflow state persistence."""
        os.makedirs(os.path.dirname(self.checkpoint_db), exist_ok=True)
        conn = sqlite3.connect(self.checkpoint_db, check_same_thread=False)
        return SqliteSaver(conn)
    
    @abstractmethod
    def _compile_workflow(self):
        """
        Compile the workflow graph. Must be implemented by subclasses.
        
        Returns:
            The compiled LangGraph workflow
        """
        pass
    
    @abstractmethod
    def invoke(self, input_state: Dict[str, Any], session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Invoke the workflow with the given input state.
        
        Args:
            input_state: The initial state for the workflow
            session_id: Optional session ID for checkpointing
            
        Returns:
            Dict[str, Any]: The final state of the workflow
        """
        pass
    
    def _log_workflow_start(self, workflow_name: str, input_state: Dict[str, Any]) -> None:
        """Log the start of a workflow execution."""
        log.info(f"Starting {workflow_name} workflow for topic: {input_state.get('topic', 'Unknown')}")
    
    def _log_workflow_complete(self, workflow_name: str, final_state: Dict[str, Any]) -> None:
        """Log the completion of a workflow execution."""
        cards_generated = len(final_state.get('all_generated_cards', []))
        log.info(f"Completed {workflow_name} workflow. Generated {cards_generated} cards.")
    
    def _validate_input_state(self, input_state: Dict[str, Any], required_fields: List[str]) -> None:
        """
        Validate that the input state contains all required fields.
        
        Args:
            input_state: The input state to validate
            required_fields: List of required field names
            
        Raises:
            ValueError: If any required field is missing
        """
        missing_fields = [field for field in required_fields if field not in input_state]
        if missing_fields:
            raise ValueError(f"Missing required fields in input state: {missing_fields}")
    
    def _create_initial_state(self, input_state: Dict[str, Any], additional_fields: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Create an initial workflow state from input state and additional fields.
        
        Args:
            input_state: The input state from the user
            additional_fields: Additional fields to include in the initial state
            
        Returns:
            Dict[str, Any]: The initial workflow state
        """
        initial_state = {
            "topic": input_state["topic"],
            "all_generated_cards": [],
            "overall_process_complete": False,
        }
        
        if additional_fields:
            initial_state.update(additional_fields)
            
        return initial_state