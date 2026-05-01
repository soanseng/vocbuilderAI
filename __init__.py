import hashlib
import json
import random
import re
import sys
import time
from pathlib import Path

import requests

try:  # pragma: no cover - exercised by Anki, not by headless tests.
    from .prompts import JPY_PROMPT, VOC_PROMPT
except ImportError:
    from prompts import JPY_PROMPT, VOC_PROMPT

try:
    if "pytest" in sys.modules:
        raise ImportError("Skip Anki/Qt imports during pytest collection.")
    from aqt import gui_hooks, mw
    from aqt.editor import Editor
    from aqt.qt import (
        QAction,
        QCheckBox,
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QDoubleSpinBox,
        QFormLayout,
        QFrame,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPushButton,
        QScrollArea,
        QSizePolicy,
        QTabWidget,
        QVBoxLayout,
        QWidget,
    )
    from aqt.utils import showInfo
    from anki.notes import Note

    ANKI_AVAILABLE = mw is not None and getattr(mw, "form", None) is not None
except Exception:
    ANKI_AVAILABLE = False
    mw = None
    gui_hooks = None
    Editor = object
    Note = None

    def showInfo(message):
        print(message)

    class _UnavailableQt:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("Qt is only available inside Anki.")

    QAction = QCheckBox = QComboBox = QDialog = QDialogButtonBox = QDoubleSpinBox = _UnavailableQt
    QFormLayout = QFrame = QGroupBox = QHBoxLayout = QLabel = QLineEdit = _UnavailableQt
    QPushButton = QScrollArea = QSizePolicy = QTabWidget = QVBoxLayout = QWidget = _UnavailableQt


CONFIG_DEFAULTS = {
    "openai_api_key": "your-openai-key",
    "deepseek_api_key": "your-deepseek-key",
    "groq_api_key": "your-groq-key",
    "openrouter_api_key": "your-openrouter-key",
    "default_deck": "Big",
    "default_tag": "vocabulary::wordoftheday",
    "note_type": "vocbuilderAI",
    "model": "",
    "max_tokens": 15000,
    "temperature": 0.5,
    "speech_voice": "",
    "speech_model": "gpt-4o-mini-tts",
    "speech_speed": 1.0,
    "provider": "openai",
}

PROVIDER_DEFAULTS = {
    "openai": {
        "model": "gpt-4o-mini",
        "base_url": "https://api.openai.com/v1",
        "api_key_config": "openai_api_key",
        "supports_response_format": True,
    },
    "deepseek": {
        "model": "deepseek-chat",
        "base_url": "https://api.deepseek.com",
        "api_key_config": "deepseek_api_key",
        "supports_response_format": True,
    },
    "groq": {
        "model": "llama-3.3-70b-versatile",
        "base_url": "https://api.groq.com/openai/v1/chat/completions",
        "api_key_config": "groq_api_key",
        "supports_response_format": True,
    },
    "openrouter": {
        "model": "openai/gpt-4o-mini",
        "base_url": "https://openrouter.ai/api/v1/chat/completions",
        "api_key_config": "openrouter_api_key",
        "supports_response_format": False,
    },
}

PLACEHOLDER_KEYS = {
    "your-openai-key",
    "your-deepseek-key",
    "your-groq-key",
    "your-openrouter-key",
}

JAPANESE_CHAR_PATTERN = re.compile(
    r"[\u3000-\u303F\u3040-\u309F\u30A0-\u30FF\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF]"
)


def load_addon_config():
    if not ANKI_AVAILABLE or mw is None:
        return dict(CONFIG_DEFAULTS)
    addon_config = mw.addonManager.getConfig(__name__) or {}
    return {**CONFIG_DEFAULTS, **addon_config}


config = load_addon_config()


def get_provider_defaults(provider):
    return PROVIDER_DEFAULTS.get(provider, PROVIDER_DEFAULTS["openai"])


