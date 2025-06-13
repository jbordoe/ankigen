import json
import logging
import os
import re
import sqlite3
from typing import List, TypedDict

from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver

log = logging.getLogger("rich")

class SubtopicIdentificationState(TypedDict):
    """
    Represents the state of the subtopic identification workflow.
    """
    topic: str
    subtopics: List[str]
    overall_process_complete: bool
    iteration_count: int

class SubtopicIdentificationGraph:
    def __init__(
        self,
        llm_model_name: str = "gemini-2.0-flash",
        batch_size: int = 5,
        max_iterations: int = 5,
        max_subtopics: int = 10,
        deduplicate_subtopics: bool = True
    ):
        self.llm = ChatGoogleGenerativeAI(model=llm_model_name, temperature=0.7)
        self.max_iterations = max_iterations
        self.max_subtopics = max_subtopics
        self.deduplicate_subtopics = deduplicate_subtopics
        
        # Ensure checkpoints directory exists
        os.makedirs("checkpoints", exist_ok=True)
        # NB: check_same_thread=False is fine here as implementation uses a lock
        # to ensure thread safety
        conn = sqlite3.connect("checkpoints/ankigen_graph.sqlite", check_same_thread=False)
        self.checkpointer = SqliteSaver(conn)

        workflow = StateGraph(SubtopicIdentificationState)
        workflow.add_node("identify_initial_subtopics", self._identify_initial_subtopics)
        workflow.add_node("evaluate_and_suggest_more", self._evaluate_and_suggest_more)
        workflow.add_node("deduplicate_subtopics", self._deduplicate_subtopics)
        workflow.set_entry_point("identify_initial_subtopics")
        workflow.add_edge("identify_initial_subtopics", "evaluate_and_suggest_more")
        # After generating subtopics, check if more are needed
        workflow.add_conditional_edges(
            "evaluate_and_suggest_more",
            self._continue_or_end,
            {
                "continue": "evaluate_and_suggest_more",
                "end": "deduplicate_subtopics"
            }
        )
        workflow.add_edge("deduplicate_subtopics", END)
        
        self.workflow = workflow.compile(checkpointer=self.checkpointer)

    def invoke(self, input_state: SubtopicIdentificationState, session_id: str = None) -> SubtopicIdentificationState:
        """
            Invokes the iterative flashcard workflow with the given input state.
            
            Args:
                input_state (SubtopicIdentificationState): The initial state of the workflow.
                session_id (str, optional): An optional session ID to use for checkpointing. Defaults to None.

            Returns:
                SubtopicIdentificationState: The final state of the workflow.
        """

        initial_workflow_state = {
            "topic": input_state["topic"],
            "subtopics": input_state.get("subtopics", []),
            "overall_process_complete": False,
            "iteration_count": 0,
        }

        log.info(f"Starting subtopic identification workflow for topic: {initial_workflow_state['topic']}")
        final_state: SubtopicIdentificationState = self.workflow.invoke(
            initial_workflow_state,
            config={"configurable": {"thread_id": session_id}}
        )
        return final_state

    def _identify_initial_subtopics(self, state: SubtopicIdentificationState) -> SubtopicIdentificationState:
        if state.get("subtopics") and len(state["subtopics"]) > 0:
            log.info("Subtopics already loaded, Skipping initial step.")
            return state

        topic = state["topic"]
        log.info(f"Identifying subtopics for topic: {topic}")

        prompt = PromptTemplate.from_template(
            f"For the topic '{topic}', identify the initial subtopics to generate flashcards for."
            "that would be essential for learninig. Return as a JSON list of strings"
        )
        chain = prompt | self.llm | JsonOutputParser()
        try:
            subtopics = chain.invoke({"topic": topic})
                
            if not isinstance(subtopics, list):
                log.warniing(f"Unexpected output from initial subtopic identification: {subtopics}")
                subtopics = [] # Fallback to empty list if LLM fails

            log.info(f"Initial subtopics identified: {subtopics}")
            return {
                **state,
                "subtopics": subtopics,
                "iteration_count": state.get("iteration_count", 1),
                "overall_process_complete": False
            }
        except Exception as e:
            log.error(f"Error identifying initial subtopics: {e}")
            return {
                **state,
                "overall_process_complete": True, # Stop processing
            }

    def _evaluate_and_suggest_more(self, state: SubtopicIdentificationState) -> SubtopicIdentificationState:
        subtopics = state["subtopics"]
        iteration_count = state["iteration_count"]

        if state["overall_process_complete"]:
            log.info("Overall process marked complete. Ending workflow.")
            return state
        elif iteration_count >= self.max_iterations:
            log.info(f"Reached max_iterations limit ({self.max_iterations}). Forcing subtopic completion.")
            return {
                **state,
                "overall_process_complete": True,
            }
        elif len(subtopics) >= self.max_subtopics:
            log.info(f"Reached max_subtopics limit ({self.max_subtopics}). Forcing subtopic completion.")
            return {
                **state,
                "overall_process_complete": True,
            }

        log.info(f"Evaluating topic coverage for '{topic}' (Iteration {iteration_count + 1})...")

        # Provide context of what's been covered to the LLM
        # Summarize cards for context (avoiding context window limits)
        existing_context = "\n".join(subtopics[:10]) # Limit context

        prompt = PromptTemplate.from_template(
            "Topic: '{topic}'\n\n"
            "Subtopics generated so far:\n{existing_context}\n\n"
            "Has this topic been sufficiently covered for comprehensive subtopics, considering typical learning needs?\n"
            "If YES, respond STRICTLY with JSON: {{ \"status\": \"COMPLETE\" }}.\n"
            "If NO, respond STRICTLY with JSON: {{ \"status\": \"MORE_NEEDED\", \"new_subtopics\": [\"New Subtopic 1\", \"New Subtopic 2\"] }}. "
            f"Suggest {self.batch} *new, distinct* key subtopics that are still missing from a comprehensive understanding of '{topic}'.\n"
            "Do not include any other text or conversational elements in your response."
        )

        chain = prompt | self.llm | JsonOutputParser()

        try:
            llm_response = chain.invoke({"topic": topic, "existing_context": existing_context})
            status = llm_response.get("status")
            new_subtopics = llm_response.get("new_subtopics", [])
            all_subtopics = state["subtopics"] + new_subtopics

            log.info(f"LLM evaluation status: {status}, New subtopics suggested: {new_subtopics}")
                
            if status == "COMPLETE":
                return {
                    **state,
                    "overall_process_complete": True,
                    "subtopics": all_subtopics,
                }
            elif status == "MORE_NEEDED":
                return {
                    **state,
                    "overall_process_complete": False,
                    "subtopics": all_subtopics,
                }
            else:
                log.warning(f"LLM returned unexpected status: {status}. Defaulting to COMPLETE to prevent loop.")
                return {
                    **state,
                    "overall_process_complete": True,
                    "subtopics": all_subtopics,
                }

        except Exception as e:
            log.error(f"Error evaluating subtopics or parsing LLM response: {e}")
            # On error, force completion to avoid infinite loops
            return {
                **state,
                "overall_process_complete": True,
                "subtopics": all_subtopics,
            }

    def _continue_or_end(self, state: SubtopicIdentificationState) -> str:
        if state["overall_process_complete"]:
            log.info("Overall subtopic generation process complete. Ending workflow.")
            return "end"
        else:
            log.info(f"Continuing iteration {state['iteration_count']}. Current subtopics: {len(state.get('subtopics', []))}.")
            return "continue"

    def _deduplicate_subtopics(self, state: SubtopicIdentificationState) -> SubtopicIdentificationState:
        if not self.deduplicate_subtopics:
            log.info("Deduplication disabled. Skipping deduplication step.")
            return state

        subtopics = state["subtopics"]
        log.info(f"Deduplicating subtopics: {subtopics}")

        # Deduplicate subtopics
        deduplicated_subtopics = list(set(subtopics))

        log.info(f"Deduplication reduced subtopics from {len(subtopics)} to {len(deduplicated_subtopics)}.")

        return {
            **state,
            "subtopics": deduplicated_subtopics,
        }
