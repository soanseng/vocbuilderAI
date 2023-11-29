from platform import node
from aqt import mw, gui_hooks
from aqt.gui_hooks import editor_did_init_buttons
from aqt.editor import Editor
from aqt.utils import showInfo
from aqt.qt import *
from anki.notes import Note
import os
import sys
import json
from pathlib import Path
import hashlib
import traceback


# path to the libs folder
libs_path = os.path.join(os.path.dirname(__file__), "libs")
sys.path.insert(0, libs_path)

from openai import OpenAI

# Accessing the configuration
config = mw.addonManager.getConfig(__name__)
OPENAI_API_KEY = config.get("openai_api_key")


def generate_speech(vocab_word):
    client = OpenAI(api_key=OPENAI_API_KEY)
    # Generate a hash of the vocabulary word
    hashed_vocab = hashlib.md5(vocab_word.encode()).hexdigest()

    # Define the path for the speech file
    speech_file_path = Path(__file__).parent / f"whisper-{hashed_vocab}.mp3"

    # get info from config
    voice = config.get("speech_voice", "alloy")

    # Generate the speech
    response = client.audio.speech.create(model="tts-1", voice=voice, input=vocab_word)

    # Save the speech file
    response.stream_to_file(speech_file_path)

    return speech_file_path


def format_vocabulary_html(word):
    return f"<h2>{word}</h2>"


def format_pronunciations_html(pronunciation):
    return f"<h3>Pronunciation:</h3><p>{pronunciation}</p>"


def format_sound_html(sound_link):
    return f"<h3>Sound:</h3><a href='{sound_link}'>Listen</a>"


def format_meanings_html(meanings):
    html_content = "<h3>Meanings:</h3><ul>"
    for lang, meaning in meanings.items():
        html_content += f"<li><b>{lang.capitalize()}:</b> {meaning}</li>"
    html_content += "</ul><br>"
    return html_content


def format_definitions_html(definitions):
    html_content = "<h3>Definitions:</h3><ol>"
    for definition in definitions:
        html_content += f"<li><b>{definition['text']}</b>"
        if "grammaticalInfo" in definition:
            grammatical_info = definition["grammaticalInfo"]
            if "partOfSpeech" in grammatical_info:
                html_content += f" <i>({grammatical_info['partOfSpeech']})</i>"

            if "forms" in grammatical_info:
                html_content += "<ul>"
                for form, values in grammatical_info["forms"].items():
                    html_content += f"<li><b>{form.capitalize()}:</b> {values}</li>"
                html_content += "</ul>"
        html_content += "</li>"
    html_content += "</ol>"
    return html_content


def format_etymology_html(etymology):
    return f"<h3>Etymology:</h3><p>{etymology}</p><br>"


def format_synonyms_html(synonyms):
    html_content = "<h3>Synonyms:</h3><ol>"
    for synonym in synonyms:
        html_content += f"<li>{synonym}</li>"
    html_content += "</ol><br>"
    return html_content


def format_antonyms_html(antonyms):
    html_content = "<h3>Antonyms:</h3><ol>"
    for antonyms in antonyms:
        html_content += f"<li>{antonyms}</li>"
    html_content += "</ol><br>"
    return html_content


def format_examples_html(vocab_word, examples):
    html_content = "<h3>Real-world Examples:</h3><ul>"
    for example in examples:
        bold_word = example.replace(vocab_word, f"<strong>{vocab_word}</strong>")
        html_content += f"<li>{bold_word}</li>"
    html_content += "</ul>"
    return html_content