def is_japanese_vocab(vocab_word):
    return bool(vocab_word and JAPANESE_CHAR_PATTERN.search(str(vocab_word)))


def normalize_api_key(api_key):
    api_key = (api_key or "").strip()
    if not api_key or api_key in PLACEHOLDER_KEYS:
        return ""
    return api_key


def chat_completions_url(base_url):
    if "/chat/completions" in base_url:
        return base_url
    return f"{base_url.rstrip('/')}/chat/completions"


def llm_api_request(payload, api_key, base_url, retries=3, provider="openai"):
    api_key = normalize_api_key(api_key)
    if not api_key:
        showInfo(f"{provider.capitalize()} API key is missing. Open VocBuilderAI Settings and add it.")
        return None

    full_url = chat_completions_url(base_url)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if provider == "openrouter":
        headers.update(
            {
                "HTTP-Referer": "https://ankiweb.net/shared/info/vocbuilderai",
                "X-Title": "VocBuilderAI",
            }
        )

    for attempt in range(retries):
        try:
            response = requests.post(full_url, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            return response
        except requests.exceptions.HTTPError as error:
            if attempt < retries - 1:
                time.sleep(2)
                continue

            try:
                response_body = response.json()
            except ValueError:
                response_body = response.text
            showInfo(
                "LLM HTTP error:\n"
                f"{error}\nStatus Code: {response.status_code}\nURL: {full_url}\nResponse: {response_body}"
            )
        except requests.exceptions.RequestException as error:
            if attempt < retries - 1:
                time.sleep(2)
                continue
            showInfo(f"LLM request error:\n{error}\nURL: {full_url}")
    return None


def generate_vocab_note(vocab_word: str, retries=3):
    provider = config.get("provider", "openai")
    provider_defaults = get_provider_defaults(provider)
    model = (config.get("model") or "").strip() or provider_defaults["model"]
    api_key = config.get(provider_defaults["api_key_config"])
    temperature = float(config.get("temperature", 0.5))
    max_tokens = int(config.get("max_tokens", 15000))

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": JPY_PROMPT if is_japanese_vocab(vocab_word) else VOC_PROMPT,
            },
            {"role": "user", "content": str(vocab_word)},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if provider_defaults.get("supports_response_format"):
        payload["response_format"] = {"type": "json_object"}

    response = llm_api_request(
        payload,
        api_key,
        provider_defaults["base_url"],
        retries=retries,
        provider=provider,
    )
    if response is None:
        return None

    try:
        response_json = response.json()
        return response_json["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, ValueError) as error:
        showInfo(f"LLM returned an unexpected response shape:\n{error}")
        return None


def clean_response(response: str) -> str:
    if response is None:
        return ""
    response = str(response).strip()

    fence_match = re.search(r"```(?:json)?\s*(.*?)\s*```", response, re.DOTALL | re.IGNORECASE)
    if fence_match:
        return fence_match.group(1).strip()

    first_brace = response.find("{")
    last_brace = response.rfind("}")
    if first_brace != -1 and last_brace != -1 and first_brace < last_brace:
        return response[first_brace : last_brace + 1].strip()

    return response


def process_response(response: str) -> dict:
    cleaned_response = clean_response(response)
    if not cleaned_response:
        showInfo("No note data was returned by the LLM.")
        return {}
    try:
        parsed = json.loads(cleaned_response)
    except json.JSONDecodeError as error:
        showInfo(f"Failed to parse note data: {error}\nContent: {cleaned_response}")
        return {}
    return parsed if isinstance(parsed, dict) else {}


def html_text(value, fallback=""):
    if value is None:
        return fallback
    return str(value)


def as_dict(value):
    return value if isinstance(value, dict) else {}


def as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def join_values(value):
    if isinstance(value, list):
        return ", ".join(str(item) for item in value if item is not None)
    return html_text(value)


def format_vocabulary_html(word):
    return f"<h2>{html_text(word)}</h2>"


def format_pronunciations_html(pronunciation):
    return f"<h3>Pronunciation:</h3><p>{html_text(pronunciation, 'N/A')}</p>"


def format_sound_html(sound_link):
    sound_link = html_text(sound_link)
    if not sound_link:
        return "<h3>Sound:</h3><p>N/A</p>"
    return f"<h3>Sound:</h3><a href='{sound_link}'>Listen</a>"


def format_meanings_html(meanings):
    meanings = as_dict(meanings)
    html_content = "<h3>Meanings:</h3><ul>"
    if not meanings:
        html_content += "<li>N/A</li>"
    for lang, meaning in meanings.items():
        html_content += f"<li><b>{html_text(lang).capitalize()}:</b> {html_text(meaning)}</li>"
    html_content += "</ul><br>"
    return html_content


forms_mapping = {
    "verb": join_values,
    "adjective": join_values,
    "noun": join_values,
}


def format_definitions_html(definitions):
    html_content = "<h3>Definitions:</h3><ol>"
    definitions = as_list(definitions)
    if not definitions:
        html_content += "<li>No definition</li>"
    for definition in definitions:
        if isinstance(definition, str):
            html_content += f"<li><b>{definition}</b></li>"
            continue

        definition = as_dict(definition)
        html_content += f"<li><b>{html_text(definition.get('text'), 'No definition')}</b>"
        grammatical_info = as_dict(definition.get("grammaticalInfo"))
        part_of_speech = grammatical_info.get("partOfSpeech")
        if part_of_speech:
            html_content += f" <i>({part_of_speech})</i>"

        forms = as_dict(grammatical_info.get("forms"))
        if forms:
            html_content += "<ul>"
            for form, values in forms.items():
                values_str = forms_mapping.get(form, join_values)(values)
                html_content += f"<li><b>{html_text(form).capitalize()}:</b> {values_str}</li>"
            html_content += "</ul>"
        html_content += "</li>"
    html_content += "</ol>"
    return html_content


def format_etymology_html(etymology):
    return f"<h3>Etymology:</h3><p>{html_text(etymology, 'N/A')}</p><br>"


def format_synonyms_html(synonyms):
    html_content = "<h3>Synonyms:</h3><ol>"
    for synonym in as_list(synonyms):
        html_content += f"<li>{html_text(synonym)}</li>"
    html_content += "</ol><br>"
    return html_content


def format_antonyms_html(antonyms):
    html_content = "<h3>Antonyms:</h3><ol>"
    for antonym in as_list(antonyms):
        html_content += f"<li>{html_text(antonym)}</li>"
    html_content += "</ol><br>"
    return html_content


def format_examples_html(vocab_word, examples):
    html_content = "<h3>Real-world Examples:</h3><ul>"
    for example in as_list(examples):
        example = html_text(example)
        bold_word = example.replace(str(vocab_word), f"<strong>{vocab_word}</strong>")
        html_content += f"<li>{bold_word}</li>"
    html_content += "</ul>"
    return html_content


def format_kanji_html(kanji):
    return f"<h3>Kanji:</h3><p>{html_text(kanji, 'N/A')}</p>"


def format_furigana_html(furigana):
    return f"<h3>Furigana:</h3><p>{html_text(furigana, 'N/A')}</p>"


def format_pitchPattern_html(pitchPattern):
    return f"<h3>Pitch Pattern:</h3><p>{html_text(pitchPattern, 'N/A')}</p>"


def format_explanations_html(explanations):
    explanations = as_dict(explanations)
    return (
        "<h3>Explanations:</h3>"
        f"<p>en-US: {html_text(explanations.get('en-US'), 'N/A')}</p>"
        f"<p>zh-TW: {html_text(explanations.get('zh-TW'), 'N/A')}</p>"
    )


def format_partsOfSpeech_html(partsOfSpeech):
    return f"<h3>Parts of Speech:</h3><p>{html_text(partsOfSpeech, 'N/A')}</p>"


def format_rule_group(title, rules, preferred_order=None):
    rules = as_dict(rules)
    if not rules:
        return ""

    html_content = f"<h4>{title}:</h4>"
    keys = preferred_order or list(rules.keys())
    rendered_keys = set()
    for key in keys:
        if key in rules and rules[key]:
            html_content += f"<p>{key}: {join_values(rules[key])}</p>"
            rendered_keys.add(key)
    for key, value in rules.items():
        if key not in rendered_keys and value:
            html_content += f"<p>{key}: {join_values(value)}</p>"
    return html_content


def format_grammaticalRules_html(grammaticalRules: dict):
    grammaticalRules = as_dict(grammaticalRules)
    html_content = "<h3>Grammatical Rules:</h3>"

    sections = [
        (
            "verbs",
            "verbs",
            [
                "PlainForm",
                "PoliteForm",
                "NegativeForm",
                "PastTense",
                "TeForm",
                "PotentialForm",
                "CausativeForm",
                "PassiveForm",
            ],
        ),
        (
            "adjectives",
            "adjectives",
            ["NegativeForm", "PastPositiveForm", "PastNegativeForm", "TeForm"],
        ),
        ("nouns", "nouns", ["Variations", "Examples"]),
        ("others", "others", None),
    ]

    rendered_any = False
    for key, title, preferred_order in sections:
        rendered = format_rule_group(title, grammaticalRules.get(key), preferred_order)
        if rendered:
            html_content += rendered
            rendered_any = True

    if not rendered_any:
        html_content += "<p>No grammatical rules found.</p>"
    return html_content


def format_exampleSentences_html(exampleSentences):
    html_content = "<h3>Example Sentences:</h3><ol>"
    for exampleSentence in as_list(exampleSentences):
        if isinstance(exampleSentence, str):
            sentence = exampleSentence
            translation = ""
        else:
            exampleSentence = as_dict(exampleSentence)
            sentence = exampleSentence.get("sentence", "")
            translation = (
                exampleSentence.get("translation")
                or exampleSentence.get("translation in zh-tw")
                or exampleSentence.get("translationInZhTw")
                or ""
            )
        html_content += f"<li><strong>{html_text(sentence)}</strong>"
        if translation:
            html_content += f" - {html_text(translation)}"
        html_content += "</li>"
    html_content += "</ol>"
    return html_content


def generate_speech(vocab_word, retries=3):
    api_key = normalize_api_key(config.get("openai_api_key"))
    if not api_key:
        return None

    base_url = "https://api.openai.com/v1"
    temp_file_path = None
    payload = {}
    for attempt in range(retries):
        try:
            hashed_vocab = hashlib.md5(str(vocab_word).encode()).hexdigest()
            temp_file_path = Path(__file__).parent / f"vocbuilderai-{hashed_vocab}.mp3"
            random_voice = [
                "alloy",
                "ash",
                "ballad",
                "coral",
                "echo",
                "fable",
                "nova",
                "onyx",
                "sage",
                "shimmer",
            ]
            speech_voice = config.get("speech_voice") or random.choice(random_voice)
            speech_model = config.get("speech_model") or "gpt-4o-mini-tts"
            input_text = str(vocab_word)

            payload = {
                "model": speech_model,
                "voice": speech_voice,
                "input": input_text,
                "instructions": "Speak clearly and naturally. Use Japanese pronunciation for Japanese text.",
                "speed": float(config.get("speech_speed", 1.0)),
            }

            response = requests.post(
                f"{base_url}/audio/speech",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=60,
            )
            response.raise_for_status()

            with open(temp_file_path, "wb") as audio_file:
                audio_file.write(response.content)

            final_file_name = mw.col.media.addFile(temp_file_path)
            temp_file_path.unlink(missing_ok=True)
            return final_file_name
        except Exception as error:
            if attempt < retries - 1:
                time.sleep(2)
                continue
            showInfo(f"Speech Error:\n{error}\nPayload: {payload}")
            if temp_file_path:
                temp_file_path.unlink(missing_ok=True)
            return None


def sound_reference(sound_file):
    return f"<br>[sound:{sound_file}]" if sound_file else ""


def populate_english_note(editor, note_data):
    word = note_data.get("word") or editor.note.fields[0]
    editor.note["vocabulary"] = format_vocabulary_html(word)
    editor.note["Pronunciations"] = format_pronunciations_html(note_data.get("pronunciation"))
    sound = generate_speech(word)
    editor.note["Sound"] = format_sound_html(note_data.get("soundLink")) + sound_reference(sound)
    editor.note["detail definition"] = format_meanings_html(note_data.get("meanings")) + format_definitions_html(
        note_data.get("definitions")
    )
    editor.note["Etymology, Synonyms and Antonyms"] = (
        format_etymology_html(note_data.get("etymology"))
        + format_synonyms_html(note_data.get("synonyms"))
        + format_antonyms_html(note_data.get("antonyms"))
    )
    editor.note["Real-world examples"] = format_examples_html(word, note_data.get("realWorldExamples"))


def populate_japanese_note(editor, note_data):
    vocabulary = note_data.get("vocabulary") or note_data.get("word") or editor.note.fields[0]
    explanations = note_data.get("explanations")
    sound = generate_speech(vocabulary)

    editor.note["vocabulary"] = format_vocabulary_html(vocabulary)
    editor.note["Pronunciations"] = format_partsOfSpeech_html(
        note_data.get("partsOfSpeech")
    ) + format_pronunciations_html(note_data.get("pronunciations"))
    editor.note["Sound"] = format_sound_html(note_data.get("sound")) + sound_reference(sound)
    editor.note["detail definition"] = (
        format_kanji_html(note_data.get("kanji", vocabulary))
        + "<br>"
        + format_furigana_html(note_data.get("furigana"))
        + "<br>"
        + format_pitchPattern_html(note_data.get("pitchPattern"))
        + "<br>"
        + format_meanings_html(explanations)
        + "<br>"
        + format_explanations_html(explanations)
    )
    editor.note["Etymology, Synonyms and Antonyms"] = format_grammaticalRules_html(
        note_data.get("grammaticalRules")
    )
    editor.note["Real-world examples"] = format_exampleSentences_html(note_data.get("exampleSentences"))


def on_add_note(editor: Editor):
    vocab_word = editor.note.fields[0]
    if not vocab_word:
        showInfo("No vocabulary word entered. Please enter a word in the 'vocabulary' field.")
        return

    response = generate_vocab_note(vocab_word)
    note_data = process_response(response)
    if not note_data:
        return

    try:
        if is_japanese_vocab(vocab_word):
            populate_japanese_note(editor, note_data)
        else:
            populate_english_note(editor, note_data)
        editor.loadNote()
    except Exception as error:
        showInfo(f"Error on add note: {error}")


def add_note_to_deck(deck_name, tag_name, note_data):  # pragma: no cover - requires a live Anki collection.
    if not ANKI_AVAILABLE:
        raise RuntimeError("Anki is required to add notes to a deck.")

    did = mw.col.decks.id(deck_name)
    mw.col.decks.select(did)

    model = mw.col.models.byName(config.get("note_type", "vocbuilderAI"))
    mw.col.models.setCurrent(model)

    note = Note(mw.col, model)
    if is_japanese_vocab(note_data.get("vocabulary") or note_data.get("word")):
        class _Editor:
            pass

        editor = _Editor()
        editor.note = note
        editor.note.fields = [note_data.get("vocabulary") or note_data.get("word")]
        populate_japanese_note(editor, note_data)
    else:
        class _Editor:
            pass

        editor = _Editor()
        editor.note = note
        editor.note.fields = [note_data.get("word")]
        populate_english_note(editor, note_data)

    note.addTag(tag_name)
    mw.col.addNote(note)
    mw.col.decks.save()
    mw.col.save()


def add_action_button(buttons, editor: Editor):  # pragma: no cover - requires Anki editor UI.
    button = editor.addButton(
        icon=None,
        label="VocAI",
        cmd="generate_vocab_content",
        func=lambda _, e=editor: on_add_note(e),
        tip="Generate vocabulary content",
        keys=None,
    )
    buttons.append(button)
    return buttons


if ANKI_AVAILABLE:  # pragma: no cover - Anki hook registration.
    gui_hooks.editor_did_init_buttons.append(add_action_button)


if ANKI_AVAILABLE:  # pragma: no cover - Qt settings UI requires Anki runtime.

    class ConfigDialog(QDialog):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setWindowTitle("VocBuilderAI Settings")
            self.setMinimumWidth(560)
            self.setup_ui()
            self.load_config()
            self.update_provider_hints()

        def setup_ui(self):
            layout = QVBoxLayout(self)
            self.tabs = QTabWidget()

            self.provider = QComboBox()
            self.provider.addItems(list(PROVIDER_DEFAULTS.keys()))
            self.provider.currentTextChanged.connect(self.update_provider_hints)

            self.model = QLineEdit()
            self.use_default_model = QCheckBox("Use provider default when model is blank")
            self.use_default_model.setChecked(True)
            use_default_button = QPushButton("Use default")
            use_default_button.clicked.connect(self.apply_default_model)

            model_row = QHBoxLayout()
            model_row.addWidget(self.model)
            model_row.addWidget(use_default_button)

            self.temperature = QDoubleSpinBox()
            self.temperature.setRange(0.0, 2.0)
            self.temperature.setSingleStep(0.1)
            self.temperature.setDecimals(2)

            self.max_tokens = QDoubleSpinBox()
            self.max_tokens.setRange(512, 32000)
            self.max_tokens.setSingleStep(512)
            self.max_tokens.setDecimals(0)

            self.provider_hint = QLabel()
            self.provider_hint.setWordWrap(True)

            generation_tab = QWidget()
            generation_layout = QVBoxLayout(generation_tab)
            provider_group = QGroupBox("Generation")
            provider_form = QFormLayout(provider_group)
            provider_form.addRow("Provider", self.provider)
            provider_form.addRow("Model", model_row)
            provider_form.addRow("", self.use_default_model)
            provider_form.addRow("Temperature", self.temperature)
            provider_form.addRow("Max tokens", self.max_tokens)
            provider_form.addRow("Current default", self.provider_hint)
            generation_layout.addWidget(provider_group)
            generation_layout.addStretch()
            self.tabs.addTab(generation_tab, "Generation")

            self.openai_key = self.api_key_input()
            self.deepseek_key = self.api_key_input()
            self.groq_key = self.api_key_input()
            self.openrouter_key = self.api_key_input()

            keys_tab = QWidget()
            keys_layout = QVBoxLayout(keys_tab)
            keys_group = QGroupBox("API Keys")
            keys_form = QFormLayout(keys_group)
            keys_form.addRow("OpenAI", self.openai_key)
            keys_form.addRow("DeepSeek", self.deepseek_key)
            keys_form.addRow("Groq", self.groq_key)
            keys_form.addRow("OpenRouter", self.openrouter_key)
            keys_layout.addWidget(keys_group)
            keys_layout.addStretch()
            self.tabs.addTab(keys_tab, "API Keys")

            self.default_deck = QLineEdit()
            self.default_tag = QLineEdit()
            self.note_type = QLineEdit()

            anki_tab = QWidget()
            anki_layout = QVBoxLayout(anki_tab)
            anki_group = QGroupBox("Anki Defaults")
            anki_form = QFormLayout(anki_group)
            anki_form.addRow("Default deck", self.default_deck)
            anki_form.addRow("Default tag", self.default_tag)
            anki_form.addRow("Note type", self.note_type)
            anki_layout.addWidget(anki_group)
            anki_layout.addStretch()
            self.tabs.addTab(anki_tab, "Anki")

            self.speech_voice = QComboBox()
            self.speech_voice.addItems(
                ["", "alloy", "ash", "ballad", "coral", "echo", "fable", "nova", "onyx", "sage", "shimmer"]
            )
            self.speech_model = QLineEdit()
            self.speech_speed = QDoubleSpinBox()
            self.speech_speed.setRange(0.25, 4.0)
            self.speech_speed.setSingleStep(0.25)
            self.speech_speed.setDecimals(2)

            speech_tab = QWidget()
            speech_layout = QVBoxLayout(speech_tab)
            speech_group = QGroupBox("Speech")
            speech_form = QFormLayout(speech_group)
            speech_form.addRow("Voice", self.speech_voice)
            speech_form.addRow("Model", self.speech_model)
            speech_form.addRow("Speed", self.speech_speed)
            speech_layout.addWidget(speech_group)
            speech_layout.addStretch()
            self.tabs.addTab(speech_tab, "Speech")

            layout.addWidget(self.tabs)

            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
            buttons.accepted.connect(self.save_config)
            buttons.rejected.connect(self.reject)
            layout.addWidget(buttons)

        def api_key_input(self):
            field = QLineEdit()
            field.setEchoMode(QLineEdit.EchoMode.Password)
            field.setClearButtonEnabled(True)
            return field

        def update_provider_hints(self):
            provider = self.provider.currentText()
            defaults = get_provider_defaults(provider)
            self.model.setPlaceholderText(defaults["model"])
            self.provider_hint.setText(f"{defaults['model']} at {defaults['base_url']}")

        def apply_default_model(self):
            self.model.setText(get_provider_defaults(self.provider.currentText())["model"])

        def load_config(self):
            self.provider.setCurrentText(config.get("provider", "openai"))
            self.openai_key.setText(config.get("openai_api_key", ""))
            self.deepseek_key.setText(config.get("deepseek_api_key", ""))
            self.groq_key.setText(config.get("groq_api_key", ""))
            self.openrouter_key.setText(config.get("openrouter_api_key", ""))
            self.model.setText(config.get("model", ""))
            self.temperature.setValue(float(config.get("temperature", 0.5)))
            self.max_tokens.setValue(float(config.get("max_tokens", 15000)))
            self.speech_voice.setCurrentText(config.get("speech_voice", ""))
            self.speech_model.setText(config.get("speech_model", "gpt-4o-mini-tts"))
            self.speech_speed.setValue(float(config.get("speech_speed", 1.0)))
            self.default_deck.setText(config.get("default_deck", "Big"))
            self.default_tag.setText(config.get("default_tag", "vocabulary::wordoftheday"))
            self.note_type.setText(config.get("note_type", "vocbuilderAI"))

        def save_config(self):
            new_config = {
                "provider": self.provider.currentText(),
                "openai_api_key": self.openai_key.text().strip(),
                "deepseek_api_key": self.deepseek_key.text().strip(),
                "groq_api_key": self.groq_key.text().strip(),
                "openrouter_api_key": self.openrouter_key.text().strip(),
                "model": self.model.text().strip(),
                "temperature": self.temperature.value(),
                "max_tokens": int(self.max_tokens.value()),
                "speech_voice": self.speech_voice.currentText(),
                "speech_model": self.speech_model.text().strip() or "gpt-4o-mini-tts",
                "speech_speed": self.speech_speed.value(),
                "default_deck": self.default_deck.text().strip() or "Big",
                "default_tag": self.default_tag.text().strip() or "vocabulary::wordoftheday",
                "note_type": self.note_type.text().strip() or "vocbuilderAI",
            }

            global config
            config.update(new_config)
            mw.addonManager.writeConfig(__name__, new_config)
            self.accept()


    def show_config():
        dialog = ConfigDialog(mw)
        dialog.exec()


    config_action = QAction("VocBuilderAI Settings", mw)
    config_action.triggered.connect(show_config)
    mw.form.menuTools.addAction(config_action)
