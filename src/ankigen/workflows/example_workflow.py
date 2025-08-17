import json
import logging
import os
from typing import Dict, Any, List, Optional
from pathlib import Path

from ankigen.models.anki_card import AnkiCard

log = logging.getLogger("rich")


class ExampleWorkflow:
    """
    Simple workflow for loading domain-specific examples to improve card generation.
    Supports explicit domain loading or zero-shot (no examples).
    """
    
    def __init__(self, examples_dir: str = "examples"):
        """
        Initialize the ExampleWorkflow.
        
        Args:
            examples_dir: Path to examples directory (relative to project root)
        """
        self.examples_dir = Path(examples_dir)
        
    def load_examples(self, domain: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Load examples for the specified domain or return empty list for zero-shot.
        
        Args:
            domain: Domain name (e.g., 'language', 'programming') or None for zero-shot
            
        Returns:
            List of example card dictionaries, empty list if domain not found or None
        """
        if domain is None:
            log.info("No domain specified - using zero-shot prompting")
            return []
            
        domain_file = self.examples_dir / "domains" / f"{domain}.json"
        
        if not domain_file.exists():
            log.warning(f"Domain file not found: {domain_file}. Using zero-shot prompting.")
            return []
            
        try:
            with open(domain_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                examples = data.get("examples", [])
                log.info(f"Loaded {len(examples)} examples for domain: {domain}")
                return examples
        except Exception as e:
            log.error(f"Error loading examples from {domain_file}: {e}")
            return []
    
    def format_examples_for_prompt(self, examples: List[Dict[str, Any]], max_examples: int = 3) -> str:
        """
        Format examples into a string suitable for few-shot prompting.
        
        Args:
            examples: List of example card dictionaries
            max_examples: Maximum number of examples to include in prompt
            
        Returns:
            JSON string with examples, empty string if no examples
        """
        if not examples:
            return ""
            
        # Limit number of examples to avoid prompt length issues
        selected_examples = examples[:max_examples]
        
        try:
            return json.dumps(selected_examples, indent=2)
        except Exception as e:
            log.error(f"Error formatting examples as JSON: {e}")
            return ""
    
    def get_example_json_format(self, examples: List[Dict[str, Any]]) -> str:
        """
        Extract JSON format instructions from examples for consistent output.
        
        Args:
            examples: List of example card dictionaries
            
        Returns:
            JSON format string showing expected structure
        """
        if not examples:
            return ""
            
        # Use first example as template, but remove content to show structure
        template = examples[0].copy()
        
        # Replace content with placeholders to show structure
        if 'front_question_text' in template:
            template['front_question_text'] = "Your question here"
        if 'back_answer' in template:
            template['back_answer'] = "Your answer here"
        if 'back_explanation' in template:
            template['back_explanation'] = "Your explanation here"
        if 'topic' in template:
            template['topic'] = "Topic name"
        if 'subtopic' in template:
            template['subtopic'] = "Subtopic name"
            
        try:
            return json.dumps(template, indent=2)
        except Exception as e:
            log.warning(f"Error creating JSON format template: {e}")
            return ""
    
    def validate_examples(self, examples: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Validate that examples conform to AnkiCard model structure.
        
        Args:
            examples: Raw example dictionaries
            
        Returns:
            List of validated examples (invalid ones are filtered out)
        """
        validated_examples = []
        
        for i, example in enumerate(examples):
            try:
                # Try to create AnkiCard to validate structure
                AnkiCard(**example)
                validated_examples.append(example)
            except Exception as e:
                log.warning(f"Example {i+1} failed validation: {e}")
                continue
                
        log.info(f"Validated {len(validated_examples)}/{len(examples)} examples")
        return validated_examples
    
    def list_available_domains(self) -> List[str]:
        """
        List all available domain files.
        
        Returns:
            List of domain names (without .json extension)
        """
        domains_dir = self.examples_dir / "domains"
        if not domains_dir.exists():
            return []
            
        domain_files = []
        for file_path in domains_dir.glob("*.json"):
            domain_files.append(file_path.stem)
            
        return sorted(domain_files)