def add_note_to_deck(deck_name, tag_name, note_data):
    # Ensure the deck exists, or create it
    did = mw.col.decks.id(deck_name)
    mw.col.decks.select(did)

    # Set the model (note type)
    model = mw.col.models.byName("vocbuilderAI")
    mw.col.models.setCurrent(model)

    # generate sound and save to note
    speech_file_path = generate_speech(note_data["word"])
    # Copy the speech file to Anki's media folder
    mw.col.media.addFile(speech_file_path)

    # Create a new note
    note = Note(mw.col, model)
    note["vocabulary"] = format_vocabulary_html(note_data["word"])
    note["Pronunciations"] = format_pronunciations_html(note_data["pronunciation"])
    note["Sound"] = (
        format_sound_html(note_data["soundLink"])
        + f"<br> [sound:{speech_file_path.name}] "
    )
    note["detail defination"] = format_meanings_html(
        note_data["meanings"]
    ) + format_definitions_html(note_data["definitions"])
    note["Etymology, Synonyms and Antonyms"] = (
        format_etymology_html(note_data["etymology"])
        + format_synonyms_html(note_data["synonyms"])
        + format_antonyms_html(note_data["antonyms"])
    )
    note["Real-world examples"] = format_examples_html(
        note_data["word"], note_data["realWorldExamples"]
    )
    # set the tag for the note
    note.addTag(tag_name)

    # Add note to the deck
    mw.col.addNote(note)
    mw.col.decks.save()
    mw.col.save()


def get_tag_name(default_tag="vocabulary::wordoftheday"):
    tags = mw.col.tags.all()
    tag_name, ok = QInputDialog.getItem(
        mw,
        "Select Tag",
        "Choose the tag to add the note:",
        tags,
        tags.index(default_tag) if default_tag in tags else 0,
        False,
    )
    return tag_name if ok and tag_name else default_tag


def get_deck_name(default_deck="Big"):
    decks = mw.col.decks.allNames()
    deck_name, ok = QInputDialog.getItem(
        mw,
        "Select Deck",
        "Choose the deck to add the note:",
        decks,
        decks.index(default_deck) if default_deck in decks else 0,
        False,
    )
    return deck_name if ok and deck_name else default_deck


def generate_vocab_note(vocab_word):
    VOC_PROMPT = """
I want you to be the best bilingual dictionary in the world. 
Generate a comprehensive bilingual dictionary entry in JSON format for an English word I provide. 
The JSON object should include:

1. **Meanings**: The English word's meanings and its equivalent in Traditional Chinese.
2. **Detailed Definitions**: Several definitions matching the quality of Merriam-Webster, Oxford, Collins, and Dictionary.com.
3. **Extended Grammatical Information**: 
    - Part of speech.
    - If it's a verb, include present, past, and past participle forms.
    - If it's an adjective, include comparative and superlative forms.
    - If it's a noun, include its plural form.
4. **Pronunciations**: In the Kenyon and Knott system (not IPA).
5. **Sound Link**: A Forvo link in the specified format.
6. **Etymology**: The word's origin.
7. **Synonyms and Antonyms**: List five synonyms and five antonyms.
8. **Real-World Examples**: Five sentences using the word.
Format the JSON object as follows:
{
  "word": "Your English Word",
  "meanings": {
    "english": "Meaning in English",
    "traditionalChinese": "Equivalent in Traditional Chinese"
  },
  "definitions": [
    {
      "text": "Definition 1",
      "grammaticalInfo": {
        "partOfSpeech": "Part of Speech",
        "forms": {
          "verb": ["present form", "past form", "past participle"],
          "adjective": ["comparative", "superlative"],
          "noun": ["plural form"]
        }
      }
    },
    {
      "text": "Definition 2",
      "grammaticalInfo": {
        // Grammatical information for Definition 2
      }
    },
    {
      "text": "Definition 3",
      "grammaticalInfo": {
        // Grammatical information for Definition 3
      }
    }
  ],
  "pronunciation": "Pronunciation using Kenyon and Knott",
  "soundLink": "https://forvo.com/word/{english_word}/#en",
  "etymology": "Origin of the Word",
  "synonyms": [
    "Synonym 1",
    "Synonym 2",
    ...
  ],
  "antonyms": [
    "Antonym 1",
    "Antonym 2",
    ...
  ],
  "realWorldExamples": [
    "Example Sentence 1",
    "Example Sentence 2",
    ...
  ]
}
    """
    # get info from config
    model = config.get("model", "gpt-3.5-turbo-1106")
    temperature = config.get("temperature", 0.5)
    max_tokens = config.get("max_tokens", 4096)

    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": VOC_PROMPT,
                },
                {"role": "user", "content": f"{vocab_word}"},
            ],
            temperature=temperature,
        )
        return response.choices[0].message.content
    except Exception as e:
        showInfo(f"Error: {e}")
        return None


