"""
Intent Analysis Service for parsing natural language learning requests.

This service uses LLMs to understand user intent and convert natural language
into structured learning plans for flashcard generation.
"""

import json
import re
import os
from typing import List, Optional, Dict, Any, Union

from langchain.schema import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

try:
    from langchain_google_genai import ChatGoogleGenerativeAI
except ImportError:
    ChatGoogleGenerativeAI = None

try:
    from langchain_anthropic import ChatAnthropic
except ImportError:
    ChatAnthropic = None

from ..models.learning_intent import (
    LearningIntent, 
    GenerationPlan, 
    FocusAreaBreakdown,
    DifficultyLevel, 
    TimeConstraint,
    ParsedComponents
)


class IntentAnalysisResult(BaseModel):
    """Structured result from LLM intent analysis."""
    
    topic: str = Field(description="Main learning topic")
    domain: Optional[str] = Field(description="Learning domain (language, programming, science, etc.)")
    subject_area: Optional[str] = Field(description="Broad subject category")
    
    # Inferred parameters
    difficulty_level: Optional[str] = Field(description="beginner, elementary, intermediate, upper_intermediate, advanced, expert")
    time_constraint: Optional[str] = Field(description="quick_review, standard, comprehensive, intensive") 
    estimated_cards: int = Field(description="Suggested number of cards (1-100)", default=20, ge=1, le=100)
    
    # Learning focus
    focus_areas: List[str] = Field(description="Areas of focus like vocabulary, grammar, concepts, examples")
    specific_skills: List[str] = Field(description="Specific skills to develop")
    use_case: Optional[str] = Field(description="Context of use: travel, business, academic, hobby, etc.")
    
    # Distribution strategy
    card_breakdown: Dict[str, int] = Field(description="How many cards for each focus area")
    
    # Reasoning
    reasoning: str = Field(description="Explanation of the analysis and plan")
    confidence: float = Field(description="Confidence in analysis (0.0-1.0)", default=0.7)


