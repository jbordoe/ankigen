import logging
from typing import Dict, Any, List, Optional

from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langgraph.graph import StateGraph, END

from ankigen.models.anki_card import AnkiCard
from ankigen.workflows.base_workflow import BaseWorkflow, BaseState
from ankigen.workflows.module_workflow import ModuleWorkflow

log = logging.getLogger("rich")


class SubjectState(BaseState):
    """State for subject workflow - coordinates multiple modules."""
    modules: List[str]
    cards_per_module: int
    modules_processed: List[str]
    current_module_index: int
    subject_name: str


class SubjectWorkflow(BaseWorkflow):
    """
    Top-level workflow that coordinates multiple modules to create a comprehensive subject.
    This creates a superdeck with multiple subdecks for complex learning domains.
    """
    
    def __init__(self, llm_model_name: str = "gemini-2.0-flash"):
        super().__init__(llm_model_name)
        self.module_workflow = ModuleWorkflow(llm_model_name)
    
    def _compile_workflow(self):
        workflow = StateGraph(SubjectState)
        
        workflow.add_node("plan_modules", self._plan_modules)
        workflow.add_node("process_module", self._process_module)
        
        workflow.set_entry_point("plan_modules")
        workflow.add_edge("plan_modules", "process_module")
        
        # Continue processing modules until all are done
        workflow.add_conditional_edges(
            "process_module",
            self._check_modules_complete,
            {
                "continue": "process_module", 
                "finish": END
            }
        )
        
        return workflow.compile(checkpointer=self.checkpointer)
    
    def _plan_modules(self, state: SubjectState) -> SubjectState:
        """Plan the modules to cover for this subject."""
        if state.get("modules"):
            return state
            
        subject_name = state["subject_name"]
        main_subject = state["topic"]
        
        log.info(f"Planning modules for subject: {subject_name}")
        
        # If modules are explicitly provided, use them
        if isinstance(main_subject, list):
            modules = main_subject
        else:
            # Break down main subject into multiple focused modules
            prompt = PromptTemplate.from_template(
                f"For creating a comprehensive subject on '{main_subject}', "
                "identify 2-4 main modules that should be covered. "
                "Each module should be substantial enough for its own subdeck. "
                "Return as JSON array of module names. No other text."
            )
            
            chain = prompt | self.llm | JsonOutputParser()
            modules = chain.invoke({"main_subject": main_subject})
            
            if not isinstance(modules, list):
                log.warning(f"Expected list of modules, got: {modules}")
                modules = [main_subject]  # Fallback to single module
        
        log.info(f"Planned modules for subject: {modules}")
        
        return {
            **state,
            "modules": modules,
            "modules_processed": [],
            "current_module_index": 0
        }
    
    def _process_module(self, state: SubjectState) -> SubjectState:
        """Process the current module using ModuleWorkflow."""
        modules = state["modules"]
        current_index = state["current_module_index"]
        cards_per_module = state["cards_per_module"]
        
        if current_index >= len(modules):
            return state
            
        current_module = modules[current_index]
        log.info(f"Processing module {current_index + 1}/{len(modules)}: {current_module}")
        
        # Use ModuleWorkflow to generate cards for this module
        module_input = {
            "topic": current_module,
            "cards_per_topic": cards_per_module // 3  # Distribute cards across topics
        }
        
        try:
            module_result = self.module_workflow.invoke(module_input)
            new_cards = module_result.get("all_generated_cards", [])
            
            # Combine with existing cards
            all_cards = state.get("all_generated_cards", []) + new_cards
            processed_modules = state["modules_processed"] + [current_module]
            
            return {
                **state,
                "all_generated_cards": all_cards,
                "modules_processed": processed_modules,
                "current_module_index": current_index + 1
            }
            
        except Exception as e:
            log.error(f"Error processing module '{current_module}': {e}")
            # Skip this module and continue
            return {
                **state,
                "modules_processed": state["modules_processed"] + [current_module],
                "current_module_index": current_index + 1
            }
    
    def _check_modules_complete(self, state: SubjectState) -> str:
        """Check if all modules have been processed."""
        current_index = state["current_module_index"]
        total_modules = len(state.get("modules", []))
        
        if current_index >= total_modules:
            log.info("All modules processed")
            return "finish"
        else:
            return "continue"
    
    def invoke(self, input_state: Dict[str, Any], session_id: Optional[str] = None) -> SubjectState:
        """
        Generate a comprehensive subject covering multiple modules.
        
        Required input_state fields:
        - topic: str or List[str] (main subject or list of modules)
        - subject_name: str
        - cards_per_module: int (optional, defaults to 15)
        """
        self._validate_input_state(input_state, ["topic", "subject_name"])
        
        initial_state = self._create_initial_state(input_state, {
            "subject_name": input_state["subject_name"],
            "cards_per_module": input_state.get("cards_per_module", 15),
            "modules": [],
            "modules_processed": [],
            "current_module_index": 0
        })
        
        self._log_workflow_start("SubjectWorkflow", input_state)
        
        final_state = self.workflow.invoke(
            initial_state,
            config={"configurable": {"thread_id": session_id}}
        )
        
        self._log_workflow_complete("SubjectWorkflow", final_state)
        return final_state