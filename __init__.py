import hashlib
import random
import re
import sys
import time
from pathlib import Path

import requests

try:  # pragma: no cover - exercised by Anki, not by headless tests.
    from .formatters import (
        as_dict,
        as_list,
        format_antonyms_html,
        format_definitions_html,
        format_etymology_html,
        format_exampleSentences_html,
        format_examples_html,
        format_explanations_html,
        format_furigana_html,
        format_grammaticalRules_html,
        format_kanji_html,
        format_meanings_html,
        format_partsOfSpeech_html,
        format_pitchPattern_html,
        format_pronunciations_html,
        format_rule_group,
        format_sound_html,
        format_synonyms_html,
        format_vocabulary_html,
        html_text,
        join_values,
    )
    from .llm import build_chat_payload, chat_completions_url, extract_chat_content
    from .llm import health_check as provider_health_check
    from .llm import llm_api_request as perform_llm_api_request
    from .parsing import clean_response, normalize_english_note_data, normalize_japanese_note_data
    from .parsing import process_response as parse_response
    from .prompts import JPY_PROMPT, VOC_PROMPT, with_generation_mode
    from .settings import (
        CONFIG_DEFAULTS,
        GENERATION_MODES,
        PLACEHOLDER_KEYS,
        PROVIDER_DEFAULTS,
        config_for_storage,
        get_provider_defaults,
        migrate_config,
        normalize_api_key,
        resolve_provider_defaults,
    )
except ImportError:
    from formatters import (
        as_dict,
        as_list,
        format_antonyms_html,
        format_definitions_html,
        format_etymology_html,
        format_exampleSentences_html,
        format_examples_html,
        format_explanations_html,
        format_furigana_html,
        format_grammaticalRules_html,
        format_kanji_html,
        format_meanings_html,
        format_partsOfSpeech_html,
        format_pitchPattern_html,
        format_pronunciations_html,
        format_rule_group,
        format_sound_html,
        format_synonyms_html,
        format_vocabulary_html,
        html_text,
        join_values,
    )
    from llm import build_chat_payload, chat_completions_url, extract_chat_content
    from llm import health_check as provider_health_check
    from llm import llm_api_request as perform_llm_api_request
    from parsing import clean_response, normalize_english_note_data, normalize_japanese_note_data
    from parsing import process_response as parse_response
    from prompts import JPY_PROMPT, VOC_PROMPT, with_generation_mode
    from settings import (
        CONFIG_DEFAULTS,
        GENERATION_MODES,
        PLACEHOLDER_KEYS,
        PROVIDER_DEFAULTS,
        config_for_storage,
        get_provider_defaults,
        migrate_config,
        normalize_api_key,
        resolve_provider_defaults,
    )

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

if not ANKI_AVAILABLE:  # pragma: no cover - keeps CLI smoke checks usable when aqt is installed.

    def showInfo(message):
        print(message)


JAPANESE_CHAR_PATTERN = re.compile(
    r"[\u3000-\u303F\u3040-\u309F\u30A0-\u30FF\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF]"
)


def load_addon_config():
    if not ANKI_AVAILABLE or mw is None:
        return migrate_config()
    addon_config = mw.addonManager.getConfig(__name__) or {}
    return migrate_config(addon_config)


config = load_addon_config()
GENERATION_CACHE = {}
CACHE_TTL_SECONDS = 300


def is_japanese_vocab(vocab_word):
    return bool(vocab_word and JAPANESE_CHAR_PATTERN.search(str(vocab_word)))


def llm_api_request(payload, api_key, base_url, retries=3, provider="openai"):
    return perform_llm_api_request(
        payload,
        api_key,
        base_url,
        retries=retries,
        provider=provider,
        notify=showInfo,
        post=requests.post,
        sleeper=time.sleep,
    )


def generation_cache_key(vocab_word, provider, model):
    return (
        str(vocab_word),
        provider,
        model,
        config.get("generation_mode", "standard"),
        float(config.get("temperature", 0.5)),
        int(config.get("max_tokens", 15000)),
    )


def get_cached_generation(cache_key):
    if not config.get("cache_enabled", True):
        return None
    cached = GENERATION_CACHE.get(cache_key)
    if not cached:
        return None
    timestamp, content = cached
    if time.time() - timestamp > CACHE_TTL_SECONDS:
        GENERATION_CACHE.pop(cache_key, None)
        return None
    return content


