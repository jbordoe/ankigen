import os
import logging
import typer
from typing_extensions import Annotated

from rich.logging import RichHandler, Console
from typing import Optional

from ankigen.services import (
    FlashcardGenerationService, 
    GenerationRequest, 
    OutputConfig
)
from ankigen.services.intent_analyzer import IntentAnalyzer
from ankigen.services.plan_presenter import (
    PlanPresenter, 
    get_user_confirmation_cli, 
    modify_plan_interactive
)
from ankigen.utils.template_manager import list_templates

FORMAT = "%(message)s"
log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=log_level,
    format=FORMAT,
    datefmt="[%X]",
    handlers=[RichHandler(console=Console(stderr=True))]
)
log = logging.getLogger("rich")

app = typer.Typer(
    help="Generate Anki flashcards from a given topic using an LLM.",
    pretty_exceptions_show_locals=False # Hide locals in tracebacks for cleaner output
)

@app.command()
def generate(
    topic: Annotated[
        str,
        typer.Option(
            "--topic", "-t",
            help="The main topic for which to generate flashcards.",
            prompt="Please enter the topic for flashcard generation"
        )
    ],
    num_cards: Annotated[
        int,
        typer.Option(
            "--num-cards", "-n",
            help="The number of flashcards to generate for the topic.",
            min=1,
            max=100 # Set a reasonable max to prevent excessive LLM calls
        )
    ],
    model_name: Annotated[
        str,
        typer.Option(
            "--model", "-m",
            help="The LLM model name to use (e.g., 'gemini-2.0-flash', 'gemini-1.5-pro').",
            show_default=True
        )
    ] = "gemini-2.0-flash", # Default LLM model
    output_filename: Annotated[
        str,
        typer.Option(
            "--output", "-o",
            help="The filename for the generated Anki deck (.apkg).",
            show_default=True
        )
    ] = "generated_flashcards.apkg",
    deck_name: Annotated[
        str,
        typer.Option(
            "--deck-name", "-d",
            help="The name of the Anki deck inside Anki. Defaults to 'Generated Flashcards: [Topic]'.",
            show_default=False
        )
    ] = None, # Will be set based on topic if not provided
   session_id: Annotated[
        str,
        typer.Option(
            "--session-id", "-s",
            help="Unique ID for this generation session (for resuming). If not provided, a new one is generated.",
            show_default=False
        )
    ] = None,
    template: Annotated[
        str,
        typer.Option(
            "--template", "-r",
        help=f"The template to use for rendering flashcards. Accepts: {','.join(list_templates())}",
            show_default=True
        )
    ] = 'basic',
    workflow: Annotated[
        str,
        typer.Option(
            "--workflow", "-w",
            help="Workflow type: 'topic' (single topic), 'module' (module with topics), 'subject' (multi-module subject), 'iterative' (legacy iterative)",
            show_default=True
        )
    ] = 'module',
    domain: Annotated[
        Optional[str],
        typer.Option(
            "--domain", "-x",
            help="Domain for few-shot examples: 'language', 'programming', etc. Leave empty for zero-shot prompting.",
            show_default=False
        )
    ] = None,
    preview: Annotated[
        bool,
        typer.Option(
            "--preview", "-p",
            help="Generate HTML preview instead of Anki deck file",
            show_default=False
        )
    ] = False,
):
    """
    Generates a new Anki deck with flashcards for a specified topic.
    """
    try:
        # Initialize service
        service = FlashcardGenerationService()
        
        # Create generation request
        request = GenerationRequest(
            topic=topic,
            num_cards=num_cards,
            model_name=model_name,
            deck_name=deck_name,
            session_id=session_id,
            workflow=workflow,
            domain=domain,
            template=template
        )
        
        # Create output configuration
        output_config = OutputConfig(
            output_type="preview" if preview else "anki",
            filename=output_filename
        )
        
        # Generate flashcards
        result = service.generate_flashcards(request, output_config)
        
        log.info(f"Generation completed successfully!")
        log.info(f"Generated {len(result.cards)} cards using '{result.workflow_used}' workflow")
        log.info(f"Session ID: {result.session_id}")
        
    except (ValueError, RuntimeError) as e:
        log.error(f"Generation failed: {e}")
        raise typer.Exit(code=1)
    except Exception as e:
        log.error(f"Unexpected error: {e}")
        raise typer.Exit(code=1)


