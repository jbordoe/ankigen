"""
Plan Presentation Service for displaying generation plans to users.

Provides clear, formatted output for user confirmation before starting
flashcard generation from natural language intent.
"""

from typing import Dict, Any, Optional
from ..models.learning_intent import GenerationPlan, LearningIntent


class PlanPresenter:
    """Service for presenting generation plans to users in a clear format."""
    
    @staticmethod
    def format_plan_summary(plan: GenerationPlan) -> str:
        """
        Create a formatted summary of the generation plan for user confirmation.
        
        Args:
            plan: The generation plan to format
            
        Returns:
            Formatted string suitable for CLI or GUI display
        """
        lines = []
        
        # Header
        lines.append("=" * 60)
        lines.append("📚 FLASHCARD GENERATION PLAN")
        lines.append("=" * 60)
        
        # Basic info
        lines.append(f"Topic: {plan.original_intent.topic}")
        lines.append(f"Total Cards: {plan.total_cards}")
        lines.append(f"Template: {plan.template}")
        
        if plan.domain:
            lines.append(f"Domain: {plan.domain}")
            
        if plan.original_intent.difficulty_level:
            lines.append(f"Level: {plan.original_intent.difficulty_level.value}")
            
        if plan.original_intent.use_case:
            lines.append(f"Use Case: {plan.original_intent.use_case}")
        
        lines.append("")
        
        # Card breakdown
        lines.append("📊 CARD BREAKDOWN:")
        lines.append("-" * 30)
        
        for area in plan.breakdown:
            lines.append(f"  • {area.area_name.title()}: {area.card_count} cards ({area.percentage}%)")
            lines.append(f"    {area.description}")
        
        lines.append("")
        
        # Reasoning
        lines.append("🤔 REASONING:")
        lines.append("-" * 30)
        lines.append(plan.reasoning)
        lines.append("")
        
        # Confidence
        lines.append("📈 CONFIDENCE:")
        lines.append("-" * 30)
        lines.append(plan.confidence_explanation)
        lines.append("")
        
        # Footer
        lines.append("=" * 60)
        
        return "\n".join(lines)
    
    @staticmethod
    def format_compact_summary(plan: GenerationPlan) -> str:
        """
        Create a compact one-line summary of the plan.
        
        Args:
            plan: The generation plan to summarize
            
        Returns:
            Compact summary string
        """
        breakdown_parts = []
        for area in plan.breakdown:
            breakdown_parts.append(f"{area.card_count} {area.area_name}")
        
        breakdown_str = ", ".join(breakdown_parts)
        
        return f"Generate {plan.total_cards} cards for '{plan.original_intent.topic}': {breakdown_str}"
    
    @staticmethod
    def get_confirmation_prompt() -> str:
        """Get the confirmation prompt text."""
        return "\n🚀 Proceed with this plan? [Y/n]: "
    
    @staticmethod
    def format_plan_for_gui(plan: GenerationPlan) -> Dict[str, Any]:
        """
        Format plan data for GUI display.
        
        Args:
            plan: The generation plan to format
            
        Returns:
            Dictionary with GUI-friendly plan data
        """
        return {
            "topic": plan.original_intent.topic,
            "total_cards": plan.total_cards,
            "template": plan.template,
            "domain": plan.domain,
            "difficulty": plan.original_intent.difficulty_level.value if plan.original_intent.difficulty_level else None,
            "use_case": plan.original_intent.use_case,
            "breakdown": [
                {
                    "area": area.area_name.title(),
                    "cards": area.card_count,
                    "percentage": area.percentage,
                    "description": area.description
                }
                for area in plan.breakdown
            ],
            "reasoning": plan.reasoning,
            "confidence_explanation": plan.confidence_explanation,
            "confidence_score": plan.original_intent.confidence_score
        }
    
    @staticmethod
    def format_intent_analysis(intent: LearningIntent) -> str:
        """
        Format the parsed intent for debugging/logging.
        
        Args:
            intent: The parsed learning intent
            
        Returns:
            Formatted intent analysis
        """
        lines = []
        
        lines.append("🔍 INTENT ANALYSIS:")
        lines.append("-" * 25)
        lines.append(f"Raw Input: '{intent.raw_input}'")
        lines.append(f"Parsed Topic: {intent.topic}")
        lines.append(f"Domain: {intent.domain or 'Not specified'}")
        lines.append(f"Subject Area: {intent.subject_area or 'Not specified'}")
        lines.append(f"Focus Areas: {', '.join(intent.focus_areas) if intent.focus_areas else 'None'}")
        lines.append(f"Specific Skills: {', '.join(intent.specific_skills) if intent.specific_skills else 'None'}")
        lines.append(f"Difficulty: {intent.difficulty_level.value if intent.difficulty_level else 'Not specified'}")
        lines.append(f"Time Constraint: {intent.time_constraint.value if intent.time_constraint else 'Not specified'}")
        lines.append(f"Use Case: {intent.use_case or 'Not specified'}")
        lines.append(f"Estimated Cards: {intent.estimated_cards}")
        lines.append(f"Confidence Score: {intent.confidence_score:.2f}")
        
        return "\n".join(lines)


