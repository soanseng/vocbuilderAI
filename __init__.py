import html
from inspect import iscoroutine
from platform import node
import random
from .prompts import VOC_PROMPT, JPY_PROMPT
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
import re
import time



# path to the libs folder
libs_path = os.path.join(os.path.dirname(__file__), "libs")
sys.path.insert(0, libs_path)


from openai import OpenAI


# Accessing the configuration
config = mw.addonManager.getConfig(__name__)

def generate_speech(vocab_word, retries=3):
    api_key = config.get("openai_api_key")
    client = OpenAI(api_key=api_key)

    for i in range(retries):
        try:
            hashed_vocab = hashlib.md5(vocab_word.encode()).hexdigest()
            temp_file_path = Path(__file__).parent / f"whisper-{hashed_vocab}.mp3"
            random_voice = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
            if config.get("speech_voice", "") == "":
                speech_voice = random.choice(random_voice)
            else:
                speech_voice = config.get("speech_voice", "")

            speech_model = config.get("speech_model", "tts-1-hd")
            speech_speed = config.get("speech_speed", 1)
            response = client.audio.speech.create(
                model=speech_model, 
                voice=speech_voice, 
                speed=speech_speed,
                input=vocab_word)
            response.stream_to_file(temp_file_path)
            final_file_name = mw.col.media.addFile(str(temp_file_path))
            temp_file_path.unlink(missing_ok=True)
            return final_file_name
        except Exception as e:
            showInfo(f"Error: {e}")
            if i < retries - 1:
                time.sleep(5)
                continue
            else:
                showInfo(f"Error: {e}. Please try again later.")
                return None


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


#   "definitions": [
#     {
#       "text": "Definition 1",
#       "grammaticalInfo": {
#         "partOfSpeech": "Part of Speech",
#         "forms": {
#           "verb": ["present form", "past form", "past participle"],
#           "adjective": ["comparative", "superlative"],
#           "noun": ["plural form"]
#         }
#       }
#     },
forms_mapping = {
    "verb": lambda values: ", ".join(values),
    "adjective": lambda values: ", ".join(values),
    "noun": lambda values: "".join(values),
}

def format_definitions_html(definitions):
    html_content = "<h3>Definitions:</h3><ol>"
    for definition in definitions:
        html_content += f"<li><b>{definition.get('text', 'No definition')}</b>"

        grammatical_info = definition.get("grammaticalInfo")
        if grammatical_info:
            part_of_speech = grammatical_info.get("partOfSpeech")
            if part_of_speech:
                html_content += f" <i>({part_of_speech})</i>"

            forms = grammatical_info.get("forms")
            if forms:
                html_content += "<ul>"
                for form, values in forms.items():
                    values_str = forms_mapping.get(form, lambda x: x)(values)
                    html_content += f"<li><b>{form.capitalize()}:</b> {values_str}</li>"
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
    for antonym in antonyms:
        html_content += f"<li>{antonym}</li>"
    html_content += "</ol><br>"
    return html_content


def format_examples_html(vocab_word, examples):
    html_content = "<h3>Real-world Examples:</h3><ul>"
    for example in examples:
        bold_word = example.replace(vocab_word, f"<strong>{vocab_word}</strong>")
        html_content += f"<li>{bold_word}</li>"
    html_content += "</ul>"
    return html_content

# format for japanese vocab
# {
#   "vocabulary": "近い",
#   "kanji": "近い",
#   "furigana": "ちかい",
#   "pitchPattern": "0",
#   "pronunciations": "chikai",
#   "explanations": {
#     "en-US": "near, close",
#     "zh-TW": "近的"
#   },
#   "partsOfSpeech": "adjective",
#   "grammaticalRules": {
#     "adjectives": {
#       "NegativeForm": "近くない",
#       "PastPositiveForm": "近かった",
#       "PastNegativeForm": "近くなかった",
#       "TeForm": "近くて"
#     }
#   },
#   "sound": "https://forvo.com/word/近い/#ja",
#   "exampleSentences": [
#     {"sentence": "この家は駅に近いです。", "translation": "這個房子離車站很近。"},
#     {"sentence": "彼は私の近い友達です。", "translation": "他是我親近的朋友。"},
#     {"sentence": "近い将来に旅行したいです。", "translation": "我想在不久的將來旅行。"},
#     {"sentence": "彼女は近い将来に結婚する予定です。", "translation": "她計劃在不久的將來結婚。"},
#     {"sentence": "この店は近い将来に閉店する予定です。", "translation": "這家店計劃在不久的將來關閉。"}
#   ]
# }