@app.command()
def learn(
    request: Annotated[
        str,
        typer.Option(
            "--request", "-r",
            help="Natural language description of what you want to learn.",
            prompt="What would you like to learn? (e.g., 'Spanish cooking vocabulary', 'Python programming basics')"
        )
    ],
    model_name: Annotated[
        str,
        typer.Option(
            "--model", "-m",
            help="The LLM model name to use for both analysis and generation.",
            show_default=True
        )
    ] = "gemini-2.0-flash",
    output_filename: Annotated[
        str,
        typer.Option(
            "--output", "-o",
            help="The filename for the generated Anki deck (.apkg).",
            show_default=True
        )
    ] = "generated_flashcards.apkg",
    session_id: Annotated[
        str,
        typer.Option(
            "--session-id", "-s",
            help="Unique ID for this generation session (for resuming).",
            show_default=False
        )
    ] = None,
    preview: Annotated[
        bool,
        typer.Option(
            "--preview", "-p",
            help="Generate HTML preview instead of Anki deck file",
            show_default=False
        )
    ] = False,
    show_analysis: Annotated[
        bool,
        typer.Option(
            "--show-analysis", "-a",
            help="Show detailed intent analysis before plan confirmation",
            show_default=False
        )
    ] = False,
):
    """
    Natural language interface: describe what you want to learn and let the LLM plan your flashcards.
    
    Examples:
    - "I want to learn Spanish cooking vocabulary for my trip to Barcelona"
    - "Help me understand Python data structures and algorithms"
    - "Quick review of calculus derivatives before my exam"
    """
    try:
        # Initialize intent analyzer
        log.info("🤔 Analyzing your learning request...")
        analyzer = IntentAnalyzer()
        
        # Parse the natural language request
        intent = analyzer.analyze_intent(request)
        log.info(f"✅ Parsed topic: '{intent.topic}'")
        
        # Create generation plan
        log.info("📋 Creating generation plan...")
        plan = analyzer.create_generation_plan(intent)
        
        # Present plan and get confirmation
        confirmed = get_user_confirmation_cli(plan, show_analysis=show_analysis)
        
        if not confirmed:
            # Offer to modify the plan
            print("\n🔧 Would you like to modify the plan? [y/N]: ", end="")
            try:
                modify_response = input().strip().lower()
                if modify_response in ['y', 'yes']:
                    modified_plan = modify_plan_interactive(plan)
                    if modified_plan:
                        plan = modified_plan
                        confirmed = get_user_confirmation_cli(plan, show_analysis=False)
                        
                if not confirmed:
                    log.info("❌ Generation cancelled by user")
                    raise typer.Exit(code=0)
                    
            except (KeyboardInterrupt, EOFError):
                log.info("❌ Generation cancelled by user")
                raise typer.Exit(code=0)
        
        # Initialize generation service
        log.info("🚀 Starting flashcard generation...")
        service = FlashcardGenerationService()
        
        # Create generation request from plan
        request_obj = GenerationRequest(
            topic=plan.original_intent.topic,
            num_cards=plan.total_cards,
            model_name=model_name,
            deck_name=f"Generated Flashcards: {plan.original_intent.topic}",
            session_id=session_id,
            workflow=plan.workflow,
            domain=plan.domain,
            template=plan.template
        )
        
        # Create output configuration
        output_config = OutputConfig(
            output_type="preview" if preview else "anki",
            filename=output_filename
        )
        
        # Generate flashcards
        result = service.generate_flashcards(request_obj, output_config)
        
        log.info(f"🎉 Generation completed successfully!")
        log.info(f"Generated {len(result.cards)} cards using '{result.workflow_used}' workflow")
        log.info(f"Session ID: {result.session_id}")
        
        # Show breakdown summary
        print("\n" + "=" * 50)
        print("📊 FINAL RESULTS:")
        print("=" * 50)
        print(f"Topic: {plan.original_intent.topic}")
        print(f"Cards Generated: {len(result.cards)}")
        print(f"Original Plan: {plan.get_breakdown_summary()}")
        if not preview:
            print(f"Output File: {output_filename}")
        print("=" * 50)
        
    except (ValueError, RuntimeError) as e:
        log.error(f"Generation failed: {e}")
        raise typer.Exit(code=1)
    except Exception as e:
        log.error(f"Unexpected error: {e}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
