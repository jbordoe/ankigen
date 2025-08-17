import logging
from typing import Dict, Any, List, Optional

from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langgraph.graph import StateGraph, END

from ankigen.models.anki_card import AnkiCard
from ankigen.workflows.base_workflow import BaseWorkflow, BaseState
from ankigen.workflows.topic_workflow import TopicWorkflow

log = logging.getLogger("rich")


class ModuleState(BaseState):
    """State for module workflow - coordinates multiple topics."""
    topics: List[str]
    cards_per_topic: int
    topics_processed: List[str]
    current_topic_index: int


class ModuleWorkflow(BaseWorkflow):
    """
    Workflow that breaks a module into topics and generates cards for each.
    Coordinates multiple TopicWorkflow instances.
    """
    
    def __init__(self, llm_model_name: str = "gemini-2.0-flash"):
        super().__init__(llm_model_name)
        self.topic_workflow = TopicWorkflow(llm_model_name)
    
    def _compile_workflow(self):
        workflow = StateGraph(ModuleState)
        
        workflow.add_node("identify_topics", self._identify_topics)
        workflow.add_node("process_topic", self._process_topic)
        
        workflow.set_entry_point("identify_topics")
        workflow.add_edge("identify_topics", "process_topic")
        
        # Continue processing topics until all are done
        workflow.add_conditional_edges(
            "process_topic",
            self._check_topics_complete,
            {
                "continue": "process_topic",
                "finish": END
            }
        )
        
        return workflow.compile(checkpointer=self.checkpointer)
    
    def _identify_topics(self, state: ModuleState) -> ModuleState:
        """Break the module into manageable topics."""
        if state.get("topics"):
            return state
            
        module = state["topic"]
        log.info(f"Identifying topics for module: {module}")
        
        prompt = PromptTemplate.from_template(
            f"Break down the module '{module}' into 3-5 key topics for comprehensive learning. "
            "Return as JSON array of topic names. No other text."
        )
        
        chain = prompt | self.llm | JsonOutputParser()
        topics = chain.invoke({"module": module})
        
        if not isinstance(topics, list):
            log.warning(f"Expected list of topics, got: {topics}")
            topics = [module]  # Fallback to single topic
        
        log.info(f"Identified topics: {topics}")
        
        return {
            **state,
            "topics": topics,
            "topics_processed": [],
            "current_topic_index": 0
        }
    
    def _process_topic(self, state: ModuleState) -> ModuleState:
        """Process the current topic using TopicWorkflow."""
        topics = state["topics"]
        current_index = state["current_topic_index"]
        cards_per_topic = state["cards_per_topic"]
        
        if current_index >= len(topics):
            return state
            
        current_topic = topics[current_index]
        log.info(f"Processing topic {current_index + 1}/{len(topics)}: {current_topic}")
        
        # Use TopicWorkflow to generate cards for this topic
        topic_input = {
            "topic": state["topic"],
            "subtopic": current_topic,
            "num_cards": cards_per_topic
        }
        
        try:
            topic_result = self.topic_workflow.invoke(topic_input)
            new_cards = topic_result.get("all_generated_cards", [])
            
            # Combine with existing cards
            all_cards = state.get("all_generated_cards", []) + new_cards
            processed_topics = state["topics_processed"] + [current_topic]
            
            return {
                **state,
                "all_generated_cards": all_cards,
                "topics_processed": processed_topics,
                "current_topic_index": current_index + 1
            }
            
        except Exception as e:
            log.error(f"Error processing topic '{current_topic}': {e}")
            # Skip this topic and continue
            return {
                **state,
                "topics_processed": state["topics_processed"] + [current_topic],
                "current_topic_index": current_index + 1
            }
    
    def _check_topics_complete(self, state: ModuleState) -> str:
        """Check if all topics have been processed."""
        current_index = state["current_topic_index"]
        total_topics = len(state.get("topics", []))
        
        if current_index >= total_topics:
            log.info("All topics processed")
            return "finish"
        else:
            return "continue"
    
    def invoke(self, input_state: Dict[str, Any], session_id: Optional[str] = None) -> ModuleState:
        """
        Generate cards for a module by breaking it into topics.
        
        Required input_state fields:
        - topic: str
        - cards_per_topic: int (optional, defaults to 5)
        """
        self._validate_input_state(input_state, ["topic"])
        
        initial_state = self._create_initial_state(input_state, {
            "cards_per_topic": input_state.get("cards_per_topic", 5),
            "topics": [],
            "topics_processed": [],
            "current_topic_index": 0
        })
        
        self._log_workflow_start("ModuleWorkflow", input_state)
        
        final_state = self.workflow.invoke(
            initial_state,
            config={"configurable": {"thread_id": session_id}}
        )
        
        self._log_workflow_complete("ModuleWorkflow", final_state)
        return final_state