def set_cached_generation(cache_key, content):
    if config.get("cache_enabled", True) and content:
        GENERATION_CACHE[cache_key] = (time.time(), content)


def generate_vocab_note(vocab_word: str, retries=3):
    provider = config.get("provider", "openai")
    provider_defaults = resolve_provider_defaults(config)
    model = (config.get("model") or "").strip() or provider_defaults["model"]
    api_key = config.get(provider_defaults["api_key_config"])
    cache_key = generation_cache_key(vocab_word, provider, model)
    cached_content = get_cached_generation(cache_key)
    if cached_content is not None:
        return cached_content

    payload = build_chat_payload(
        vocab_word,
        prompt_for_vocab(vocab_word),
        config,
        provider_defaults,
    )

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
        content = extract_chat_content(response)
        set_cached_generation(cache_key, content)
        return content
    except (KeyError, IndexError, TypeError, ValueError) as error:
        showInfo(f"LLM returned an unexpected response shape:\n{error}")
        return None


def prompt_for_vocab(vocab_word):
    mode = config.get("generation_mode", "standard")
    if config.get("generation_mode") == "japanese" or is_japanese_vocab(vocab_word):
        return with_generation_mode(JPY_PROMPT, "japanese" if mode == "japanese" else mode)
    return with_generation_mode(VOC_PROMPT, mode)


def process_response(response: str) -> dict:
    return parse_response(response, notify=showInfo)


def run_api_health_check(sample_word="apple"):
    result = provider_health_check(
        config,
        prompt_for_vocab(sample_word),
        sample_word,
        notify=showInfo,
        post=requests.post,
        sleeper=time.sleep,
    )
    if not result.ok:
        return result
    note_data = process_response(result.message)
    if not note_data:
        return type(result)(False, "Provider responded, but the content was not valid note JSON.")
    return type(result)(True, "Provider connection and JSON parsing succeeded.")


