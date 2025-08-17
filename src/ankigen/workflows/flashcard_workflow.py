import logging
from typing import List, Dict, Any, Optional

from langchain_core.prompts import PromptTemplate
from langgraph.graph import StateGraph, END

from ankigen.models.anki_card import AnkiCard
from ankigen.workflows.base_workflow import BaseWorkflow, BaseState

log = logging.getLogger("rich")

class FlashcardState(BaseState):
    """
    Represents the state of the flashcard generation workflow.
    `num_cards` is now part of the state, passed at invocation.
    """
    num_cards: int
    overall_cards_generated_count: int
    concepts_for_generation: List[str]

class FlashcardGenerator(BaseWorkflow):
    """
    A class to encapsulate the LangGraph workflow for generating Anki flashcards.
    Allows for parameterization of the LLM model.
    The number of cards is now passed per invocation.
    """
    def __init__(self, llm_model_name: str = "gemini-2.0-flash"):
        super().__init__(llm_model_name)

    def _compile_workflow(self):
        """
        Defines and compiles the LangGraph workflow.
        """
        workflow = StateGraph(FlashcardState)

        # Add Nodes
        workflow.add_node("generate_initial_concepts", self._generate_initial_concepts)
        workflow.add_node("generate_flashcard", self._generate_flashcard)

        # Define Entry Point
        workflow.set_entry_point("generate_initial_concepts")

        # Define Edges
        workflow.add_edge("generate_initial_concepts", "generate_flashcard")

        # After generating a flashcard, check if more concepts
        workflow.add_conditional_edges(
            "generate_flashcard",
            self._check_completion,
            {
                "continue": "generate_flashcard",
                "finish": END
            }
        )
        return workflow.compile(checkpointer=self.checkpointer)

    def _generate_initial_concepts(self, state: FlashcardState) -> FlashcardState:
        """
        Node to generate an initial flat list of concepts for the given topic.
        Uses num_cards from the state.
        """
        if state["concepts_for_generation"]:
            log.info("Concepts already generated. Skipping.")
            return state

        topic = state["topic"]
        num_cards = state["num_cards"] # Access from state
        log.info(f"Generating {num_cards} concepts for topic: {topic}...")
        prompt = PromptTemplate.from_template(
            f"For the topic '{topic}', list {num_cards} distinct and important concepts or sub-topics "
            "that are essential for learning. "
            "Return the concepts as a comma-separated list, e.g., 'Concept A, Concept B, Concept C'. "
            "Do not add any other text."
        )
        response_str = self.llm.invoke(prompt.format(topic=topic)).content
        concepts = [c.strip() for c in response_str.split(',') if c.strip()]

        log.info(f"Generated concepts: {concepts}")
        return {
            "concepts_for_generation": concepts,
            "all_generated_cards": [],
            "overall_process_complete": False,
            "overall_cards_generated_count": 0,
            "num_cards": num_cards # Keep num_cards in state for consistency if needed downstream
        }

    def _generate_flashcard(self, state: FlashcardState) -> FlashcardState:
        """
        Node to generate a single flashcard for a concept and add it to the list.
        """
        if not state["concepts_for_generation"]:
            log.info("No more concepts to generate cards for.")
            return state # No changes, signifies completion via router

        concept = state["concepts_for_generation"][0]
        log.info(f"Generating flashcard for concept: '{concept}' under topic: '{state['topic']}'...")

        card_prompt = PromptTemplate.from_template(
            f"Generate a detailed Anki flashcard for the concept '{concept}' within the topic '{state['topic']}'. "
            "Fill in all relevant fields (Type, Topic, Subtopic, Title, Question, Answer, etc.) based on the concept. "
            "For question text, include a specific question. For answer, provide the concise correct answer. "
            "Include a brief explanation. "
            "If specific details like code, media, multiple choice, related concepts, or sources are applicable and you can generate them meaningfully, include them. "
            "Otherwise, omit optional fields. "
            "Strictly adhere to the following JSON format. Do not include any other text or conversational elements:\n"
            "{format_instructions}\n"
        ).partial(format_instructions=self.anki_card_parser.get_format_instructions())

        try:
            chain = card_prompt | self.llm | self.anki_card_parser
            card_dict: dict = chain.invoke({"concept": concept, "topic": state['topic']})
            card_data = AnkiCard(**card_dict)
            log.debug(f"Generated raw flashcard data for '{concept}': {card_data.model_dump_json(indent=2)}") # Use model_dump_json for Pydantic v2+

            updated_cards = state["all_generated_cards"] + [card_data]
            return {
                "concepts_for_generation": state["concepts_for_generation"],
                "all_generated_cards": updated_cards,
                "overall_process_complete": False,
                "overall_cards_generated_count": state["overall_cards_generated_count"] + 1,
                "num_cards": state["num_cards"] # Keep num_cards in state
            }
        except Exception as e:
            log.warning(f"Error generating or parsing card for '{concept}': {e}. Skipping this card.")
            # Continue with remaining concepts if parsing fails for one
            return {
                "concepts_for_generation": state["concepts_for_generation"],
                "all_generated_cards": state["all_generated_cards"],
                "overall_process_complete": False,
                "overall_cards_generated_count": state["overall_cards_generated_count"],
                "num_cards": state["num_cards"] # Keep num_cards in state
            }
        finally:
            state["concepts_for_generation"].pop(0)

    def _check_completion(self, state: FlashcardState) -> str:
        """
        Router node to determine if more concepts need processing.
        """
        if state["concepts_for_generation"]:
            return "continue"
        else:
            log.info("All flashcards generated.")
            return "finish"

    def invoke(self, input_state: Dict[str, Any], session_id: Optional[str] = None) -> FlashcardState:
        """
        Invokes the compiled LangGraph application.

        Args:
            input_state (FlashcardState): The initial state for the workflow.
            session_id (str, optional): The session ID to use for checkpointing. Defaults to None.

        Returns:
            FlashcardState: The final state of the workflow.
        """
        initial_state = {
            "topic": input_state["topic"],
            "num_cards": input_state["num_cards"],
        }

        self._log_workflow_start("FlashcardGenerator", input_state)
        log.info(f"Invoking workflow with initial state: {initial_state}")
        final_state: FlashcardState = self.workflow.invoke(
            initial_state,
            config={"configurable": {"thread_id": session_id}}
        )
        self._log_workflow_complete("FlashcardGenerator", final_state)
        return final_state