def get_user_confirmation_cli(plan: GenerationPlan, show_analysis: bool = False) -> bool:
    """
    Present plan to user and get confirmation via CLI.
    
    Args:
        plan: The generation plan to present
        show_analysis: Whether to show detailed intent analysis
        
    Returns:
        True if user confirms, False otherwise
    """
    # Show intent analysis if requested
    if show_analysis:
        print(PlanPresenter.format_intent_analysis(plan.original_intent))
        print()
    
    # Show plan summary
    print(PlanPresenter.format_plan_summary(plan))
    
    # Get confirmation
    try:
        response = input(PlanPresenter.get_confirmation_prompt()).strip().lower()
        return response in ['', 'y', 'yes', 'yeah', 'yep']
    except (KeyboardInterrupt, EOFError):
        return False


def modify_plan_interactive(plan: GenerationPlan) -> Optional[GenerationPlan]:
    """
    Allow user to modify the plan interactively via CLI.
    
    Args:
        plan: The original generation plan
        
    Returns:
        Modified plan or None if user cancels
    """
    print("\n⚙️  MODIFY PLAN:")
    print("-" * 20)
    print("What would you like to change?")
    print("1. Number of cards")
    print("2. Focus area distribution") 
    print("3. Template type")
    print("4. Cancel modifications")
    
    try:
        choice = input("\nEnter choice (1-4): ").strip()
        
        if choice == "1":
            new_total = int(input(f"Current: {plan.total_cards} cards. New total: "))
            if new_total > 0:
                # Recalculate breakdown proportionally
                ratio = new_total / plan.total_cards
                for area in plan.breakdown:
                    area.card_count = max(1, int(area.card_count * ratio))
                    area.percentage = round((area.card_count / new_total) * 100)
                plan.total_cards = sum(area.card_count for area in plan.breakdown)
                print(f"✅ Updated to {plan.total_cards} cards")
                
        elif choice == "2":
            print("Current breakdown:")
            for i, area in enumerate(plan.breakdown):
                print(f"{i+1}. {area.area_name}: {area.card_count} cards")
            
            area_idx = int(input("Which area to modify (number): ")) - 1
            if 0 <= area_idx < len(plan.breakdown):
                new_count = int(input(f"New count for {plan.breakdown[area_idx].area_name}: "))
                if new_count >= 0:
                    old_count = plan.breakdown[area_idx].card_count
                    plan.breakdown[area_idx].card_count = new_count
                    plan.total_cards += (new_count - old_count)
                    
                    # Recalculate percentages
                    for area in plan.breakdown:
                        area.percentage = round((area.card_count / plan.total_cards) * 100)
                    print(f"✅ Updated {plan.breakdown[area_idx].area_name} to {new_count} cards")
                    
        elif choice == "3":
            templates = ["basic", "comprehensive"]
            print(f"Current: {plan.template}")
            print("Available templates:", ", ".join(templates))
            new_template = input("New template: ").strip()
            if new_template in templates:
                plan.template = new_template
                print(f"✅ Updated template to {new_template}")
                
        elif choice == "4":
            return None
            
        return plan
        
    except (ValueError, KeyboardInterrupt, EOFError, IndexError):
        print("❌ Invalid input or cancelled")
        return None