def format_kanji_html(kanji):
    html_content = "<h3>Kanji:</h3>"
    html_content += f"<p>{kanji}</p>"
    return html_content
def format_furigana_html(furigana):
    html_content = "<h3>Furigana:</h3>"
    html_content += f"<p>{furigana}</p>"
    return html_content
def format_pitchPattern_html(pitchPattern):
    html_content = "<h3>Pitch Pattern:</h3>"
    html_content += f"<p>{pitchPattern}</p>"
    return html_content
def format_explanations_html(explanations):
    html_content = "<h3>Explanations:</h3>"
    html_content += f"<p>en-US: {explanations['en-US']}</p>"
    html_content += f"<p>zh-TW: {explanations['zh-TW']}</p>"
    return html_content
def format_partsOfSpeech_html(partsOfSpeech):
    html_content = "<h3>Parts of Speech:</h3>"
    html_content += f"<p>{partsOfSpeech}</p>"
    return html_content
def format_grammaticalRules_html(grammaticalRules: dict):
    # "grammaticalRules": {
    # "verbs": {},
    # "adjectives": {},
    # "nouns": {
    #   "Variations": "遅刻する (to be late); 遅刻者 (latecomer)",
    #   "Examples": "彼はいつも遅刻する。\nHe is always late.\n他の人よりも遅刻することが多い。\nHe is late more often than others.\n彼は遅刻者だ。\nHe is a latecomer."
    # }
    # the json is been parsed by `process_response` into a dict, sometimes the verb, adjective, noun is empty
    html_content = "<h3>Grammatical Rules:</h3>"

    if grammaticalRules.get("verbs"):
        html_content += "<h4>verbs:</h4>"
        html_content += f"<p>PlainForm: {grammaticalRules['verbs']['PlainForm']}</p>"
        html_content += f"<p>PoliteForm: {grammaticalRules['verbs']['PoliteForm']}</p>"
        html_content += f"<p>NegativeForm: {grammaticalRules['verbs']['NegativeForm']}</p>"
        html_content += f"<p>PastTense: {grammaticalRules['verbs']['PastTense']}</p>"
        html_content += f"<p>TeForm: {grammaticalRules['verbs']['TeForm']}</p>"
        html_content += f"<p>PotentialForm: {grammaticalRules['verbs']['PotentialForm']}</p>"
        html_content += f"<p>CausativeForm: {grammaticalRules['verbs']['CausativeForm']}</p>"
        html_content += f"<p>PassiveForm: {grammaticalRules['verbs']['PassiveForm']}</p>"
    if grammaticalRules.get("adjectives"):
        html_content += "<h4>adjectives:</h4>"
        html_content += f"<p>NegativeForm: {grammaticalRules['adjectives']['NegativeForm']}</p>"
        html_content += f"<p>PastPositiveForm: {grammaticalRules['adjectives']['PastPositiveForm']}</p>"
        html_content += f"<p>PastNegativeForm: {grammaticalRules['adjectives']['PastNegativeForm']}</p>"
        html_content += f"<p>TeForm: {grammaticalRules['adjectives']['TeForm']}</p>"
    if grammaticalRules.get("nouns"):
        html_content += "<h4>nouns:</h4>"
        html_content += f"<p>Variations: {grammaticalRules['nouns']['Variations']}</p>"
        # break the line in examples to unordered list
        html_content += "<ul>"
        for example in grammaticalRules['nouns']['Examples'].split("\n"):
            html_content += f"<li>{example}</li>"
    if grammaticalRules.get("others"):
        html_content += "<h4>others:</h4>"
        html_content += f"<p>others: {grammaticalRules['others']}</p>"
    #error handling
    if not grammaticalRules.get("verbs") and not grammaticalRules.get("adjectives") and not grammaticalRules.get("nouns") and not grammaticalRules.get("others"):
        html_content += "<p>No grammatical rules found.</p>"
    return html_content

