import hashlib
import html
import random
import re
import sys
import tempfile
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
        format_grammarPoints_html,
        format_grammar_translation_html,
        format_grammaticalRules_html,
        format_kanji_html,
        format_math_back_html,
        format_meanings_html,
        format_partsOfSpeech_html,
        format_pitchPattern_html,
        format_pronunciations_html,
        format_rule_group,
        format_relatedGrammar_html,
        format_sound_html,
        format_synonyms_html,
        format_vocabulary_html,
        html_text,
        join_values,
    )
    from .llm import build_chat_payload, chat_completions_url, extract_chat_content, should_retry_status
    from .llm import health_check as provider_health_check
    from .llm import llm_api_request as perform_llm_api_request
    from .parsing import clean_response, normalize_english_note_data, normalize_japanese_grammar_data, normalize_japanese_note_data, normalize_math_note_data
    from .parsing import process_response as parse_response
    from .prompts import JPG_PROMPT, JPY_PROMPT, MATH_PROMPT, VOC_PROMPT, with_generation_mode
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
        format_grammarPoints_html,
        format_grammar_translation_html,
        format_grammaticalRules_html,
        format_kanji_html,
        format_math_back_html,
        format_meanings_html,
        format_partsOfSpeech_html,
        format_pitchPattern_html,
        format_pronunciations_html,
        format_relatedGrammar_html,
        format_rule_group,
        format_sound_html,
        format_synonyms_html,
        format_vocabulary_html,
        html_text,
        join_values,
    )
    from llm import build_chat_payload, chat_completions_url, extract_chat_content, should_retry_status
    from llm import health_check as provider_health_check
    from llm import llm_api_request as perform_llm_api_request
    from parsing import clean_response, normalize_english_note_data, normalize_japanese_grammar_data, normalize_japanese_note_data, normalize_math_note_data
    from parsing import process_response as parse_response
    from prompts import JPG_PROMPT, JPY_PROMPT, MATH_PROMPT, VOC_PROMPT, with_generation_mode
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
        QSpinBox,
        QTabWidget,
        QVBoxLayout,
        QWidget,
    )
    from aqt.utils import showInfo, tooltip
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
    def tooltip(message):
        print(message)


    class _UnavailableQt:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("Qt is only available inside Anki.")

    QAction = QCheckBox = QComboBox = QDialog = QDialogButtonBox = QDoubleSpinBox = _UnavailableQt
    QFormLayout = QFrame = QGroupBox = QHBoxLayout = QLabel = QLineEdit = _UnavailableQt
    QPushButton = QScrollArea = QSizePolicy = QSpinBox = QTabWidget = QVBoxLayout = QWidget = _UnavailableQt

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
SPEECH_CACHE = {}

