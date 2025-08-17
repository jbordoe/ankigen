import logging
from typing import Dict, Any, List, Optional

from langchain_core.prompts import PromptTemplate
from langgraph.graph import StateGraph, END

from ankigen.models.anki_card import AnkiCard
from ankigen.workflows.base_workflow import BaseWorkflow, BaseState
from ankigen.workflows.example_workflow import ExampleWorkflow

log = logging.getLogger("rich")


class TopicState(BaseState):
    """State for topic workflow - generates cards for a single topic."""
    subtopic: str
    num_cards: int
    concepts_generated: bool
    concepts: List[str]


class TopicWorkflow(BaseWorkflow):
    """
    Simple workflow that generates flashcards for a single topic.
    This is the most basic building block - other workflows compose this.
    """
    
    def __init__(self, llm_model_name: str = "gemini-2.0-flash", domain: Optional[str] = None):
        """
        Initialize TopicWorkflow with optional domain for few-shot examples.
        
        Args:
            llm_model_name: LLM model to use
            domain: Domain for examples (None for zero-shot)
        """
        super().__init__(llm_model_name)
        self.example_workflow = ExampleWorkflow()
        self.examples = self.example_workflow.load_examples(domain)
        self.domain = domain
    
    def _compile_workflow(self):
        workflow = StateGraph(TopicState)
        
        workflow.add_node("generate_concepts", self._generate_concepts)
        workflow.add_node("generate_cards", self._generate_cards)
        
        workflow.set_entry_point("generate_concepts")
        workflow.add_edge("generate_concepts", "generate_cards")
        workflow.add_edge("generate_cards", END)
        
        return workflow.compile(checkpointer=self.checkpointer)
    
    def _generate_concepts(self, state: TopicState) -> TopicState:
        """Generate key concepts for the subtopic."""
        if state.get("concepts_generated", False):
            return state
            
        subtopic = state["subtopic"]
        topic = state["topic"]
        num_cards = state["num_cards"]
        
        log.info(f"Generating {num_cards} concepts for subtopic: {subtopic}")
        
        prompt = PromptTemplate.from_template(
            f"For the subtopic '{subtopic}' within the broader topic '{topic}', "
            f"list {num_cards} specific concepts that need flashcards. "
            "Return as comma-separated list. No other text."
        )
        
        response = self.llm.invoke(prompt.format(subtopic=subtopic, topic=topic)).content
        log.debug(f"Concept generation response: {response}")
        concepts = [c.strip() for c in response.split(',') if c.strip()]
        
        return {
            **state,
            "concepts_generated": True,
            "concepts": concepts[:num_cards]  # Ensure we don't exceed requested number
        }
    
    def _generate_cards(self, state: TopicState) -> TopicState:
        """Generate cards for the concepts."""
        concepts = state.get("concepts", [])
        subtopic = state["subtopic"] 
        topic = state["topic"]
        
        log.info(f"Generating cards for {len(concepts)} concepts in subtopic: {subtopic}")
        
        cards = []
        for concept in concepts:
            try:
                card = self._generate_single_card(concept, subtopic, topic)
                cards.append(card)
            except Exception as e:
                log.warning(f"Failed to generate card for concept '{concept}': {e}")
        
        return {
            **state,
            "all_generated_cards": cards,
            "overall_process_complete": True
        }
    
    def _generate_single_card(self, concept: str, subtopic: str, topic: str) -> AnkiCard:
        """Generate a single card for a concept using few-shot or zero-shot prompting."""
        if self.examples:
            # Few-shot prompting with examples - construct prompt directly to avoid template variable issues
            examples_text = self.example_workflow.format_examples_for_prompt(self.examples)
            
            prompt_text = f"""Here are examples of good flashcards for {self.domain} domain:

{examples_text}

Now generate a similar flashcard for concept '{concept}' within subtopic '{subtopic}' of topic '{topic}'.
Follow the same style and format as the examples above.
Return valid JSON matching the same structure."""
            
            # Use the LLM directly without PromptTemplate to avoid curly brace issues
            response = self.llm.invoke(prompt_text)
            card_dict = self.anki_card_parser.parse(response.content)
            return AnkiCard(**card_dict)
        else:
            # Zero-shot prompting (original behavior) 
            prompt = PromptTemplate.from_template(
                f"Generate an Anki flashcard for concept '{{concept}}' within subtopic '{{subtopic}}' of topic '{{topic}}'. "
                "Include question, answer, and explanation. "
                "Return valid JSON matching AnkiCard format:\n"
                "{format_instructions}"
            ).partial(format_instructions=self.anki_card_parser.get_format_instructions())
            
            chain = prompt | self.llm | self.anki_card_parser
            card_dict = chain.invoke({"concept": concept, "subtopic": subtopic, "topic": topic})
            return AnkiCard(**card_dict)
    
    def invoke(self, input_state: Dict[str, Any], session_id: Optional[str] = None) -> TopicState:
        """
        Generate cards for a single subtopic.
        
        Required input_state fields:
        - topic: str
        - subtopic: str  
        - num_cards: int
        """
        self._validate_input_state(input_state, ["topic", "subtopic", "num_cards"])
        
        initial_state = self._create_initial_state(input_state, {
            "subtopic": input_state["subtopic"],
            "num_cards": input_state["num_cards"],
            "concepts_generated": False
        })
        
        self._log_workflow_start("TopicWorkflow", input_state)
        
        final_state = self.workflow.invoke(
            initial_state,
            config={"configurable": {"thread_id": session_id}}
        )
        
        self._log_workflow_complete("TopicWorkflow", final_state)
        return final_state