def format_exampleSentences_html(exampleSentences):
    html_content = "<h3>Example Sentences:</h3><ol>"
    for exampleSentence in exampleSentences:
        html_content += f"<li><strong>{exampleSentence.get('sentence')}</strong> - {exampleSentence.get('translation')}</li>"
        html_content += "</ol>"
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

    # Create a new note
    note = Note(mw.col, model)
    note["vocabulary"] = format_vocabulary_html(note_data["word"])
    note["Pronunciations"] = format_pronunciations_html(note_data["pronunciation"])
    note["Sound"] = (
        format_sound_html(note_data["soundLink"]) + f"<br> [sound:{speech_file_path}] "
    )
    note["detail definition"] = format_meanings_html(
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

def is_japanese_vocab(vocab_word):

    """
    Determine if a given word is Japanese based on character set analysis.

    Args:
    word (str): The word to be analyzed.

    Returns:
    bool: True if the word is Japanese, False otherwise.
    """
    # Regular expression pattern for matching Japanese characters (Kanji, Hiragana, Katakana)
    japanese_char_pattern = r'[\u3000-\u303F\u3040-\u309F\u30A0-\u30FF\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF]'

    # Check if the word contains any Japanese characters
    if re.search(japanese_char_pattern, vocab_word):
        return True
    else:
        return False



def generate_vocab_note(vocab_word: str, retries=3):
    # get info from config
    provider = config.get("provider")
    temperature = config.get("temperature", 0.5)
    if provider == 'openai':
        model = config.get("model", "gpt-3.5-turbo-1106")
        api_key = config.get("openai_api_key") 
        base_url = "https://api.openai.com/v1"
    else:
        model = config.get("model")
        base_url = config.get("other_base_url")
        api_key = config.get("other_api_key")

    for i in range(retries):
        try:
            client = OpenAI(api_key=api_key, base_url=base_url)
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": VOC_PROMPT if not is_japanese_vocab(vocab_word) else JPY_PROMPT, 
                    },
                    {"role": "user", "content": f"{vocab_word}"},
                ],
                temperature=temperature,
                response_format={"type" : "json_object"}
            )
            return response.choices[0].message.content
        except Exception as e:
            if i < retries - 1:
                time.sleep(5)
                continue
            else:
                showInfo(f"Error: {e}. please try again later")
                return None


def clean_response(response: str) -> str:
    # Find the index of the marker
    idx = response.find("```")
    if idx == -1:
        idx = response.find("```json")
    
    # If the marker is found, remove everything before it
    if idx != -1:
        response = response[idx + len("```"):]  # account for the length of the marker
        if response.startswith("json"):
            response = response[len("json"):]

    # Remove the ending marker if present
    if response.endswith("```"):
        response = response[: -len("```")]

    return response.strip()


def process_response(response :str) -> dict:
    cleaned_response = clean_response(response)
    try:
        return json.loads(cleaned_response)
    except json.JSONDecodeError as e:
        showInfo(f"Failed to parse note data: {e}\nContent: {cleaned_response}")
        return {}


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
        try:
            note_data = json.loads(response)
        except json.JSONDecodeError:
            note_data = process_response(response)


        # Check if note_data is a dictionary and has necessary keys
        if isinstance(note_data, dict) and not is_japanese_vocab(vocab_word):
            # Populate the fields in the editor
            editor.note["vocabulary"] = format_vocabulary_html(note_data["word"])
            editor.note["Pronunciations"] = format_pronunciations_html(
                note_data["pronunciation"]
            )
            sound = generate_speech(note_data['word'])
            editor.note["Sound"] = (
                format_sound_html(note_data["soundLink"])
                + f"<br>[sound:{sound}]"
            )
            editor.note["detail definition"] = format_meanings_html(
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
        if isinstance(note_data, dict) and is_japanese_vocab(vocab_word):
            # Populate the fields in the editor
            editor.note["vocabulary"] = format_vocabulary_html(note_data["vocabulary"])
            editor.note["Pronunciations"] = format_partsOfSpeech_html(note_data["partsOfSpeech"]) + format_pronunciations_html(note_data["pronunciations"])
            sound = generate_speech(note_data['vocabulary'])
            editor.note["Sound"] = format_sound_html(note_data["sound"]) + f"<br>[sound:{ sound }]"
            editor.note["detail definition"] = (
                format_kanji_html(note_data["kanji"]) 
                + "<br>" + format_furigana_html(note_data["furigana"]) 
                + "<br>" + format_meanings_html(note_data["explanations"]) 
                + "<br>" + format_explanations_html(note_data["explanations"])
            )
            editor.note["Etymology, Synonyms and Antonyms"] = format_grammaticalRules_html(note_data["grammaticalRules"])
            editor.note["Real-world examples"] = format_exampleSentences_html(note_data["exampleSentences"])
            #add tags to this note
            
            editor.loadNote()
    except Exception as e:
        showInfo(f"Error: {e}")
        return


def add_action_button(buttons, editor: Editor):
    icon_path = None
    action = QAction("Generate Content", editor.widget)
    action.triggered.connect(lambda _, e=editor:on_add_note(e))
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