OPENAI_TTS_VOICES = [
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
KOKORO_AMERICAN_VOICES = [
    "af_heart",
    "af_alloy",
    "af_aoede",
    "af_bella",
    "af_jessica",
    "af_kore",
    "af_nicole",
    "af_nova",
    "af_river",
    "af_sarah",
    "af_sky",
    "am_adam",
    "am_echo",
    "am_eric",
    "am_fenrir",
    "am_liam",
    "am_michael",
    "am_onyx",
    "am_puck",
    "am_santa",
]
KOKORO_RANDOM_AMERICAN_VOICES = [
    "af_bella",
    "af_nicole",
    "af_sarah",
    "af_sky",
    "am_adam",
    "am_michael",
]
KOKORO_JAPANESE_VOICES = [
    "jf_alpha",
    "jf_gongitsune",
    "jf_nezumi",
    "jf_tebukuro",
    "jm_kumo",
]
KOKORO_TTS_MODEL = "speaches-ai/Kokoro-82M-v1.0-ONNX"
KOKORO_LEGACY_ENGLISH_MODEL = "csukuangfj/kokoro-en-v0_19"


def is_japanese_vocab(vocab_word):
    return bool(vocab_word and JAPANESE_CHAR_PATTERN.search(str(vocab_word)))

CANONICAL_NOTE_FIELDS = [
    "vocabulary",
    "detail definition",
    "Pronunciations",
    "Sound",
    "Etymology, Synonyms and Antonyms",
    "Real-world examples",
]


MATH_CANONICAL_NOTE_FIELDS = ["Front", "Back"]


def clean_vocab_input(value):
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    text = html.unescape(text)
    return " ".join(text.split())


class MissingNoteFieldsError(ValueError):
    def __init__(self, missing, available):
        self.missing = list(missing)
        self.available = list(available)
        missing_lines = "\n".join(f"- {name}" for name in self.missing)
        available_text = ", ".join(self.available) if self.available else "(none)"
        super().__init__(
            "This note type is missing fields that VocBuilderAI writes:\n"
            f"{missing_lines}\n\n"
            f"Fields on this note type: {available_text}\n"
            "Add the missing fields (or rename existing ones) in Tools -> Manage Note Types."
        )


def _normalized_field_name(name):
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def resolve_note_fields(note, required_fields=CANONICAL_NOTE_FIELDS):
    """Map canonical field names onto the note's actual field keys.

    Matching ignores case, whitespace, and commas, so note types created with
    field lists like "Vocabulary" or "Etymology, Synonyms, and Antonyms" keep
    working. Raises MissingNoteFieldsError listing anything absent so users
    get a clear diagnostic before any API call is made.
    """
    try:
        available = list(note.keys())
    except Exception:
        available = []
    if not available:
        # Plain dict notes (tests, pre-population) accept canonical names.
        return {field: field for field in required_fields}
    normalized = {_normalized_field_name(key): key for key in available}
    mapping = {}
    missing = []
    for field in required_fields:
        actual = normalized.get(_normalized_field_name(field))
        if actual is None:
            missing.append(field)
        else:
            mapping[field] = actual
    if missing:
        raise MissingNoteFieldsError(missing, available)
    return mapping



def llm_api_request(payload, api_key, base_url, retries=3, provider="openai", notify=None):
    return perform_llm_api_request(
        payload,
        api_key,
        base_url,
        retries=retries,
        provider=provider,
        notify=notify or showInfo,
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
    if not (config.get("cache_enabled", True) and content):
        return
    now = time.time()
    for key, (timestamp, _cached) in list(GENERATION_CACHE.items()):
        if now - timestamp > CACHE_TTL_SECONDS:
            GENERATION_CACHE.pop(key, None)
    GENERATION_CACHE[cache_key] = (now, content)


def _generate_llm_content(vocab_word, system_prompt, retries=3, notify=None, cache_namespace=None):
    notify = notify or showInfo
    provider = config.get("provider", "openai")
    provider_defaults = resolve_provider_defaults(config)
    model = (config.get("model") or "").strip() or provider_defaults["model"]
    api_key = config.get(provider_defaults["api_key_config"])
    base_cache_key = generation_cache_key(vocab_word, provider, model)
    cache_key = (cache_namespace,) + base_cache_key if cache_namespace else base_cache_key
    cached_content = get_cached_generation(cache_key)
    if cached_content is not None:
        return cached_content

    payload = build_chat_payload(
        vocab_word,
        system_prompt,
        config,
        provider_defaults,
    )

    response = llm_api_request(
        payload,
        api_key,
        provider_defaults["base_url"],
        retries=retries,
        provider=provider,
        notify=notify,
    )
    if response is None:
        return None

    try:
        content = extract_chat_content(response)
        set_cached_generation(cache_key, content)
        return content
    except (KeyError, IndexError, TypeError, ValueError) as error:
        notify(f"LLM returned an unexpected response shape:\n{error}")
        return None


def generate_vocab_note(vocab_word: str, retries=3, notify=None):
    return _generate_llm_content(vocab_word, prompt_for_vocab(vocab_word), retries=retries, notify=notify)


def generate_grammar_note(grammar_input: str, retries=3, notify=None):
    mode = config.get("generation_mode", "standard")
    grammar_prompt = with_generation_mode(JPG_PROMPT, mode)
    return _generate_llm_content(
        grammar_input,
        grammar_prompt,
        retries=retries,
        notify=notify,
        cache_namespace="japanese-grammar",
    )


def generate_grammar_note_data(grammar_input, notify=None):
    response = generate_grammar_note(grammar_input, notify=notify)
    if response is None:
        return None
    return parse_response(response, notify=notify) or None


def generate_math_note(math_input: str, retries=3, notify=None):
    return _generate_llm_content(
        math_input,
        MATH_PROMPT,
        retries=retries,
        notify=notify,
        cache_namespace="math",
    )


def generate_math_note_data(math_input, notify=None):
    response = generate_math_note(math_input, notify=notify)
    if response is None:
        return None
    return parse_response(response, notify=notify) or None


def prompt_for_vocab(vocab_word):
    mode = config.get("generation_mode", "standard")
    if is_japanese_vocab(vocab_word):
        return with_generation_mode(JPY_PROMPT, mode)
    if mode == "japanese":
        # An English word typed while Japanese mode is selected would produce
        # an empty card; fall back to the English schema.
        mode = "standard"
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


def audio_speech_url(base_url):
    if "/audio/speech" in base_url:
        return base_url
    return f"{base_url.rstrip('/')}/audio/speech"


def speech_file_extension(response_format):
    response_format = (response_format or "mp3").strip().lower()
    if response_format in {"wav", "mp3", "opus", "aac", "flac", "pcm"}:
        return response_format
    return "mp3"


def speech_settings(input_text=""):
    provider = config.get("speech_provider", "openai")
    if provider not in {"openai", "custom"}:
        provider = "openai"
    is_japanese_text = is_japanese_vocab(input_text)

    if provider == "custom":
        api_key = normalize_api_key(config.get("speech_api_key"))
        base_url = config.get("speech_base_url") or CONFIG_DEFAULTS["speech_base_url"]
        configured_model = config.get("speech_model")
        model = (
            KOKORO_TTS_MODEL
            if configured_model in {"", "gpt-4o-mini-tts", KOKORO_LEGACY_ENGLISH_MODEL, None}
            else configured_model
        )
        response_format = config.get("speech_response_format") or "wav"
        if is_japanese_text:
            voices = KOKORO_JAPANESE_VOICES
            random_pool = KOKORO_JAPANESE_VOICES
        else:
            voices = KOKORO_AMERICAN_VOICES
            random_pool = KOKORO_RANDOM_AMERICAN_VOICES
    else:
        api_key = normalize_api_key(config.get("speech_api_key")) or normalize_api_key(config.get("openai_api_key"))
        base_url = "https://api.openai.com/v1"
        model = config.get("speech_model") or "gpt-4o-mini-tts"
        response_format = config.get("speech_response_format") or "mp3"
        voices = OPENAI_TTS_VOICES
        random_pool = OPENAI_TTS_VOICES

    configured_voice = config.get("speech_voice")
    if configured_voice in voices:
        voice = configured_voice
    else:
        # Seed per text so the same word always gets the same random voice;
        # repeated generations then produce identical media Anki can dedupe.
        random.seed(hashlib.md5(str(input_text).encode()).hexdigest())
        voice = random.choice(random_pool)
    return provider, api_key, audio_speech_url(base_url), model, voice, response_format


def fetch_speech_audio(vocab_word, retries=3, notify=None, settings=None):
    """Fetch spoken audio over the network. Returns (audio_bytes, extension) or None."""
    notify = notify or showInfo
    provider, api_key, url, speech_model, speech_voice, response_format = (
        settings or speech_settings(vocab_word)
    )
    if not api_key:
        return None

    payload = {
        "model": speech_model,
        "voice": speech_voice,
        "input": str(vocab_word),
    }
    if provider == "custom":
        payload["response_format"] = response_format
        payload["sample_rate"] = int(config.get("speech_sample_rate", 24000))
    else:
        payload["instructions"] = "Speak clearly and naturally. Use Japanese pronunciation for Japanese text."
        payload["speed"] = float(config.get("speech_speed", 1.0))
        if response_format != "mp3":
            payload["response_format"] = response_format

    for attempt in range(retries):
        try:
            response = requests.post(
                url,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=60,
            )
            response.raise_for_status()
            return response.content, speech_file_extension(response_format)
        except requests.exceptions.HTTPError as error:
            status = getattr(response, "status_code", None)
            if attempt < retries - 1 and should_retry_status(status):
                time.sleep(2)
                continue
            notify(f"Speech Error:\n{error}\nPayload: {payload}")
            return None
        except Exception as error:
            if attempt < retries - 1:
                time.sleep(2)
                continue
            notify(f"Speech Error:\n{error}\nPayload: {payload}")
            return None
    return None


def save_speech_media(audio_content, vocab_word, extension):
    hashed_vocab = hashlib.md5(str(vocab_word).encode()).hexdigest()
    temp_file_path = Path(__file__).parent / f"vocbuilderai-{hashed_vocab}.{extension}"
    try:
        with open(temp_file_path, "wb") as audio_file:
            audio_file.write(audio_content)
        return mw.col.media.addFile(temp_file_path)
    finally:
        temp_file_path.unlink(missing_ok=True)


def generate_speech(vocab_word, retries=3):
    settings = speech_settings(vocab_word)
    _provider, _api_key, _url, model, voice, response_format = settings
    cache_key = (str(vocab_word), model, voice, response_format)
    fetched = SPEECH_CACHE.pop(cache_key, None)
    if fetched is None:
        fetched = fetch_speech_audio(vocab_word, retries=retries, settings=settings)
    if fetched is None:
        return None
    audio_content, extension = fetched
    try:
        return save_speech_media(audio_content, vocab_word, extension)
    except Exception as error:
        showInfo(f"Speech Error:\n{error}")
        return None


def prewarm_speech(speech_text, notify=None):
    """Fetch TTS audio off the main thread so populate can reuse it without network."""
    settings = speech_settings(speech_text)
    fetched = fetch_speech_audio(speech_text, notify=notify, settings=settings)
    if fetched is None:
        return None
    _provider, _api_key, _url, model, voice, response_format = settings
    SPEECH_CACHE[(str(speech_text), model, voice, response_format)] = fetched
    return fetched


def prewarm_speech_for_note(vocab_word, note_data, notify=None):
    if is_japanese_vocab(vocab_word):
        speech_text = japanese_speech_text(note_data, vocab_word)
    else:
        speech_text = str(note_data.get("word") or vocab_word)
    prewarm_speech(speech_text, notify=notify)


def sound_reference(sound_file):
    return f"<br>[sound:{sound_file}]" if sound_file else ""


def populate_english_note(editor, note_data):
    note_data = normalize_english_note_data(note_data)
    field_map = resolve_note_fields(editor.note)
    word = note_data.get("word") or editor.note.fields[0]
    note = editor.note
    note[field_map["vocabulary"]] = format_vocabulary_html(word)
    note[field_map["Pronunciations"]] = (
        format_pronunciations_html(note_data.get("pronunciation")) if note_data.get("pronunciation") else ""
    )
    sound = generate_speech(word)
    note[field_map["Sound"]] = format_sound_html(note_data.get("soundLink")) + sound_reference(sound)
    note[field_map["detail definition"]] = format_meanings_html(note_data.get("meanings")) + format_definitions_html(
        note_data.get("definitions")
    )
    note[field_map["Etymology, Synonyms and Antonyms"]] = (
        format_etymology_html(note_data.get("etymology"))
        + format_synonyms_html(note_data.get("synonyms"))
        + format_antonyms_html(note_data.get("antonyms"))
    )
    note[field_map["Real-world examples"]] = format_examples_html(word, note_data.get("realWorldExamples"))


def japanese_speech_text(note_data, fallback):
    furigana = (note_data.get("furigana") or "").strip()
    if furigana:
        return furigana
    return fallback


def populate_japanese_note(editor, note_data):
    note_data = normalize_japanese_note_data(note_data)
    field_map = resolve_note_fields(editor.note)
    vocabulary = note_data.get("vocabulary") or note_data.get("word") or editor.note.fields[0]
    explanations = note_data.get("explanations")
    sound = generate_speech(japanese_speech_text(note_data, vocabulary))

    note = editor.note
    note[field_map["vocabulary"]] = format_vocabulary_html(vocabulary)
    pronunciation_sections = []
    if note_data.get("partsOfSpeech"):
        pronunciation_sections.append(format_partsOfSpeech_html(note_data.get("partsOfSpeech")))
    if note_data.get("pronunciations"):
        pronunciation_sections.append(format_pronunciations_html(note_data.get("pronunciations")))
    note[field_map["Pronunciations"]] = "".join(pronunciation_sections)
    note[field_map["Sound"]] = format_sound_html(note_data.get("sound")) + sound_reference(sound)
    definition_sections = [format_kanji_html(note_data.get("kanji") or vocabulary)]
    if note_data.get("furigana"):
        definition_sections.append(format_furigana_html(note_data.get("furigana")))
    if note_data.get("pitchPattern"):
        definition_sections.append(format_pitchPattern_html(note_data.get("pitchPattern")))
    definition_sections.append(format_meanings_html(explanations))
    definition_sections.append(format_explanations_html(explanations))
    note[field_map["detail definition"]] = "<br>".join(definition_sections)
    note[field_map["Etymology, Synonyms and Antonyms"]] = format_grammaticalRules_html(
        note_data.get("grammaticalRules")
    )
    note[field_map["Real-world examples"]] = format_exampleSentences_html(note_data.get("exampleSentences"))


def populate_japanese_grammar_note(editor, note_data):
    note_data = normalize_japanese_grammar_data(note_data)
    field_map = resolve_note_fields(editor.note)
    sentence = note_data.get("sentence") or editor.note.fields[0]
    speech_text = (note_data.get("reading") or "").strip() or sentence
    sound = generate_speech(speech_text)

    note = editor.note
    note[field_map["vocabulary"]] = format_vocabulary_html(sentence)
    note[field_map["Pronunciations"]] = (
        format_pronunciations_html(note_data.get("reading")) if note_data.get("reading") else ""
    )
    note[field_map["Sound"]] = sound_reference(sound)
    detail_sections = [
        format_grammar_translation_html(note_data.get("translation")),
        format_grammarPoints_html(note_data.get("grammarPoints")),
    ]
    note[field_map["detail definition"]] = "<br>".join(section for section in detail_sections if section)
    note[field_map["Etymology, Synonyms and Antonyms"]] = format_relatedGrammar_html(
        note_data.get("relatedGrammar")
    )
    note[field_map["Real-world examples"]] = format_exampleSentences_html(note_data.get("exampleSentences"))


def populate_math_note(editor, note_data):
    note_data = normalize_math_note_data(note_data)
    field_map = resolve_note_fields(editor.note, required_fields=MATH_CANONICAL_NOTE_FIELDS)
    editor.note[field_map["Back"]] = format_math_back_html(note_data)


def generate_note_data(vocab_word, notify=None):
    response = generate_vocab_note(vocab_word, notify=notify)
    if response is None:
        return None
    return parse_response(response, notify=notify) or None


def on_add_note(editor: Editor):
    vocab_word = clean_vocab_input(editor.note.fields[0])
    if not vocab_word:
        showInfo("No vocabulary word entered. Please enter a word in the 'vocabulary' field.")
        return
    try:
        resolve_note_fields(editor.note)
    except MissingNoteFieldsError as error:
        showInfo(str(error))
        return

    def work():
        messages = []
        note_data = generate_note_data(vocab_word, notify=messages.append)
        if note_data is not None:
            prewarm_speech_for_note(vocab_word, note_data, notify=messages.append)
        return note_data, messages

    def finish(result):
        note_data, messages = result
        for message in messages:
            showInfo(message)
        if note_data is None:
            return
        try:
            if is_japanese_vocab(vocab_word):
                populate_japanese_note(editor, note_data)
            else:
                populate_english_note(editor, note_data)
            editor.loadNote()
        except Exception as error:
            showInfo(f"Error on add note: {error}")

    taskman = getattr(mw, "taskman", None) if ANKI_AVAILABLE else None
    if taskman is not None:
        tooltip("VocBuilderAI: generating…")

        def on_done(future):
            try:
                finish(future.result())
            except Exception as error:
                showInfo(f"Error on add note: {error}")

        taskman.run_in_background(work, on_done, uses_collection=False)
    else:
        finish(work())


def on_add_grammar_note(editor: Editor):
    grammar_input = clean_vocab_input(editor.note.fields[0])
    if not grammar_input:
        showInfo("No Japanese sentence entered. Please enter a sentence in the 'vocabulary' field.")
        return
    if not is_japanese_vocab(grammar_input):
        showInfo("Grammar explanation expects a Japanese sentence or pattern.")
        return
    try:
        resolve_note_fields(editor.note)
    except MissingNoteFieldsError as error:
        showInfo(str(error))
        return

    def work():
        messages = []
        note_data = generate_grammar_note_data(grammar_input, notify=messages.append)
        if note_data is not None:
            reading = (note_data.get("reading") or "").strip()
            prewarm_speech(reading or grammar_input, notify=messages.append)
        return note_data, messages

    def finish(result):
        note_data, messages = result
        for message in messages:
            showInfo(message)
        if note_data is None:
            return
        try:
            populate_japanese_grammar_note(editor, note_data)
            editor.loadNote()
        except Exception as error:
            showInfo(f"Error on grammar note: {error}")

    taskman = getattr(mw, "taskman", None) if ANKI_AVAILABLE else None
    if taskman is not None:
        tooltip("VocBuilderAI: explaining grammar…")

        def on_done(future):
            try:
                finish(future.result())
            except Exception as error:
                showInfo(f"Error on grammar note: {error}")

        taskman.run_in_background(work, on_done, uses_collection=False)
    else:
        finish(work())


def on_add_math_note(editor: Editor):
    math_input = clean_vocab_input(editor.note.fields[0])
    if not math_input:
        showInfo("No math input entered. Please enter a formula or question in the first field.")
        return
    try:
        resolve_note_fields(editor.note, required_fields=MATH_CANONICAL_NOTE_FIELDS)
    except MissingNoteFieldsError as error:
        showInfo(str(error))
        return

    def work():
        messages = []
        note_data = generate_math_note_data(math_input, notify=messages.append)
        return note_data, messages

    def finish(result):
        note_data, messages = result
        for message in messages:
            showInfo(message)
        if note_data is None:
            return
        try:
            populate_math_note(editor, note_data)
            editor.loadNote()
        except Exception as error:
            showInfo(f"Error on math note: {error}")

    taskman = getattr(mw, "taskman", None) if ANKI_AVAILABLE else None
    if taskman is not None:
        tooltip("VocBuilderAI: generating math card…")

        def on_done(future):
            try:
                finish(future.result())
            except Exception as error:
                showInfo(f"Error on math note: {error}")

        taskman.run_in_background(work, on_done, uses_collection=False)
    else:
        finish(work())


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


def _icon_file(name, svg):
    """Write an inline SVG to a temp file and return its absolute path.

    Anki's editor converts absolute icon paths to data URIs itself
    (aqt.editor.NewEditor._addButton); passing our own data URI would be
    misread as a bundled image name and render broken.

    Icons are decoration only: any filesystem failure returns "" so module
    import cannot break, and callers fall back to text labels.
    """
    try:
        icon_dir = Path(tempfile.gettempdir()) / "vocbuilder_ai_icons"
        icon_dir.mkdir(parents=True, exist_ok=True)
        path = icon_dir / name
        path.write_text(svg, encoding="utf-8")
        return str(path)
    except OSError:
        return ""


VOCAI_BUTTON_ICON = _icon_file(
    "vocai.svg",
    '<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22">'
    '<rect x="1" y="1" width="20" height="20" rx="5" fill="#3566a5"/>'
    '<text x="11" y="15" font-family="sans-serif" font-size="10" font-weight="bold" '
    'fill="#fff" text-anchor="middle">A字</text></svg>',
)


GRAMMAR_BUTTON_ICON = _icon_file(
    "grammar.svg",
    '<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22">'
    '<rect x="1" y="1" width="20" height="20" rx="5" fill="#2e8b57"/>'
    '<text x="11" y="14.5" font-family="sans-serif" font-size="9" font-weight="bold" '
    'fill="#fff" text-anchor="middle">文法</text></svg>',
)


MATH_BUTTON_ICON = _icon_file(
    "math.svg",
    '<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22">'
    '<rect x="1" y="1" width="20" height="20" rx="5" fill="#7048b6"/>'
    '<text x="11" y="16.5" font-family="sans-serif" font-size="13" font-weight="bold" '
    'fill="#fff" text-anchor="middle">∑</text></svg>',
)


def add_action_button(buttons, editor: Editor):  # pragma: no cover - requires Anki editor UI.
    button = editor.addButton(
        icon=VOCAI_BUTTON_ICON,
        label="VocAI" if not VOCAI_BUTTON_ICON else "",
        cmd="generate_vocab_content",
        func=lambda _, e=editor: on_add_note(e),
        tip="VocBuilderAI: Generate vocabulary content (VocAI)",
        keys=None,
    )
    buttons.append(button)

    grammar_button = editor.addButton(
        icon=GRAMMAR_BUTTON_ICON,
        label="文法" if not GRAMMAR_BUTTON_ICON else "",
        cmd="generate_japanese_grammar",
        func=lambda _, e=editor: on_add_grammar_note(e),
        tip="VocBuilderAI: Explain Japanese grammar of the entered sentence (文法)",
        keys=None,
    )
    buttons.append(grammar_button)
    math_button = editor.addButton(
        icon=MATH_BUTTON_ICON,
        label="∑" if not MATH_BUTTON_ICON else "",
        cmd="generate_math_card",
        func=lambda _, e=editor: on_add_math_note(e),
        tip="VocBuilderAI: Generate the back of a math card for the entered formula or question (∑)",
        keys=None,
    )
    buttons.append(math_button)
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

            self.speech_provider = QComboBox()
            self.speech_provider.addItems(["openai", "custom"])
            self.speech_provider.currentTextChanged.connect(self.update_speech_hints)
            self.speech_key = self.api_key_input()
            self.speech_base_url = QLineEdit()
            self.speech_voice = QComboBox()
            self.speech_voice.addItems([""] + OPENAI_TTS_VOICES + KOKORO_AMERICAN_VOICES)
            self.speech_model = QLineEdit()
            self.speech_response_format = QComboBox()
            self.speech_response_format.addItems(["", "mp3", "wav", "opus", "aac", "flac", "pcm"])
            self.speech_sample_rate = QSpinBox()
            self.speech_sample_rate.setRange(8000, 48000)
            self.speech_sample_rate.setSingleStep(1000)
            self.speech_speed = QDoubleSpinBox()
            self.speech_speed.setRange(0.25, 4.0)
            self.speech_speed.setSingleStep(0.25)
            self.speech_speed.setDecimals(2)

            speech_tab = QWidget()
            speech_layout = QVBoxLayout(speech_tab)
            speech_group = QGroupBox("Speech")
            speech_form = QFormLayout(speech_group)
            speech_form.addRow("Provider", self.speech_provider)
            speech_form.addRow("Speech API key", self.speech_key)
            speech_form.addRow("Custom base URL", self.speech_base_url)
            speech_form.addRow("Voice", self.speech_voice)
            speech_form.addRow("Model", self.speech_model)
            speech_form.addRow("Format", self.speech_response_format)
            speech_form.addRow("Sample rate", self.speech_sample_rate)
            speech_form.addRow("Speed", self.speech_speed)
            test_speech_button = QPushButton("Test TTS")
            test_speech_button.clicked.connect(self.test_speech)
            speech_form.addRow("", test_speech_button)
            speech_layout.addWidget(speech_group)
            speech_layout.addStretch()
            self.tabs.addTab(speech_tab, "Speech")
            self.update_speech_hints()

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

        def update_speech_hints(self):
            if not hasattr(self, "speech_base_url"):
                return
            is_custom = self.speech_provider.currentText() == "custom"
            self.speech_base_url.setEnabled(is_custom)
            self.speech_sample_rate.setEnabled(is_custom)
            self.speech_speed.setEnabled(not is_custom)
            self.speech_model.setPlaceholderText(
                KOKORO_TTS_MODEL if is_custom else "gpt-4o-mini-tts"
            )

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
                    "speech_provider": self.speech_provider.currentText(),
                    "speech_api_key": self.speech_key.text().strip(),
                    "speech_base_url": self.speech_base_url.text().strip(),
                    "speech_voice": self.speech_voice.currentText(),
                    "speech_model": self.speech_model.text().strip(),
                    "speech_response_format": self.speech_response_format.currentText(),
                    "speech_sample_rate": self.speech_sample_rate.value(),
                    "speech_speed": self.speech_speed.value(),
                    "default_deck": self.default_deck.text().strip() or "Big",
                    "default_tag": self.default_tag.text().strip() or "vocabulary::wordoftheday",
                    "note_type": self.note_type.text().strip() or "vocbuilderAI",
                    "generation_mode": self.current_generation_mode(),
                    "cache_enabled": self.cache_enabled.isChecked(),
                }
            )

        def test_api(self):
            previous_config = dict(config)
            config.update(self.current_form_config())
            try:
                result = run_api_health_check("apple")
            finally:
                config.clear()
                config.update(previous_config)
            showInfo(result.message)

        def test_japanese_json(self):
            previous_config = dict(config)
            config.update(self.current_form_config())
            try:
                result = run_japanese_json_health_check()
            finally:
                config.clear()
                config.update(previous_config)
            showInfo(result.message)

        def test_speech(self):
            previous_config = dict(config)
            config.update(self.current_form_config())
            try:
                sound_file = generate_speech("VocBuilderAI", retries=1)
            finally:
                config.clear()
                config.update(previous_config)
            if sound_file:
                showInfo("Text-to-speech generation succeeded.")
            else:
                showInfo("Text-to-speech generation failed. Check your speech provider, API key, and settings.")

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
            self.speech_provider.setCurrentText(config.get("speech_provider", "openai"))
            self.speech_key.setText(config.get("speech_api_key", ""))
            self.speech_base_url.setText(config.get("speech_base_url", ""))
            self.speech_voice.setCurrentText(config.get("speech_voice", ""))
            self.speech_model.setText(config.get("speech_model", "gpt-4o-mini-tts"))
            self.speech_response_format.setCurrentText(config.get("speech_response_format", ""))
            self.speech_sample_rate.setValue(int(config.get("speech_sample_rate", 24000)))
            self.speech_speed.setValue(float(config.get("speech_speed", 1.0)))
            self.update_speech_hints()
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