def run_japanese_json_health_check():
    result = provider_health_check(
        config,
        with_generation_mode(JPY_PROMPT, "japanese"),
        "近い",
        notify=showInfo,
        post=requests.post,
        sleeper=time.sleep,
    )
    if not result.ok:
        return result
    note_data = normalize_japanese_note_data(process_response(result.message))
    if not note_data.get("vocabulary") or not isinstance(note_data.get("exampleSentences"), list):
        return type(result)(False, "Japanese response parsed, but required fields were incomplete.")
    return type(result)(True, "Japanese JSON generation and parsing succeeded.")


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
    note_data = normalize_english_note_data(note_data)
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
    note_data = normalize_japanese_note_data(note_data)
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

            self.generation_mode = QComboBox()
            for mode, details in GENERATION_MODES.items():
                self.generation_mode.addItem(details["label"], mode)

            self.model = QLineEdit()
            self.custom_base_url = QLineEdit()
            self.custom_response_format = QCheckBox("Request JSON response format")
            self.custom_disable_thinking = QCheckBox("Disable Qwen thinking")
            self.use_default_model = QCheckBox("Use provider default when model is blank")
            self.use_default_model.setChecked(True)
            self.cache_enabled = QCheckBox("Reuse recent identical generations")
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
            provider_form.addRow("Mode", self.generation_mode)
            provider_form.addRow("Model", model_row)
            provider_form.addRow("Custom base URL", self.custom_base_url)
            provider_form.addRow("", self.custom_response_format)
            provider_form.addRow("", self.custom_disable_thinking)
            provider_form.addRow("", self.use_default_model)
            provider_form.addRow("", self.cache_enabled)
            provider_form.addRow("Temperature", self.temperature)
            provider_form.addRow("Max tokens", self.max_tokens)
            provider_form.addRow("Current default", self.provider_hint)

            health_group = QGroupBox("Health Checks")
            health_layout = QHBoxLayout(health_group)
            test_api_button = QPushButton("Test API")
            test_api_button.clicked.connect(self.test_api)
            test_japanese_button = QPushButton("Test Japanese JSON")
            test_japanese_button.clicked.connect(self.test_japanese_json)
            health_layout.addWidget(test_api_button)
            health_layout.addWidget(test_japanese_button)

            generation_layout.addWidget(provider_group)
            generation_layout.addWidget(health_group)
            generation_layout.addStretch()
            self.tabs.addTab(generation_tab, "Generation")

            self.openai_key = self.api_key_input()
            self.groq_key = self.api_key_input()
            self.openrouter_key = self.api_key_input()
            self.custom_key = self.api_key_input()

            keys_tab = QWidget()
            keys_layout = QVBoxLayout(keys_tab)
            keys_group = QGroupBox("API Keys")
            keys_form = QFormLayout(keys_group)
            keys_form.addRow("OpenAI", self.openai_key)
            keys_form.addRow("Groq", self.groq_key)
            keys_form.addRow("OpenRouter", self.openrouter_key)
            keys_form.addRow("Custom", self.custom_key)
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
            test_speech_button = QPushButton("Test TTS")
            test_speech_button.clicked.connect(self.test_speech)
            speech_form.addRow("", test_speech_button)
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
            if hasattr(self, "custom_base_url"):
                is_custom = provider == "custom"
                self.custom_base_url.setEnabled(is_custom)
                self.custom_response_format.setEnabled(is_custom)
                self.custom_disable_thinking.setEnabled(is_custom)
            self.provider_hint.setText(f"{defaults['model']} at {defaults['base_url']}")

        def apply_default_model(self):
            self.model.setText(get_provider_defaults(self.provider.currentText())["model"])

        def current_generation_mode(self):
            return self.generation_mode.currentData() or "standard"

        def select_generation_mode(self, mode):
            index = self.generation_mode.findData(mode)
            self.generation_mode.setCurrentIndex(index if index >= 0 else 0)

        def current_form_config(self):
            return config_for_storage(
                {
                    **config,
                    "provider": self.provider.currentText(),
                    "openai_api_key": self.openai_key.text().strip(),
                    "groq_api_key": self.groq_key.text().strip(),
                    "openrouter_api_key": self.openrouter_key.text().strip(),
                    "custom_api_key": self.custom_key.text().strip(),
                    "custom_base_url": self.custom_base_url.text().strip(),
                    "custom_supports_response_format": self.custom_response_format.isChecked(),
                    "custom_disable_thinking": self.custom_disable_thinking.isChecked(),
                    "model": self.model.text().strip(),
                    "temperature": self.temperature.value(),
                    "max_tokens": int(self.max_tokens.value()),
                    "speech_voice": self.speech_voice.currentText(),
                    "speech_model": self.speech_model.text().strip() or "gpt-4o-mini-tts",
                    "speech_speed": self.speech_speed.value(),
                    "default_deck": self.default_deck.text().strip() or "Big",
                    "default_tag": self.default_tag.text().strip() or "vocabulary::wordoftheday",
                    "note_type": self.note_type.text().strip() or "vocbuilderAI",
                    "generation_mode": self.current_generation_mode(),
                    "cache_enabled": self.cache_enabled.isChecked(),
                }
            )

        def test_api(self):
            global config
            previous_config = dict(config)
            config.update(self.current_form_config())
            result = run_api_health_check("apple")
            config.clear()
            config.update(previous_config)
            showInfo(result.message)

        def test_japanese_json(self):
            global config
            previous_config = dict(config)
            config.update(self.current_form_config())
            result = run_japanese_json_health_check()
            config.clear()
            config.update(previous_config)
            showInfo(result.message)

        def test_speech(self):
            global config
            previous_config = dict(config)
            config.update(self.current_form_config())
            sound_file = generate_speech("VocBuilderAI", retries=1)
            config.clear()
            config.update(previous_config)
            if sound_file:
                showInfo("Text-to-speech generation succeeded.")
            else:
                showInfo("Text-to-speech generation failed. Check your OpenAI API key and speech settings.")

        def load_config(self):
            self.provider.setCurrentText(config.get("provider", "openai"))
            self.select_generation_mode(config.get("generation_mode", "standard"))
            self.cache_enabled.setChecked(bool(config.get("cache_enabled", True)))
            self.openai_key.setText(config.get("openai_api_key", ""))
            self.groq_key.setText(config.get("groq_api_key", ""))
            self.openrouter_key.setText(config.get("openrouter_api_key", ""))
            self.custom_key.setText(config.get("custom_api_key", ""))
            self.custom_base_url.setText(config.get("custom_base_url", ""))
            self.custom_response_format.setChecked(bool(config.get("custom_supports_response_format", False)))
            self.custom_disable_thinking.setChecked(bool(config.get("custom_disable_thinking", True)))
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
            new_config = self.current_form_config()

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
