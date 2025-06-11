import logging
import os
from jinja2 import Environment, FileSystemLoader, select_autoescape
from typing import List

from ankigen.models.anki_card import AnkiCard

log = logging.getLogger("rich")

TEMPLATE_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "../../../templates"
)

# Set up the Jinja2 environment
# autoescape is good for HTML templates to prevent XSS
jinja_env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(['html', 'xml'])
)

def render_anki_card_to_html(card: AnkiCard, side: str, template: str) -> str:
    """
    Renders an AnkiCard Pydantic object into HTML strings
    """
    try:
        template_name = f"{template}-{side}.html"
        template = jinja_env.get_template(template_name)
        card_html = template.render(card=card)

        return card_html
    except Exception as e:
        log.error(f"Error rendering template: {e}")
        return None

def list_templates() -> List[str]:
    """
    Lists all valid template names.
    """
    # list all files in the templates directory
    # and check if the template name is in the list
    template_files = [f.name for f in os.scandir(TEMPLATE_DIR) if f.is_file()]
    prefixes = [f.split("-")[0] for f in template_files]
    return prefixes

def is_valid_template(template_name: str) -> bool:
    """
    Checks if a given template name is valid.
    """
    return template_name in list_templates()
