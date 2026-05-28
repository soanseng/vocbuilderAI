import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace


def load_addon():
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    spec = importlib.util.spec_from_file_location("vocbuilderai_addon", root / "__init__.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


addon = load_addon()
import llm
import prompts


def setup_function():
    addon.GENERATION_CACHE.clear()


class DummyNote(dict):
    def __init__(self, fields):
        super().__init__()
        self.fields = fields


class DummyEditor:
    def __init__(self, word):
        self.note = DummyNote([word])
        self.loaded = False

    def loadNote(self):
        self.loaded = True


def test_process_response_accepts_fenced_json():
    response = '```json\n{"word": "apple", "pronunciation": "ap-ul"}\n```'

    assert addon.process_response(response) == {"word": "apple", "pronunciation": "ap-ul"}


def test_process_response_handles_none_without_crashing(monkeypatch):
    messages = []
    monkeypatch.setattr(addon, "showInfo", messages.append)

    assert addon.process_response(None) == {}
    assert messages == ["No note data was returned by the LLM."]


def test_japanese_note_population_tolerates_sparse_openrouter_response(monkeypatch):
    monkeypatch.setattr(addon, "generate_speech", lambda word: None)
    editor = DummyEditor("近い")
    note_data = {
        "vocabulary": "近い",
        "explanations": {"zh-TW": "近的"},
        "grammaticalRules": {
            "adjectives": {
                "NegativeForm": "近くない",
            }
        },
        "exampleSentences": [
            {"sentence": "駅に近いです。", "translation in zh-tw": "離車站很近。"}
        ],
    }

    addon.populate_japanese_note(editor, note_data)

    assert editor.note["vocabulary"] == "<h2>近い</h2>"
    assert "近くない" in editor.note["Etymology, Synonyms and Antonyms"]
    assert "離車站很近。" in editor.note["Real-world examples"]


def test_on_add_note_handles_missing_llm_response_without_crashing(monkeypatch):
    messages = []
    editor = DummyEditor("近い")
    monkeypatch.setattr(addon, "generate_vocab_note", lambda word: None)
    monkeypatch.setattr(addon, "showInfo", messages.append)

    addon.on_add_note(editor)

    assert editor.loaded is False
    assert messages == ["No note data was returned by the LLM."]


def test_openrouter_generation_omits_response_format(monkeypatch):
    captured = {}

    class Response:
        def json(self):
            return {"choices": [{"message": {"content": json.dumps({"vocabulary": "近い"})}}]}

    def fake_request(payload, api_key, base_url, retries=3, provider="openai"):
        captured.update(
            {
                "payload": payload,
                "api_key": api_key,
                "base_url": base_url,
                "provider": provider,
            }
        )
        return Response()

    monkeypatch.setattr(addon, "llm_api_request", fake_request)
    monkeypatch.setitem(addon.config, "provider", "openrouter")
    monkeypatch.setitem(addon.config, "model", "")
    monkeypatch.setitem(addon.config, "openrouter_api_key", "test-key")

    result = addon.generate_vocab_note("近い")

    assert json.loads(result) == {"vocabulary": "近い"}
    assert captured["provider"] == "openrouter"
    assert captured["payload"]["model"] == "openai/gpt-4o-mini"
    assert captured["payload"]["max_tokens"] == 15000
    assert "max_completion_tokens" not in captured["payload"]
    assert "response_format" not in captured["payload"]


def test_openai_generation_includes_json_response_format(monkeypatch):
    captured = {}

    class Response:
        def json(self):
            return {"choices": [{"message": {"content": json.dumps({"word": "apple"})}}]}

    def fake_request(payload, api_key, base_url, retries=3, provider="openai"):
        captured.update({"payload": payload, "api_key": api_key, "base_url": base_url, "provider": provider})
        return Response()

    monkeypatch.setattr(addon, "llm_api_request", fake_request)
    monkeypatch.setitem(addon.config, "provider", "openai")
    monkeypatch.setitem(addon.config, "model", "")
    monkeypatch.setitem(addon.config, "openai_api_key", "test-key")

    result = addon.generate_vocab_note("apple")

    assert json.loads(result) == {"word": "apple"}
    assert captured["provider"] == "openai"
    assert captured["payload"]["model"] == "5.4-nano"
    assert captured["payload"]["max_completion_tokens"] == 15000
    assert "max_tokens" not in captured["payload"]
    assert captured["payload"]["response_format"] == {"type": "json_object"}


def test_custom_generation_uses_configured_litellm_endpoint(monkeypatch):
    captured = {}

    class Response:
        def json(self):
            return {"choices": [{"message": {"content": json.dumps({"word": "apple"})}}]}

    def fake_request(payload, api_key, base_url, retries=3, provider="openai"):
        captured.update({"payload": payload, "api_key": api_key, "base_url": base_url, "provider": provider})
        return Response()

    monkeypatch.setattr(addon, "llm_api_request", fake_request)
    monkeypatch.setitem(addon.config, "provider", "custom")
    monkeypatch.setitem(addon.config, "model", "")
    monkeypatch.setitem(addon.config, "custom_api_key", "litellm-key")
    monkeypatch.setitem(addon.config, "custom_base_url", "http://your-litellm-server:4000/v1")
    monkeypatch.setitem(addon.config, "custom_supports_response_format", False)
    monkeypatch.setitem(addon.config, "custom_disable_thinking", True)

    result = addon.generate_vocab_note("apple")

    assert json.loads(result) == {"word": "apple"}
    assert captured["provider"] == "custom"
    assert captured["api_key"] == "litellm-key"
    assert captured["base_url"] == "http://your-litellm-server:4000/v1"
    assert captured["payload"]["model"] == "qwen36-fast"
    assert captured["payload"]["max_tokens"] == 15000
    assert captured["payload"]["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}
    assert "response_format" not in captured["payload"]


def test_custom_generation_can_request_json_response_format(monkeypatch):
    monkeypatch.setitem(addon.config, "custom_supports_response_format", True)
    monkeypatch.setitem(addon.config, "custom_disable_thinking", False)
    defaults = addon.resolve_provider_defaults({**addon.config, "provider": "custom"})

    payload = addon.build_chat_payload("apple", addon.prompt_for_vocab("apple"), {**addon.config, "model": ""}, defaults)

    assert payload["response_format"] == {"type": "json_object"}
    assert "extra_body" not in payload


def test_generate_vocab_note_reuses_recent_cache(monkeypatch):
    calls = []

    class Response:
        def json(self):
            return {"choices": [{"message": {"content": json.dumps({"word": "apple"})}}]}

    def fake_request(*args, **kwargs):
        calls.append("call")
        return Response()

    monkeypatch.setattr(addon, "llm_api_request", fake_request)
    monkeypatch.setitem(addon.config, "provider", "openai")
    monkeypatch.setitem(addon.config, "model", "")
    monkeypatch.setitem(addon.config, "openai_api_key", "test-key")
    monkeypatch.setitem(addon.config, "cache_enabled", True)

    assert json.loads(addon.generate_vocab_note("apple")) == {"word": "apple"}
    assert json.loads(addon.generate_vocab_note("apple")) == {"word": "apple"}
    assert calls == ["call"]


def test_generate_vocab_note_cache_can_be_disabled(monkeypatch):
    calls = []

    class Response:
        def json(self):
            return {"choices": [{"message": {"content": json.dumps({"word": "apple"})}}]}

    def fake_request(*args, **kwargs):
        calls.append("call")
        return Response()

    monkeypatch.setattr(addon, "llm_api_request", fake_request)
    monkeypatch.setitem(addon.config, "provider", "openai")
    monkeypatch.setitem(addon.config, "model", "")
    monkeypatch.setitem(addon.config, "openai_api_key", "test-key")
    monkeypatch.setitem(addon.config, "cache_enabled", False)

    addon.generate_vocab_note("apple")
    addon.generate_vocab_note("apple")

    assert calls == ["call", "call"]


def test_generation_cache_expires(monkeypatch):
    cache_key = ("apple", "openai", "5.4-nano", "standard", 0.5, 15000)
    monkeypatch.setitem(addon.config, "cache_enabled", True)
    monkeypatch.setattr(addon.time, "time", lambda: 1000)
    addon.set_cached_generation(cache_key, "cached")
    monkeypatch.setattr(addon.time, "time", lambda: 1000 + addon.CACHE_TTL_SECONDS + 1)

    assert addon.get_cached_generation(cache_key) is None
    assert cache_key not in addon.GENERATION_CACHE


def test_clean_response_extracts_json_from_preface():
    response = 'Here is the result:\n{"word": "apple"}\nThanks.'

    assert addon.clean_response(response) == '{"word": "apple"}'


def test_process_response_rejects_invalid_json(monkeypatch):
    messages = []
    monkeypatch.setattr(addon, "showInfo", messages.append)

    assert addon.process_response("{not valid") == {}
    assert messages[0].startswith("Failed to parse note data:")


def test_process_response_rejects_non_object_json():
    assert addon.process_response('["not", "an", "object"]') == {}


def test_small_helpers_normalize_values():
    assert addon.get_provider_defaults("missing") == addon.PROVIDER_DEFAULTS["openai"]
    assert addon.normalize_api_key(" your-real-key ") == "your-real-key"
    assert addon.normalize_api_key("your-groq-key") == ""
    assert addon.chat_completions_url("https://api.example.com/v1") == "https://api.example.com/v1/chat/completions"
    assert addon.chat_completions_url("https://api.example.com/v1/chat/completions").endswith("/chat/completions")
    assert addon.is_japanese_vocab("近い") is True
    assert addon.is_japanese_vocab("apple") is False
    assert addon.as_list(("a", "b")) == ["a", "b"]
    assert addon.as_list("a") == ["a"]
    assert addon.join_values(["a", None, "b"]) == "a, b"
    assert addon.sound_reference("x.mp3") == "<br>[sound:x.mp3]"
    assert addon.sound_reference(None) == ""


def test_english_note_population_tolerates_sparse_response(monkeypatch):
    monkeypatch.setattr(addon, "generate_speech", lambda word: "apple.mp3")
    editor = DummyEditor("apple")
    note_data = {
        "word": "apple",
        "meanings": {"traditionalChinese": "蘋果"},
        "definitions": ["a fruit"],
        "realWorldExamples": ["I ate an apple."],
    }

    addon.populate_english_note(editor, note_data)

    assert editor.note["vocabulary"] == "<h2>apple</h2>"
    assert "[sound:apple.mp3]" in editor.note["Sound"]
    assert "蘋果" in editor.note["detail definition"]
    assert "<strong>apple</strong>" in editor.note["Real-world examples"]


def test_format_definitions_handles_dict_forms_and_strings():
    html = addon.format_definitions_html(
        [
            {
                "text": "to move quickly",
                "grammaticalInfo": {
                    "partOfSpeech": "verb",
                    "forms": {"verb": ["run", "ran", "run"]},
                },
            },
            "a quick trip",
        ]
    )

    assert "to move quickly" in html
    assert "run, ran, run" in html
    assert "a quick trip" in html


def test_formatters_render_empty_fallbacks():
    assert "N/A" in addon.format_sound_html("")
    assert "N/A" in addon.format_meanings_html(None)
    assert "No definition" in addon.format_definitions_html(None)
    assert "No grammatical rules found" in addon.format_grammaticalRules_html(None)
    assert "N/A" in addon.format_etymology_html(None)
    assert addon.format_synonyms_html(None).startswith("<h3>Synonyms")
    assert addon.format_antonyms_html(None).startswith("<h3>Antonyms")


def test_format_example_sentences_accepts_translation_variants():
    html = addon.format_exampleSentences_html(
        [
            {"sentence": "駅に近いです。", "reading": "えきにちかいです。", "translation in zh-tw": "離車站很近。"},
            {"sentence": "近いです。", "furigana": "ちかいです。", "translation": "很近。"},
            "近い。",
        ]
    )

    assert html.count("<li>") == 3
    assert "えきにちかいです。" in html
    assert "ちかいです。" in html
    assert "離車站很近。" in html
    assert "很近。" in html


def test_llm_api_request_adds_openrouter_headers(monkeypatch):
    captured = {}

    class Response:
        status_code = 200
        text = "{}"

        def raise_for_status(self):
            return None

    def fake_post(url, headers, json, timeout):
        captured.update({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return Response()

    monkeypatch.setattr(addon.requests, "post", fake_post)

    result = addon.llm_api_request(
        {"model": "openai/gpt-4o-mini"},
        "test-key",
        "https://openrouter.ai/api/v1/chat/completions",
        retries=1,
        provider="openrouter",
    )

    assert result is not None
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["headers"]["X-Title"] == "VocBuilderAI"
    assert captured["url"].endswith("/chat/completions")


def test_llm_api_request_missing_key_returns_none(monkeypatch):
    messages = []
    monkeypatch.setattr(addon, "showInfo", messages.append)

    result = addon.llm_api_request({}, "your-openai-key", "https://api.openai.com/v1", retries=1)

    assert result is None
    assert "API key is missing" in messages[0]


def test_llm_api_request_reports_http_error_json(monkeypatch):
    messages = []

    class Response:
        status_code = 400
        text = "bad request"

        def raise_for_status(self):
            raise addon.requests.exceptions.HTTPError("bad")

        def json(self):
            return {"error": "bad request"}

    monkeypatch.setattr(addon, "showInfo", messages.append)
    monkeypatch.setattr(addon.requests, "post", lambda *args, **kwargs: Response())

    result = addon.llm_api_request({}, "test-key", "https://api.openai.com/v1", retries=1)

    assert result is None
    assert "LLM HTTP error" in messages[0]
    assert "{'error': 'bad request'}" in messages[0]


def test_llm_api_request_reports_http_error_text(monkeypatch):
    messages = []

    class Response:
        status_code = 502
        text = "bad gateway"

        def raise_for_status(self):
            raise addon.requests.exceptions.HTTPError("bad")

        def json(self):
            raise ValueError("not json")

    monkeypatch.setattr(addon, "showInfo", messages.append)
    monkeypatch.setattr(addon.requests, "post", lambda *args, **kwargs: Response())

    result = addon.llm_api_request({}, "test-key", "https://api.openai.com/v1", retries=1)

    assert result is None
    assert "bad gateway" in messages[0]


def test_llm_api_request_retries_http_errors(monkeypatch):
    calls = []

    class FailingResponse:
        status_code = 429
        text = "rate limited"

        def raise_for_status(self):
            raise addon.requests.exceptions.HTTPError("rate limited")

        def json(self):
            return {"error": "rate limited"}

    class SuccessResponse:
        def raise_for_status(self):
            return None

    def fake_post(*args, **kwargs):
        calls.append("call")
        return FailingResponse() if len(calls) == 1 else SuccessResponse()

    monkeypatch.setattr(addon.requests, "post", fake_post)
    monkeypatch.setattr(addon.time, "sleep", lambda seconds: None)

    assert isinstance(addon.llm_api_request({}, "test-key", "https://api.openai.com/v1", retries=2), SuccessResponse)
    assert len(calls) == 2


def test_llm_api_request_reports_request_exception(monkeypatch):
    messages = []

    def fake_post(*args, **kwargs):
        raise addon.requests.exceptions.Timeout("timeout")

    monkeypatch.setattr(addon, "showInfo", messages.append)
    monkeypatch.setattr(addon.requests, "post", fake_post)

    result = addon.llm_api_request({}, "test-key", "https://api.openai.com/v1", retries=1)

    assert result is None
    assert "LLM request error" in messages[0]


def test_llm_api_request_retries_request_exception(monkeypatch):
    calls = []

    class Response:
        def raise_for_status(self):
            return None

    def fake_post(*args, **kwargs):
        calls.append("call")
        if len(calls) == 1:
            raise addon.requests.exceptions.Timeout("timeout")
        return Response()

    monkeypatch.setattr(addon.requests, "post", fake_post)
    monkeypatch.setattr(addon.time, "sleep", lambda seconds: None)

    assert isinstance(addon.llm_api_request({}, "test-key", "https://api.openai.com/v1", retries=2), Response)
    assert len(calls) == 2


def test_generate_vocab_note_handles_no_response_and_bad_shape(monkeypatch):
    messages = []
    monkeypatch.setitem(addon.config, "provider", "openai")
    monkeypatch.setitem(addon.config, "model", "custom-model")
    monkeypatch.setitem(addon.config, "openai_api_key", "test-key")
    monkeypatch.setattr(addon, "showInfo", messages.append)
    monkeypatch.setattr(addon, "llm_api_request", lambda *args, **kwargs: None)

    assert addon.generate_vocab_note("apple") is None

    class BadResponse:
        def json(self):
            return {"unexpected": []}

    monkeypatch.setattr(addon, "llm_api_request", lambda *args, **kwargs: BadResponse())

    assert addon.generate_vocab_note("apple") is None
    assert "unexpected response shape" in messages[0]


def test_generate_speech_skips_when_openai_key_missing(monkeypatch):
    monkeypatch.setitem(addon.config, "speech_provider", "openai")
    monkeypatch.setitem(addon.config, "speech_api_key", "your-speech-key")
    monkeypatch.setitem(addon.config, "openai_api_key", "your-openai-key")

    assert addon.generate_speech("近い") is None


def test_generate_speech_writes_media_file(monkeypatch, tmp_path):
    added_files = []
    monkeypatch.setitem(addon.config, "speech_provider", "openai")
    monkeypatch.setitem(addon.config, "speech_api_key", "your-speech-key")
    monkeypatch.setitem(addon.config, "openai_api_key", "test-key")
    monkeypatch.setitem(addon.config, "speech_voice", "nova")
    monkeypatch.setitem(addon.config, "speech_model", "gpt-4o-mini-tts")
    monkeypatch.setitem(addon.config, "speech_response_format", "mp3")
    monkeypatch.setattr(addon, "__file__", str(tmp_path / "__init__.py"))
    monkeypatch.setattr(addon, "mw", SimpleNamespace(col=SimpleNamespace(media=SimpleNamespace(addFile=added_files.append))))

    class Response:
        content = b"mp3"

        def raise_for_status(self):
            return None

    captured = {}

    def fake_post(url, headers, json, timeout):
        captured.update({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return Response()

    monkeypatch.setattr(addon.requests, "post", fake_post)

    result = addon.generate_speech("近い", retries=1)

    assert result is None
    assert added_files and added_files[0].name.endswith(".mp3")
    assert captured["json"]["input"] == "近い"
    assert "Japanese pronunciation" in captured["json"]["instructions"]


def test_generate_speech_reports_failure(monkeypatch, tmp_path):
    messages = []
    monkeypatch.setitem(addon.config, "speech_provider", "openai")
    monkeypatch.setitem(addon.config, "speech_api_key", "your-speech-key")
    monkeypatch.setitem(addon.config, "openai_api_key", "test-key")
    monkeypatch.setattr(addon, "__file__", str(tmp_path / "__init__.py"))
    monkeypatch.setattr(addon, "showInfo", messages.append)

    def fake_post(*args, **kwargs):
        raise addon.requests.exceptions.ConnectionError("offline")

    monkeypatch.setattr(addon.requests, "post", fake_post)

    assert addon.generate_speech("apple", retries=1) is None
    assert "Speech Error" in messages[0]


def test_generate_speech_retries_before_success(monkeypatch, tmp_path):
    added_files = []
    calls = []
    monkeypatch.setitem(addon.config, "speech_provider", "openai")
    monkeypatch.setitem(addon.config, "speech_api_key", "your-speech-key")
    monkeypatch.setitem(addon.config, "openai_api_key", "test-key")
    monkeypatch.setattr(addon, "__file__", str(tmp_path / "__init__.py"))
    monkeypatch.setattr(addon, "mw", SimpleNamespace(col=SimpleNamespace(media=SimpleNamespace(addFile=lambda path: added_files.append(path.name) or "audio.mp3"))))
    monkeypatch.setattr(addon.time, "sleep", lambda seconds: None)

    class Response:
        content = b"mp3"

        def raise_for_status(self):
            return None

    def fake_post(*args, **kwargs):
        calls.append("call")
        if len(calls) == 1:
            raise addon.requests.exceptions.ConnectionError("offline")
        return Response()

    monkeypatch.setattr(addon.requests, "post", fake_post)

    assert addon.generate_speech("apple", retries=2) == "audio.mp3"
    assert len(calls) == 2
    assert added_files[0].endswith(".mp3")


def test_generate_speech_uses_custom_kokoro_tts(monkeypatch, tmp_path):
    added_files = []
    monkeypatch.setitem(addon.config, "speech_provider", "custom")
    monkeypatch.setitem(addon.config, "speech_api_key", "speaches-key")
    monkeypatch.setitem(addon.config, "speech_base_url", "http://your-tts-server:8001/v1")
    monkeypatch.setitem(addon.config, "speech_voice", "af_bella")
    monkeypatch.setitem(addon.config, "speech_model", "csukuangfj/kokoro-en-v0_19")
    monkeypatch.setitem(addon.config, "speech_response_format", "wav")
    monkeypatch.setitem(addon.config, "speech_sample_rate", 24000)
    monkeypatch.setattr(addon, "__file__", str(tmp_path / "__init__.py"))
    monkeypatch.setattr(addon, "mw", SimpleNamespace(col=SimpleNamespace(media=SimpleNamespace(addFile=lambda path: added_files.append(path.name) or "kokoro.wav"))))

    class Response:
        content = b"wav"

        def raise_for_status(self):
            return None

    captured = {}

    def fake_post(url, headers, json, timeout):
        captured.update({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return Response()

    monkeypatch.setattr(addon.requests, "post", fake_post)

    assert addon.generate_speech("apple", retries=1) == "kokoro.wav"
    assert added_files[0].endswith(".wav")
    assert captured["url"] == "http://your-tts-server:8001/v1/audio/speech"
    assert captured["headers"]["Authorization"] == "Bearer speaches-key"
    assert captured["json"] == {
        "model": "speaches-ai/Kokoro-82M-v1.0-ONNX",
        "voice": "af_bella",
        "input": "apple",
        "response_format": "wav",
        "sample_rate": 24000,
    }


def test_custom_speech_random_voice_uses_american_kokoro_list(monkeypatch):
    monkeypatch.setitem(addon.config, "speech_provider", "custom")
    monkeypatch.setitem(addon.config, "speech_api_key", "speaches-key")
    monkeypatch.setitem(addon.config, "speech_voice", "")
    monkeypatch.setattr(addon.random, "choice", lambda choices: choices[-1])

    provider, api_key, url, model, voice, response_format = addon.speech_settings()

    assert provider == "custom"
    assert api_key == "speaches-key"
    assert voice == "am_michael"
    assert voice in addon.KOKORO_RANDOM_AMERICAN_VOICES
    assert model == "speaches-ai/Kokoro-82M-v1.0-ONNX"
    assert response_format == "wav"


def test_custom_speech_japanese_uses_multilingual_model_and_japanese_voice(monkeypatch):
    monkeypatch.setitem(addon.config, "speech_provider", "custom")
    monkeypatch.setitem(addon.config, "speech_api_key", "speaches-key")
    monkeypatch.setitem(addon.config, "speech_model", "csukuangfj/kokoro-en-v0_19")
    monkeypatch.setitem(addon.config, "speech_voice", "")
    monkeypatch.setattr(addon.random, "choice", lambda choices: choices[0])

    provider, api_key, url, model, voice, response_format = addon.speech_settings("近い")

    assert provider == "custom"
    assert model == "speaches-ai/Kokoro-82M-v1.0-ONNX"
    assert voice == "jf_alpha"
    assert voice in addon.KOKORO_JAPANESE_VOICES
    assert response_format == "wav"


def test_on_add_note_populates_english_and_loads(monkeypatch):
    editor = DummyEditor("apple")
    payload = {
        "word": "apple",
        "meanings": {"english": "fruit", "traditionalChinese": "蘋果"},
        "definitions": [{"text": "a fruit"}],
        "pronunciation": "ap-ul",
        "soundLink": "https://forvo.com/word/apple/#en",
        "etymology": "Old English",
        "synonyms": ["fruit"],
        "antonyms": ["vegetable"],
        "realWorldExamples": ["apple pie"],
    }
    monkeypatch.setattr(addon, "generate_vocab_note", lambda word: json.dumps(payload))
    monkeypatch.setattr(addon, "generate_speech", lambda word: None)

    addon.on_add_note(editor)

    assert editor.loaded is True
    assert editor.note["vocabulary"] == "<h2>apple</h2>"
    assert "Old English" in editor.note["Etymology, Synonyms and Antonyms"]


def test_on_add_note_populates_japanese_and_loads(monkeypatch):
    editor = DummyEditor("近い")
    payload = {
        "vocabulary": "近い",
        "kanji": "近い",
        "furigana": "ちかい",
        "pitchPattern": "2",
        "pronunciations": "chikai",
        "explanations": {"en-US": "near", "zh-TW": "近的"},
        "partsOfSpeech": "i-adjective",
        "grammaticalRules": {"adjectives": {"NegativeForm": "近くない"}},
        "sound": "https://forvo.com/word/近い/#ja",
        "exampleSentences": [{"sentence": "駅に近いです。", "translation": "離車站很近。"}],
    }
    monkeypatch.setattr(addon, "generate_vocab_note", lambda word: json.dumps(payload))
    monkeypatch.setattr(addon, "generate_speech", lambda word: None)

    addon.on_add_note(editor)

    assert editor.loaded is True
    assert editor.note["vocabulary"] == "<h2>近い</h2>"
    assert "近くない" in editor.note["Etymology, Synonyms and Antonyms"]


def test_japanese_note_uses_furigana_for_speech(monkeypatch):
    spoken = []
    editor = DummyEditor("禁煙")
    note_data = {
        "vocabulary": "禁煙",
        "kanji": "禁煙",
        "furigana": "きんえん",
        "explanations": {"zh-TW": "禁止吸菸"},
    }
    monkeypatch.setattr(addon, "generate_speech", lambda text: spoken.append(text) or "kinen.wav")

    addon.populate_japanese_note(editor, note_data)

    assert spoken == ["きんえん"]
    assert "[sound:kinen.wav]" in editor.note["Sound"]


def test_format_rule_group_renders_unlisted_keys():
    html = addon.format_rule_group("custom", {"Known": "yes", "Extra": "also"}, ["Known"])

    assert "Known: yes" in html
    assert "Extra: also" in html


def test_on_add_note_handles_empty_word(monkeypatch):
    messages = []
    editor = DummyEditor("")
    monkeypatch.setattr(addon, "showInfo", messages.append)

    addon.on_add_note(editor)

    assert editor.loaded is False
    assert "No vocabulary word entered" in messages[0]


def test_on_add_note_reports_population_error(monkeypatch):
    messages = []
    editor = DummyEditor("apple")
    monkeypatch.setattr(addon, "generate_vocab_note", lambda word: json.dumps({"word": "apple"}))
    monkeypatch.setattr(addon, "populate_english_note", lambda editor, note_data: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(addon, "showInfo", messages.append)

    addon.on_add_note(editor)

    assert editor.loaded is False
    assert messages == ["Error on add note: boom"]


def test_add_note_to_deck_requires_anki_runtime():
    try:
        addon.add_note_to_deck("Default", "tag", {})
    except RuntimeError as error:
        assert "Anki is required" in str(error)
    else:
        raise AssertionError("add_note_to_deck should require Anki outside Anki runtime")


def test_prompt_contracts_discourage_invalid_json():
    for prompt in [prompts.VOC_PROMPT, prompts.JPY_PROMPT]:
        assert "Return exactly one valid JSON object" in prompt
        assert "Do not wrap it in Markdown" in prompt
        assert "trailing commas" in prompt
        assert "```" not in prompt
        assert "\n//" not in prompt
        assert "..." not in prompt

    assert '"translation"' in prompts.JPY_PROMPT
    assert "translation in zh-tw" not in prompts.JPY_PROMPT


def test_config_migration_recovers_from_removed_provider_and_fields():
    migrated = addon.migrate_config(
        {
            "provider": "legacy_provider",
            "legacy_provider_api_key": "secret",
            "model": None,
            "max_tokens": "not-int",
            "temperature": "bad",
            "speech_provider": "bad-provider",
            "speech_sample_rate": "bad",
            "speech_speed": "bad",
            "generation_mode": "unknown",
        }
    )

    assert migrated["provider"] == "openai"
    assert "legacy_provider_api_key" not in migrated
    assert migrated["model"] == ""
    assert migrated["max_tokens"] == addon.CONFIG_DEFAULTS["max_tokens"]
    assert migrated["temperature"] == addon.CONFIG_DEFAULTS["temperature"]
    assert migrated["speech_provider"] == "openai"
    assert migrated["speech_sample_rate"] == addon.CONFIG_DEFAULTS["speech_sample_rate"]
    assert migrated["speech_speed"] == addon.CONFIG_DEFAULTS["speech_speed"]
    assert migrated["generation_mode"] == "standard"


def test_config_for_storage_keeps_only_supported_keys():
    stored = addon.config_for_storage({"provider": "openrouter", "legacy_provider_api_key": "secret", "extra": "ignored"})

    assert stored["provider"] == "openrouter"
    assert "legacy_provider_api_key" not in stored
    assert "extra" not in stored
    assert set(stored) == set(addon.CONFIG_DEFAULTS)


def test_prompt_for_vocab_applies_generation_mode(monkeypatch):
    monkeypatch.setitem(addon.config, "generation_mode", "concise")

    english_prompt = addon.prompt_for_vocab("apple")

    assert "Generation mode: Concise" in english_prompt
    assert "Return at most 2 definitions" in english_prompt

    monkeypatch.setitem(addon.config, "generation_mode", "japanese")

    japanese_prompt = addon.prompt_for_vocab("apple")

    assert "You are a Japanese dictionary engine" in japanese_prompt
    assert "Generation mode: Japanese" in japanese_prompt


def test_run_api_health_check_validates_parsed_json(monkeypatch):
    def fake_health_check(*args, **kwargs):
        return llm.HealthCheckResult(True, json.dumps({"word": "apple"}))

    monkeypatch.setattr(addon, "provider_health_check", fake_health_check)

    result = addon.run_api_health_check("apple")

    assert result.ok is True
    assert "succeeded" in result.message


def test_run_api_health_check_rejects_invalid_json(monkeypatch):
    messages = []

    def fake_health_check(*args, **kwargs):
        return llm.HealthCheckResult(True, "not json")

    monkeypatch.setattr(addon, "provider_health_check", fake_health_check)
    monkeypatch.setattr(addon, "showInfo", messages.append)

    result = addon.run_api_health_check("apple")

    assert result.ok is False
    assert "not valid note JSON" in result.message
    assert messages and messages[0].startswith("Failed to parse note data")


def test_run_japanese_json_health_check_normalizes_translation(monkeypatch):
    payload = {
        "vocabulary": "近い",
        "exampleSentences": [
            {"sentence": "駅に近いです。", "reading": "えきにちかいです。", "translation in zh-tw": "離車站很近。"}
        ],
    }

    def fake_health_check(*args, **kwargs):
        return llm.HealthCheckResult(True, json.dumps(payload))

    monkeypatch.setattr(addon, "provider_health_check", fake_health_check)

    result = addon.run_japanese_json_health_check()

    assert result.ok is True
    assert "succeeded" in result.message


def test_japanese_note_normalizes_example_sentence_reading():
    normalized = addon.normalize_japanese_note_data(
        {
            "vocabulary": "近い",
            "exampleSentences": [
                {"sentence": "駅に近いです。", "pronunciation": "えきにちかいです。", "translation": "離車站很近。"}
            ],
        }
    )

    assert normalized["exampleSentences"][0]["reading"] == "えきにちかいです。"


def test_redact_payload_removes_secret_values():
    payload = llm.redact_payload(
        {
            "Authorization": "Bearer secret",
            "nested": {"openai_api_key": "sk-test"},
            "safe": "value",
        }
    )

    assert payload["Authorization"] == "[redacted]"
    assert payload["nested"]["openai_api_key"] == "[redacted]"
    assert payload["safe"] == "value"
