from ankigen.utils.template_manager import render_anki_card_to_html, list_templates, is_valid_template

from ankigen.models.anki_card import AnkiCard

def test_list_templates():
    """Test the list_templates function."""
    templates = list_templates()

    assert isinstance(templates, list)
    assert "basic" in templates
    assert "comprehensive" in templates

def test_is_valid_template():
    """Test the is_valid_template function."""
    assert is_valid_template("basic")
    assert not is_valid_template("invalid")

def test_render_anki_card_to_html():
    """Test the render_anki_card_to_html function."""
    card = AnkiCard(
        type_="Vocabulary",
        topic="Math",
        subtopic="Arithmetic",
        title="Addition",
        front_question_text="What is the sum of 2 and 3?",
        back_answer="5"
    )
    html = render_anki_card_to_html(card, "front", "basic")
    assert html == """<html lang="en">
  <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
  </head>
  <body>
    <div class="card">
      What is the sum of 2 and 3?
    </div>
  </body>
</html>"""