def clean_response(response):
    # Remove starting marker
    if response.startswith("```json"):
        response = response[len("```json") :]

    # Remove ending marker
    if response.endswith("```"):
        response = response[: -len("```")]

    return response.strip()


def process_response(response):
    cleaned_response = clean_response(response)
    try:
        return json.loads(cleaned_response)
    except json.JSONDecodeError as e:
        showInfo(f"Failed to parse note data: {e}\nContent: {cleaned_response}")
        return None


def get_vocab_word():
    word, ok = QInputDialog.getText(
        mw, "VocabBuilderAI", "Enter a new vocabulary word:"
    )
    if ok and word:
        response = generate_vocab_note(word)
        note_data = process_response(response)
        deck_name = get_deck_name()
        tag_name = get_tag_name()
        if deck_name and tag_name:
            add_note_to_deck(deck_name, tag_name, note_data)
            showInfo(f"Note added to deck '{deck_name}'")
        else:
            showInfo("No deck selected. Note was not added.")


# "add note" window
def on_add_note(editor: Editor):
    vocab_word = editor.note.fields[0]  # Assumes the first field is 'vocabulary'

    if not vocab_word:
        showInfo(
            "No vocabulary word entered. Please enter a word in the 'vocabulary' field."
        )
        return
    try:
        response = generate_vocab_note(vocab_word)
        note_data = process_response(response)

        if not isinstance(note_data, dict):
            showInfo(
                "Failed to generate note content. Please check your API key and Network."
            )
            return

        # Check if note_data is a dictionary and has necessary keys
        if isinstance(note_data, dict):
            # Populate the fields in the editor
            editor.note["vocabulary"] = format_vocabulary_html(note_data["word"])
            editor.note["Pronunciations"] = format_pronunciations_html(
                note_data["pronunciation"]
            )
            editor.note["Sound"] = (
                format_sound_html(note_data["soundLink"])
                + f"<br>[sound:{generate_speech(note_data['word']).name}]"
            )
            editor.note["detail defination"] = format_meanings_html(
                note_data["meanings"]
            ) + format_definitions_html(note_data["definitions"])
            editor.note["Etymology, Synonyms and Antonyms"] = (
                format_etymology_html(note_data["etymology"])
                + format_synonyms_html(note_data["synonyms"])
                + format_antonyms_html(note_data["antonyms"])
            )
            editor.note["Real-world examples"] = format_examples_html(
                note_data["word"], note_data["realWorldExamples"]
            )
            # Update the editor to reflect these changes
            editor.loadNote()
    except Exception as e:
        showInfo(f"Error: {e}")
        return


def add_action_button(buttons, editor: Editor):
    icon_path = None
    action = QAction("Generate Content", editor.widget)
    action.triggered.connect(lambda _, e=editor: on_add_note(e))
    # editor._links["generate_vocab_content"] = lambda _, e=editor: on_add_note(e)

    button = editor.addButton(
        icon=None,  # if icon_path is None else QIcon(icon_path),
        label="VocAI",  # None if icon_path is not None else "Generate",
        cmd="generate_vocab_content",
        func=lambda _, e=editor: on_add_note(e),
        tip="Generate content for vocabulary",
        keys=None,
    )
    buttons.append(button)
    return buttons


gui_hooks.editor_did_init_buttons.append(add_action_button)


def vocab_builder_ai():
    action = QAction("VocabBuilderAI", mw)
    action.triggered.connect(get_vocab_word)
    mw.form.menuTools.addAction(action)


vocab_builder_ai()