class IntentAnalyzer:
    """Service for analyzing natural language learning intent using LLMs."""
    
    def __init__(self, llm: Optional[Union[ChatGoogleGenerativeAI, ChatAnthropic]] = None, provider: str = "google"):
        """
        Initialize the intent analyzer with specified LLM provider.
        
        Args:
            llm: Pre-configured LLM instance (optional)
            provider: LLM provider ("google" for Gemini, "anthropic" for Claude)
        """
        if llm is not None:
            self.llm = llm
        else:
            self.llm = self._create_llm(provider)
    
    def _create_llm(self, provider: str) -> Union[ChatGoogleGenerativeAI, ChatAnthropic]:
        """Create LLM instance based on provider choice."""
        if provider.lower() == "anthropic" or provider.lower() == "claude":
            if ChatAnthropic is None:
                raise ImportError("langchain-anthropic is required for Claude. Install with: uv add langchain-anthropic")
            
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY environment variable is required for Claude")
            
            return ChatAnthropic(
                model="claude-3-5-sonnet-20241022",
                temperature=0.3,
                api_key=api_key
            )
        
        elif provider.lower() == "google" or provider.lower() == "gemini":
            if ChatGoogleGenerativeAI is None:
                raise ImportError("langchain-google-genai is required for Gemini. Install with: uv add langchain-google-genai")
            
            api_key = os.getenv("GOOGLE_API_KEY")
            if not api_key:
                raise ValueError("GOOGLE_API_KEY environment variable is required for Gemini")
            
            return ChatGoogleGenerativeAI(
                model="gemini-1.5-flash",
                temperature=0.3,
                google_api_key=api_key
            )
        
        else:
            raise ValueError(f"Unsupported provider: {provider}. Use 'google' or 'anthropic'")
    
    def analyze_intent(self, user_input: str) -> LearningIntent:
        """
        Parse natural language input into structured learning intent.
        
        Args:
            user_input: Raw user input like "I want to learn Spanish cooking vocabulary"
            
        Returns:
            LearningIntent with parsed and inferred parameters
        """
        # Get structured analysis from LLM
        analysis_result = self._llm_analyze(user_input)
        
        # Convert to LearningIntent
        intent = self._convert_to_learning_intent(user_input, analysis_result)
        
        return intent
    
    def create_generation_plan(self, intent: LearningIntent) -> GenerationPlan:
        """
        Create a concrete generation plan from learning intent.
        
        Args:
            intent: Parsed learning intent
            
        Returns:
            GenerationPlan with specific execution details
        """
        # Create breakdown from intent focus areas
        breakdown = []
        total_cards = intent.estimated_cards
        
        if intent.focus_areas:
            # Distribute cards across focus areas
            area_count = len(intent.focus_areas)
            base_cards = total_cards // area_count
            remaining = total_cards % area_count
            
            for i, area in enumerate(intent.focus_areas):
                cards = base_cards + (1 if i < remaining else 0)
                percentage = round((cards / total_cards) * 100)
                
                breakdown.append(FocusAreaBreakdown(
                    area_name=area,
                    card_count=cards,
                    percentage=percentage,
                    description=self._get_area_description(area, intent.subject_area)
                ))
        else:
            # Default breakdown for concepts
            breakdown.append(FocusAreaBreakdown(
                area_name="concepts",
                card_count=total_cards,
                percentage=100,
                description="Core concepts and knowledge"
            ))
        
        # Determine template based on complexity
        template = "comprehensive" if total_cards > 30 else "basic"
        
        # Generate reasoning
        reasoning = self._generate_reasoning(intent, breakdown)
        confidence_explanation = self._generate_confidence_explanation(intent)
        
        return GenerationPlan(
            total_cards=total_cards,
            workflow="iterative",
            template=template,
            domain=intent.domain,
            breakdown=breakdown,
            reasoning=reasoning,
            confidence_explanation=confidence_explanation,
            original_intent=intent
        )
    
    def _llm_analyze(self, user_input: str) -> IntentAnalysisResult:
        """Use LLM to analyze user intent and return structured result."""
        
        system_prompt = """You are an expert learning analyst. Your job is to understand what a user wants to learn from their natural language input and create a structured learning plan.

Analyze the user's input and extract:
1. The main topic they want to learn
2. The domain/subject area (language, programming, science, history, etc.)
3. Their likely skill level (beginner to expert)
4. How much they want to learn (quick review to intensive study)
5. What aspects they want to focus on (vocabulary, concepts, practical skills, etc.)
6. The context of their learning (travel, work, academic, hobby)

Then propose a flashcard generation strategy:
- How many cards total (MAXIMUM 100 cards due to system limits)
- What percentage should focus on different areas
- Why this breakdown makes sense

Be specific and practical. If the input is vague, make reasonable assumptions and explain your reasoning.
IMPORTANT: Never suggest more than 100 total cards.

Respond with valid JSON matching this schema:
{
  "topic": "string - the main learning topic",
  "domain": "string - language/programming/science/etc or null",
  "subject_area": "string - broader category or null", 
  "difficulty_level": "string - beginner/elementary/intermediate/upper_intermediate/advanced/expert or null",
  "time_constraint": "string - quick_review/standard/comprehensive/intensive or null",
  "estimated_cards": "number - suggested total cards",
  "focus_areas": ["array of focus areas like vocabulary, grammar, concepts"],
  "specific_skills": ["array of specific skills to develop"],
  "use_case": "string - travel/business/academic/hobby/etc or null",
  "card_breakdown": {"focus_area": number_of_cards},
  "reasoning": "string - explanation of analysis and plan",
  "confidence": "number - 0.0 to 1.0"
}"""

        user_prompt = f"Analyze this learning request: '{user_input}'"
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]
        
        response = self.llm.invoke(messages)
        
        try:
            # Extract JSON from response
            json_match = re.search(r'\{.*\}', response.content, re.DOTALL)
            if json_match:
                json_data = json.loads(json_match.group())
                return IntentAnalysisResult(**json_data)
            else:
                raise ValueError("No JSON found in LLM response")
                
        except (json.JSONDecodeError, ValueError) as e:
            # Fallback for parsing errors
            return self._create_fallback_analysis(user_input)
    
    def _convert_to_learning_intent(self, user_input: str, analysis: IntentAnalysisResult) -> LearningIntent:
        """Convert LLM analysis result to LearningIntent model."""
        
        # Convert string enums to enum values
        difficulty = None
        if analysis.difficulty_level:
            try:
                difficulty = DifficultyLevel(analysis.difficulty_level.lower())
            except ValueError:
                pass
                
        time_constraint = None
        if analysis.time_constraint:
            try:
                time_constraint = TimeConstraint(analysis.time_constraint.lower())
            except ValueError:
                pass
        
        return LearningIntent(
            topic=analysis.topic,
            raw_input=user_input,
            domain=analysis.domain,
            estimated_cards=analysis.estimated_cards,
            focus_areas=analysis.focus_areas,
            difficulty_level=difficulty,
            time_constraint=time_constraint,
            subject_area=analysis.subject_area,
            specific_skills=analysis.specific_skills,
            use_case=analysis.use_case,
            confidence_score=analysis.confidence
        )
    
    def _create_fallback_analysis(self, user_input: str) -> IntentAnalysisResult:
        """Create fallback analysis when LLM parsing fails."""
        
        # Simple keyword-based analysis
        input_lower = user_input.lower()
        
        # Extract topic (everything after common phrases)
        topic = user_input
        for phrase in ["i want to learn", "help me learn", "teach me", "study"]:
            if phrase in input_lower:
                topic = user_input[input_lower.find(phrase) + len(phrase):].strip()
                break
        
        # Guess domain
        domain = None
        if any(word in input_lower for word in ["language", "spanish", "french", "german", "chinese", "japanese"]):
            domain = "language"
        elif any(word in input_lower for word in ["programming", "coding", "python", "javascript", "java"]):
            domain = "programming"
        elif any(word in input_lower for word in ["science", "physics", "chemistry", "biology"]):
            domain = "science"
        
        return IntentAnalysisResult(
            topic=topic,
            domain=domain,
            estimated_cards=20,
            focus_areas=["concepts"],
            card_breakdown={"concepts": 20},
            reasoning="Fallback analysis due to parsing error. Using basic assumptions.",
            confidence=0.3
        )
    
    def _get_area_description(self, area: str, subject_area: Optional[str]) -> str:
        """Generate description for focus area."""
        descriptions = {
            "vocabulary": "Key terms and their meanings",
            "grammar": "Rules and structure",
            "concepts": "Core ideas and principles", 
            "examples": "Practical examples and applications",
            "syntax": "Correct usage and formatting",
            "theory": "Theoretical foundations",
            "practical": "Hands-on applications"
        }
        
        base_desc = descriptions.get(area.lower(), f"{area.title()} content")
        
        if subject_area:
            return f"{base_desc} for {subject_area}"
        return base_desc
    
    def _generate_reasoning(self, intent: LearningIntent, breakdown: List[FocusAreaBreakdown]) -> str:
        """Generate human-readable reasoning for the plan."""
        lines = [
            f"Based on your request to learn '{intent.topic}', I've designed a {intent.estimated_cards}-card study plan."
        ]
        
        if intent.difficulty_level:
            lines.append(f"The {intent.difficulty_level.value} level suggests a balanced approach.")
        
        if intent.use_case and intent.use_case != "null":
            lines.append(f"Since this is for {intent.use_case}, I've focused on practical knowledge.")
        
        return " ".join(lines)
    
    def _generate_confidence_explanation(self, intent: LearningIntent) -> str:
        """Generate explanation of confidence level."""
        score = intent.confidence_score
        
        if score >= 0.8:
            return "High confidence - clear topic and learning goals identified."
        elif score >= 0.6:
            return "Good confidence - some assumptions made based on context."
        elif score >= 0.4:
            return "Moderate confidence - used common patterns to infer goals."
        else:
            return "Lower confidence - limited information, used basic defaults."
