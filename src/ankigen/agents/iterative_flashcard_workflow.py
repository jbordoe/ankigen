import json
import logging
import os
import re
import sqlite3
from typing import List, TypedDict, Optional

from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver

from ankigen.models.anki_card import AnkiCard

log = logging.getLogger("rich")

class IterativeFlashcardState(TypedDict):
    """
    Represents the state of the flashcard generation workflow.
    """
    topic: str
    all_generated_cards: List[AnkiCard]
    concepts_to_process: List[str]
    llm_completion_status: str # Indicator from LLM: e.g., "MORE_NEEDED", "COMPLETE"
    iteration_count: int
    overall_process_complete: bool
    cards_per_iteration: int
    max_cards: int
    max_iterations: int

class IterativeFlashcardGenerator:
    def __init__(self, llm_model_name: str = "gemini-2.0-flash", include_categories: bool = False):
        self.llm = ChatGoogleGenerativeAI(model=llm_model_name, temperature=0.7)
        self.anki_card_parser = JsonOutputParser(pydantic_object=AnkiCard)

        self.include_categories = include_categories
        # Ensure checkpoints directory exists
        os.makedirs("checkpoints", exist_ok=True)
        # NB: check_same_thread=False is fine here as implementation uses a lock
        # to ensure thread safety
        conn = sqlite3.connect("checkpoints/ankigen_graph.sqlite", check_same_thread=False)
        self.checkpointer = SqliteSaver(conn)
        self.workflow = self._compile_workflow()

    def _compile_workflow(self):
        if self.include_categories:
            pass
        else:
            workflow = self._compile_simple_workflow()

        return workflow.compile(checkpointer=self.checkpointer)

    def _compile_simple_workflow(self):
        workflow = StateGraph(IterativeFlashcardState)

        workflow.add_node("identify_initial_concepts", self._identify_initial_concepts)
        workflow.add_node("generate_cards_for_concepts", self._generate_cards_for_concepts)
        workflow.add_node("evaluate_and_suggest_more", self._evaluate_and_suggest_more)
        workflow.set_entry_point("identify_initial_concepts")
        workflow.add_edge("identify_initial_concepts", "generate_cards_for_concepts")
        workflow.add_edge("generate_cards_for_concepts", "evaluate_and_suggest_more")
        # After generating cards, check if more cards are needed
        workflow.add_conditional_edges(
            "evaluate_and_suggest_more",
            self._route_on_concept_status,
            {
                "continue_iteration": "generate_cards_for_concepts",
                "end_process": END
            }
        )
        return workflow

    # Generate inital batch of concepts for given topic
    def _identify_initial_concepts(self, state: IterativeFlashcardState) -> IterativeFlashcardState:
        if state.get("concepts_to_process") and len(state["concepts_to_process"]) > 0:
            log.info(f"Concepts already loaded, Skipping initial step.")
            return state

        topic = state["topic"]
        log.info(f"Identifying initial concepts for topic: {topic}")

        prompt = PromptTemplate.from_template(
            f"For the topic '{topic}', identify the initial concepts to generate flashcards for."
            "that would be essential for learninig. Return as a JSON list of strings"
        )
        chain = prompt | self.llm | JsonOutputParser()

        try:
            concepts = chain.invoke({"topic": topic})
            if not isinstance(concepts, list):
                log.warniing(f"Unexpected output from initial concept identification: {concepts}")
                concepts = [] # Fallback to empty list if LLM fails

            log.info(f"Initial concepts identified: {concepts}")
            return {
                **state, # Carry over any other state
                "concepts_to_process": concepts,
                "all_generated_cards": [],
                "llm_completion_status": "MORE_NEEDED",
                "iteration_count": 0,
                "overall_process_complete": False
            }
        except Exception as e:
            log.error(f"Error identifying initial concepts: {e}")
            return {
                **state,
                "overall_process_complete": True, # Stop processing
            }

    def _generate_cards_for_concepts(self, state: IterativeFlashcardState) -> IterativeFlashcardState:
        concepts_to_process = state["concepts_to_process"]
        all_generated_cards = state["all_generated_cards"]
        cards_per_iteration = state["cards_per_iteration"]
        max_cards = state.get("max_cards", 100)

        if not concepts_to_process:
            log.info(f"No more concepts to process, stopping.")
            return state

        batch_concepts = concepts_to_process[:cards_per_iteration]
        remaining_concepts = concepts_to_process[cards_per_iteration:]

        log.info(f"Generating cards for concepts: {batch_concepts}")

        prompt_template = PromptTemplate.from_template(
            "For the topic '{topic}', generate Anki flashcards for the following concepts:\n"
            "{concepts_json}\n\n"
            "For each concept, fill in all relevant fields (Type, Topic, Subtopic, Title, Question, Answer, Explanation, etc.) based on the concept. "
            "For question text, include a specific question. For answer, provide the concise correct answer. "
            "For phrases or spoken language fragments it's fine to just use the phrase and have the answer be the translation."
            "If specific details like code, media, multiple choice, related concepts, or sources are applicable and you can generate them meaningfully, include them. "
            "Otherwise, omit optional fields. "
            "Generate as many cards as possible for the provided concepts, avoiding truncation or repetition.\n"
            "Strictly adhere to the following JSON array format. Do not include any other text or conversational elements:\n"
            "[\n  {{ 'Type': 'Basic', 'Topic': '...', ... }},\n  {{ 'Type': 'Basic', 'Topic': '...', ... }}\n]\n"
            "{format_instructions}\n"
        ).partial(format_instructions=self.anki_card_parser.get_format_instructions())

        class AnkiCardList(TypedDict):
            cards: List[AnkiCard]

        try:
            raw_cards_output = self.llm.invoke(
                prompt_template.format(
                    topic=state["topic"],
                    concepts_json=json.dumps(batch_concepts)
                )
            ).content

            # Remove markdown code blocks wrapping the output
            # This is a hacky workaround for the current issue with the LLM output parser
            raw_cards_output = re.sub(r"^```(json)?\n", "", raw_cards_output)
            raw_cards_output = re.sub(r"```$", "", raw_cards_output)

            # Attempt to parse as a list of dicts, then validate against AnkiCard
            parsed_raw_cards = json.loads(raw_cards_output)
            generated_anki_cards = []
            for card_dict in parsed_raw_cards:
                try:
                    generated_anki_cards.append(AnkiCard(**card_dict))
                except Exception as card_e:
                    log.warning(f"Failed to parse individual card: {card_e} - {card_dict}")

            # TODO: deduplicate generated cards
            # Check max_cards limit
            final_cards_list = all_generated_cards + generated_anki_cards
            if len(final_cards_list) >= max_cards:
                log.info(f"Reached max_cards limit ({max_cards}). Setting overall_process_complete to True.")
                return {
                    **state,
                    "concepts_to_process": [], # Clear remaining concepts
                    "all_generated_cards": final_cards_list[:max_cards], # Truncate to max_cards
                    "overall_process_complete": True
                }

            return {
                **state,
                "concepts_to_process": remaining_concepts, # Concepts not yet processed in this batch
                "all_generated_cards": final_cards_list
            }

        except Exception as e:
            log.error(f"Error generating cards in bulk: {e}. Raw output: {raw_cards_output[:500] if 'raw_cards_output' in locals() else 'N/A'}")
            # If an error occurs, clear concepts for this iteration to prevent re-processing faulty ones
            # and potentially try to proceed to evaluation for a new concept suggestion.
            return {
                **state,
                "concepts_to_process": remaining_concepts,
                # TODO: handle error in state
            }

    def _evaluate_and_suggest_more(self, state: IterativeFlashcardState) -> IterativeFlashcardState:
        """
        Asks the LLM to evaluate the current coverage of the topic and suggest more concepts if needed.
        Also manages iteration limits.
        """
        topic = state["topic"]
        all_generated_cards = state.get("all_generated_cards", [])
        iteration_count = state.get("iteration_count", 0)
        max_iterations = state.get("max_iterations", 5) # Default if not set
        max_cards = state.get("max_cards", 100) # Default if not set
        concepts_to_process = state.get("concepts_to_process", [])

        # Check for immediate completion conditions
        if len(all_generated_cards) >= max_cards:
            log.info(f"Already reached max_cards limit ({max_cards}). Marking process complete.")
            return {
                **state,
                "llm_completion_status": "COMPLETE_CONCEPTS", # Indicate concepts are done
                "overall_process_complete": True,
                "concepts_to_process": [] # Clear any remaining concepts
            }
        
        if iteration_count >= max_iterations:
            log.info(f"Reached max_iterations limit ({max_iterations}). Forcing concept completion.")
            return {
                **state,
                "llm_completion_status": "COMPLETE_CONCEPTS", # Indicate concepts are done
                "overall_process_complete": True,
                "concepts_to_process": [] # Clear any remaining concepts
            }

        # If there are still concepts from the previous generation batch that haven't been processed yet,
        # we don't need to ask the LLM for more concepts. Just route to process them.
        if concepts_to_process:
            log.info(f"Still {len(concepts_to_process)} concepts remaining from previous batch. Skipping LLM evaluation for now.")
            return {
                **state,
                "llm_completion_status": "MORE_NEEDED", # Keep status as more needed
                "iteration_count": iteration_count + 1 # Increment for this pass
            }


        log.info(f"Evaluating topic coverage for '{topic}' (Iteration {iteration_count + 1})...")

        # Provide context of what's been covered to the LLM
        # Summarize cards for context (avoiding context window limits)
        card_summaries = [f"- {card.front.question.question[:50]}..." for card in all_generated_cards[:10]] # Limit context
        existing_context = "\n".join(card_summaries) if card_summaries else "No cards generated yet."
        if len(all_generated_cards) > 10:
            existing_context += f"\n... (and {len(all_generated_cards) - 10} more cards)"

        prompt = PromptTemplate.from_template(
            "Topic: '{topic}'\n\n"
            "Flashcards generated so far:\n{existing_context}\n\n"
            "Has this topic been sufficiently covered for comprehensive flashcards, considering typical learning needs?\n"
            "If YES, respond STRICTLY with JSON: {{ \"status\": \"COMPLETE\" }}.\n"
            "If NO, respond STRICTLY with JSON: {{ \"status\": \"MORE_NEEDED\", \"new_concepts\": [\"New Concept 1\", \"New Concept 2\"] }}. "
            "Suggest 2-3 *new, distinct* key concepts that are still missing from a comprehensive understanding of '{topic}'.\n"
            "Do not include any other text or conversational elements in your response."
        )

        chain = prompt | self.llm | JsonOutputParser()

        try:
            llm_response = chain.invoke({"topic": topic, "existing_context": existing_context})
            status = llm_response.get("status")
            new_concepts = llm_response.get("new_concepts", [])

            log.info(f"LLM evaluation status: {status}, New concepts suggested: {new_concepts}")

            if status == "COMPLETE":
                return {
                    **state,
                    "llm_completion_status": "COMPLETE_CONCEPTS",
                    "concepts_to_process": [], # No more concepts needed
                    "overall_process_complete": True,
                    "iteration_count": iteration_count + 1
                }
            elif status == "MORE_NEEDED":
                return {
                    **state,
                    "llm_completion_status": "MORE_NEEDED",
                    "concepts_to_process": new_concepts, # Add newly suggested concepts
                    "iteration_count": iteration_count + 1
                }
            else:
                log.warning(f"LLM returned unexpected status: {status}. Defaulting to COMPLETE_CONCEPTS to prevent loop.")
                return {
                    **state,
                    "llm_completion_status": "COMPLETE_CONCEPTS",
                    "concepts_to_process": [],
                    "overall_process_complete": True,
                    "iteration_count": iteration_count + 1
                }

        except Exception as e:
            log.error(f"Error evaluating concepts or parsing LLM response: {e}")
            # On error, force completion to avoid infinite loops
            return {
                **state,
                "llm_completion_status": "COMPLETE_CONCEPTS",
                "concepts_to_process": [],
                "overall_process_complete": True,
                "iteration_count": iteration_count + 1
            }

    # --- Router Node for Concept Loop ---
    def _route_on_concept_status(self, state: IterativeFlashcardState) -> str:
        """
        Determines the next step based on the LLM's concept completion status
        and other limits (max_iterations, max_cards).
        """
        # Prioritize overall completion (e.g., if max_cards was hit during card generation)
        if state.get("overall_process_complete", False):
            log.info("Overall process marked complete. Ending workflow.")
            return "end_process"

        # Check if LLM indicated completion or if limits are reached
        if state["llm_completion_status"] == "COMPLETE_CONCEPTS" or \
           state["iteration_count"] >= state["max_iterations"] or \
           len(state["all_generated_cards"]) >= state["max_cards"]:
            log.info("Concept generation complete or limits reached. Ending workflow.")
            return "end_process"
        else:
            # If LLM still needs more concepts AND concepts_to_process from last evaluation is empty (meaning they were processed)
            # OR if llm_completion_status is MORE_NEEDED AND concepts_to_process is still populated (meaning more cards need to be generated for them)
            # Route back to generate more cards.
            if state["llm_completion_status"] == "MORE_NEEDED" and \
               (len(state.get("concepts_to_process", [])) > 0 or state["iteration_count"] < state["max_iterations"]):
                log.info(f"Continuing iteration. Remaining concepts: {len(state.get('concepts_to_process', []))}, Iteration: {state['iteration_count']}/{state['max_iterations']}")
                return "continue_iteration"
            else:
                log.info("No more concepts or conditions to continue iteration. Ending process.")
                return "end_process"

    def invoke(self, input_state: IterativeFlashcardState, session_id: str = None) -> IterativeFlashcardState:
        """
            Invokes the iterative flashcard workflow with the given input state.

            Args:
                input_state (IterativeFlashcardState): The initial state of the workflow.
                session_id (str, optional): An optional session ID to use for checkpointing. Defaults to None.

            Returns:
                IterativeFlashcardState: The final state of the workflow.
            """

        initial_workflow_state = {
            "topic": input_state["topic"],
            "max_cards": input_state.get("max_cards", 100),
            "max_iterations": input_state.get("max_iterations", 5),
            "cards_per_iteration": input_state.get("cards_per_iteration", 5),            
            "all_generated_cards": [],
            "concepts_to_process": [],
            "llm_completion_status": "", # Will be set by first node
            "iteration_count": 0,
            "overall_process_complete": False,
        }

        log.info(f"Starting iterative flashcard workflow for topic: {initial_workflow_state['topic']}")
        final_state: IterativeFlashcardState = self.workflow.invoke(
            initial_workflow_state,
            config={"configurable": {"thread_id": session_id}}
        )
        return final_state
