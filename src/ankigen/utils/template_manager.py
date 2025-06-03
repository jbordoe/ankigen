import os
import logging
from jinja2 import Environment, FileSystemLoader, select_autoescape

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

def render_anki_card_to_html(card: AnkiCard, template_name: str) -> str:
    """
    Renders an AnkiCard Pydantic object into HTML strings
    """
    try:
        template = jinja_env.get_template(template_name)
        card_html = template.render(card=card)

        return card_html
    except Exception as e:
        log.error(f"Error rendering template: {e}")
        return None
