import logging
from typing import List, Dict, Any

from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_google_genai import ChatGoogleGenerativeAI

log = logging.getLogger("rich")


class ConceptGenerator:
    """
    Reusable component for generating concepts and subtopics from topics.
    Supports different generation strategies for various workflow needs.
    """
    
    def __init__(self, llm: ChatGoogleGenerativeAI):
        self.llm = llm
        self.json_parser = JsonOutputParser()
    
    def generate_flat_concepts(self, topic: str, num_concepts: int) -> List[str]:
        """
        Generate a flat list of concepts for a given topic.
        
        Args:
            topic: The topic to generate concepts for
            num_concepts: Number of concepts to generate
            
        Returns:
            List[str]: List of concept strings
        """
        log.info(f"Generating {num_concepts} flat concepts for topic: {topic}")
        
        prompt = PromptTemplate.from_template(
            f"For the topic '{topic}', list {num_concepts} distinct and important concepts or sub-topics "
            "that are essential for learning. "
            "Return the concepts as a comma-separated list, e.g., 'Concept A, Concept B, Concept C'. "
            "Do not add any other text."
        )
        
        response_str = self.llm.invoke(prompt.format(topic=topic)).content
        concepts = [c.strip() for c in response_str.split(',') if c.strip()]
        
        log.info(f"Generated concepts: {concepts}")
        return concepts
    
    def generate_hierarchical_subtopics(self, topic: str, max_depth: int = 2) -> Dict[str, Any]:
        """
        Generate a hierarchical structure of subtopics for a given topic.
        
        Args:
            topic: The main topic to break down
            max_depth: Maximum depth of subtopic hierarchy
            
        Returns:
            Dict[str, Any]: Hierarchical structure of subtopics
        """
        log.info(f"Generating hierarchical subtopics for topic: {topic} (max_depth: {max_depth})")
        
        prompt = PromptTemplate.from_template(
            f"For the topic '{topic}', create a hierarchical breakdown of subtopics for comprehensive learning. "
            "Structure it as a JSON object with main subtopics as keys and their sub-concepts as arrays. "
            "Limit to {max_depth} levels of nesting. "
            "Example format: {{'Subtopic 1': ['concept1', 'concept2'], 'Subtopic 2': ['concept3', 'concept4']}} "
            "Return only valid JSON, no other text."
        )
        
        chain = prompt | self.llm | self.json_parser
        
        try:
            subtopic_structure = chain.invoke({"topic": topic, "max_depth": max_depth})
            log.info(f"Generated subtopic structure: {subtopic_structure}")
            return subtopic_structure
        except Exception as e:
            log.error(f"Error generating hierarchical subtopics: {e}")
            # Fallback to flat structure
            return {"General Concepts": self.generate_flat_concepts(topic, 5)}
    
    def suggest_additional_concepts(self, topic: str, existing_concepts: List[str], num_suggestions: int = 3) -> List[str]:
        """
        Suggest additional concepts that are missing from the current set.
        
        Args:
            topic: The main topic
            existing_concepts: Concepts already covered
            num_suggestions: Number of new concepts to suggest
            
        Returns:
            List[str]: List of suggested new concepts
        """
        log.info(f"Suggesting {num_suggestions} additional concepts for topic: {topic}")
        
        existing_summary = ", ".join(existing_concepts[:10])  # Limit context
        if len(existing_concepts) > 10:
            existing_summary += f" (and {len(existing_concepts) - 10} more)"
        
        prompt = PromptTemplate.from_template(
            f"Topic: '{topic}'\n"
            f"Concepts already covered: {existing_summary}\n\n"
            f"Suggest {num_suggestions} NEW, distinct concepts that are important for understanding '{topic}' "
            "but are NOT covered by the existing concepts. "
            "Return as a JSON array of strings. No other text."
        )
        
        chain = prompt | self.llm | self.json_parser
        
        try:
            new_concepts = chain.invoke({"topic": topic, "existing_summary": existing_summary})
            if isinstance(new_concepts, list):
                log.info(f"Suggested new concepts: {new_concepts}")
                return new_concepts
            else:
                log.warning(f"Unexpected response format: {new_concepts}")
                return []
        except Exception as e:
            log.error(f"Error suggesting additional concepts: {e}")
            return []
    
    def assess_topic_complexity(self, topic: str) -> Dict[str, Any]:
        """
        Assess the complexity of a topic to help determine appropriate workflow strategy.
        
        Args:
            topic: The topic to assess
            
        Returns:
            Dict[str, Any]: Assessment results including complexity score and recommendations
        """
        log.info(f"Assessing complexity for topic: {topic}")
        
        prompt = PromptTemplate.from_template(
            f"Analyze the topic '{topic}' and assess its learning complexity. "
            "Return a JSON object with: "
            "- 'complexity_score': integer 1-5 (1=simple, 5=very complex) "
            "- 'breadth': 'narrow' or 'broad' "
            "- 'depth_required': 'shallow', 'medium', or 'deep' "
            "- 'recommended_approach': 'single_topic', 'topic_with_subtopics', or 'multi_deck' "
            "- 'estimated_cards': integer estimate of total cards needed "
            "No other text."
        )
        
        chain = prompt | self.llm | self.json_parser
        
        try:
            assessment = chain.invoke({"topic": topic})
            log.info(f"Topic complexity assessment: {assessment}")
            return assessment
        except Exception as e:
            log.error(f"Error assessing topic complexity: {e}")
            # Fallback assessment
            return {
                "complexity_score": 3,
                "breadth": "medium", 
                "depth_required": "medium",
                "recommended_approach": "topic_with_subtopics",
                "estimated_cards": 20
            }