import logging
import os
import sqlite3
from typing import List, TypedDict, Optional

from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver

from ankigen.models.anki_card import AnkiCard

log = logging.getLogger("rich")

class FlashcardState(TypedDict):
    """
    Represents the state of the flashcard generation workflow.
    `num_cards` is now part of the state, passed at invocation.
    """
    topic: str
    num_cards: int
    overall_cards_generated_count: int
    concepts_for_generation: List[str]
    all_generated_cards: List[AnkiCard] # Stores AnkiCard Pydantic objects
    overall_process_complete: bool

class FlashcardGenerator:
    """
    A class to encapsulate the LangGraph workflow for generating Anki flashcards.
    Allows for parameterization of the LLM model.
    The number of cards is now passed per invocation.
    """
    def __init__(self, llm_model_name: str = "gemini-2.0-flash"):
        self.llm = ChatGoogleGenerativeAI(model=llm_model_name, temperature=0.7)
        self.anki_card_parser = JsonOutputParser(pydantic_object=AnkiCard)

        # Ensure checkpoints directory exists
        os.makedirs("checkpoints", exist_ok=True)
        # NB: check_same_thread=False is fine here as implementation uses a lock
        # to ensure thread safety
        conn = sqlite3.connect("checkpoints/ankigen_graph.sqlite", check_same_thread=False)
        self.checkpointer = SqliteSaver(conn)
        self.workflow = self._compile_workflow()

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

    def invoke(self, input_state: FlashcardState, session_id: str = None) -> FlashcardState:
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

        log.info(f"Invoking workflow with initial state: {initial_state}")
        final_state: FlashcardState = self.workflow.invoke(
            initial_state,
            config={"configurable": {"thread_id": session_id}}
        )
        return final_state
