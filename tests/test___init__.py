import importlib.util
import json
import pathlib
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
    addon.SPEECH_CACHE.clear()


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
    monkeypatch.setattr(addon, "generate_vocab_note", lambda word, notify=None: None)
    editor = DummyEditor("近い")
    monkeypatch.setattr(addon, "showInfo", messages.append)

    addon.on_add_note(editor)

    assert editor.loaded is False
    # The request layer already reported the real error; no duplicate dialog.
    assert messages == []


def test_openrouter_generation_omits_response_format(monkeypatch):
    captured = {}

    class Response:
        def json(self):
            return {"choices": [{"message": {"content": json.dumps({"vocabulary": "近い"})}}]}

    def fake_request(payload, api_key, base_url, retries=3, provider="openai", notify=None):
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
    assert captured["payload"]["max_tokens"] == 4096
    assert "max_completion_tokens" not in captured["payload"]
    assert "response_format" not in captured["payload"]


def test_openai_generation_includes_json_response_format(monkeypatch):
    captured = {}

    class Response:
        def json(self):
            return {"choices": [{"message": {"content": json.dumps({"word": "apple"})}}]}

    def fake_request(payload, api_key, base_url, retries=3, provider="openai", notify=None):
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
    assert captured["payload"]["max_completion_tokens"] == 4096
    assert "max_tokens" not in captured["payload"]
    assert captured["payload"]["response_format"] == {"type": "json_object"}


def test_custom_generation_uses_configured_litellm_endpoint(monkeypatch):
    captured = {}

    class Response:
        def json(self):
            return {"choices": [{"message": {"content": json.dumps({"word": "apple"})}}]}

    def fake_request(payload, api_key, base_url, retries=3, provider="openai", notify=None):
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
    assert captured["payload"]["max_tokens"] == 4096
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

def test_process_response_repairs_latex_escapes_in_math_json():
    response = (
        "{\"front\": \"How does the second derivative determine concavity?\", "
        "\"explanation\": \"二階導數 \\( f''(x) \\) 描述了函數圖形的「彎曲方向」。\", "
        "\"calculation\": \"考慮 \\( f(x) = x^2 \\\\)\\n\\[ f'(x) = 2x \\\\]\\n\\[ f''(x) = 2 \\\\]\", "
        "\"example\": \"\", \"notes\": \"\"}"
    )

    note_data = addon.process_response(response)

    assert note_data["explanation"] == "二階導數 \\( f''(x) \\) 描述了函數圖形的「彎曲方向」。"
    assert note_data["calculation"] == "考慮 \\( f(x) = x^2 \\)\n\\[ f'(x) = 2x \\]\n\\[ f''(x) = 2 \\]"


def test_process_response_repairs_missing_comma_between_members():
    response = (
        "{\n"
        '  "word": "punctilio",\n'
        '  "meanings": {\n'
        '    "english": "A minor point of etiquette, formality, or propriety.",\n'
        '    "traditionalChinese": "禮儀細節；繁文縟節。"\n'
        "  },\n"
        '  "definitions": [\n'
        "    {\n"
        '      "text": "A small point of behavior.",\n'
        '      "grammaticalInfo": {\n'
        '        "partOfSpeech": "noun"\n'
        "      }\n"
        "    }\n"
        "  ]\n"
        '  "pronunciation": "pungk-TIL-ee-oh",\n'
        '  "etymology": "From Italian puntiglio."\n'
        "}"
    )

    note_data = addon.process_response(response)

    assert note_data["word"] == "punctilio"
    assert note_data["meanings"]["traditionalChinese"] == "禮儀細節；繁文縟節。"
    assert note_data["pronunciation"] == "pungk-TIL-ee-oh"
    assert note_data["etymology"] == "From Italian puntiglio."


def test_process_response_repairs_truncated_json():
    response = '{"word": "punctilio", "meanings": {"english": "A minor point of etiquette'

    note_data = addon.process_response(response)

    assert note_data == {"word": "punctilio", "meanings": {"english": "A minor point of etiquette"}}


def test_process_response_repairs_truncated_dangling_key():
    response = '{"word": "apple", "meanings"'

    assert addon.process_response(response) == {"word": "apple"}


def test_process_response_repairs_trailing_commas():
    response = '{"word": "apple", "synonyms": ["keen", "sharp",],}'

    assert addon.process_response(response) == {"word": "apple", "synonyms": ["keen", "sharp"]}


def test_process_response_repairs_literal_newline_inside_string():
    response = '{\n  "word": "apple",\n  "etymology": "from Old English\nappel"\n}'

    note_data = addon.process_response(response)

    assert note_data["etymology"] == "from Old English\nappel"


def test_process_response_repairs_other_control_characters_inside_string():
    response = (
        "{\n"
        '  "sentence": "ようやく",\n'
        '  "grammarPoints": [\n'
        "    {\n"
        '      "notes": "1. 帶有「不容易才做到」的語氣。\\n2. 常與「〜した」等表示結果的詞搭配。'
        "\x0b3. 同義詞：ついに（終於）。\"\n"
        "    }\n"
        "  ]\n"
        "}"
    )

    note_data = addon.process_response(response)

    assert note_data["grammarPoints"][0]["notes"] == (
        "1. 帶有「不容易才做到」的語氣。\n2. 常與「〜した」等表示結果的詞搭配。\x0b3. 同義詞：ついに（終於）。"
    )


def test_process_response_still_rejects_prose_without_json(monkeypatch):
    messages = []
    monkeypatch.setattr(addon, "showInfo", messages.append)

    assert addon.process_response("Sure! Here is your note: it is a great word.") == {}
    assert messages[0].startswith("Failed to parse note data:")


def test_process_response_repairs_missing_comma_between_nested_containers():
    response = '{"word": "apple", "meanings": {"english": "fruit"} "definitions": []}'

    assert addon.process_response(response) == {"word": "apple", "meanings": {"english": "fruit"}, "definitions": []}


def test_process_response_repairs_missing_comma_between_array_objects():
    response = (
        '{"word": "apple", "definitions": ['
        '{"text": "fruit"} {"text": "tree"}'
        "]}"
    )

    note_data = addon.process_response(response)

    assert note_data["definitions"] == [{"text": "fruit"}, {"text": "tree"}]


def test_process_response_repairs_number_split_after_missing_comma():
    response = '{"word": "apple", "counts": [1 200]}'

    assert addon.process_response(response) == {"word": "apple", "counts": [1, 200]}


def test_parse_failure_message_shows_error_context(monkeypatch):
    messages = []
    monkeypatch.setattr(addon, "showInfo", messages.append)
    response = '{"a": 1, "b": "x" garbage}'

    assert addon.process_response(response) == {}
    assert "Context:" in messages[0]
    assert "garbage" in messages[0]


def test_chat_truncated_detects_length_finish_reason():
    class Response:
        def json(self):
            return {"choices": [{"message": {"content": "hi"}, "finish_reason": "length"}]}

    class CompleteResponse:
        def json(self):
            return {"choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}]}

    class BrokenResponse:
        def json(self):
            raise ValueError("not json")

    assert addon.chat_truncated(Response()) is True
    assert addon.chat_truncated(CompleteResponse()) is False
    assert addon.chat_truncated(BrokenResponse()) is False


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


def test_generate_speech_uses_qwen_litellm_tts(monkeypatch, tmp_path):
    added_files = []
    monkeypatch.setitem(addon.config, "speech_provider", "qwen")
    monkeypatch.setitem(addon.config, "speech_api_key", "stale-speaches-key")
    monkeypatch.setitem(addon.config, "custom_api_key", "litellm-key")
    monkeypatch.setitem(addon.config, "custom_base_url", "http://your-litellm-server:4000/v1")
    monkeypatch.setitem(addon.config, "speech_voice", "Vivian")
    monkeypatch.setitem(addon.config, "speech_model", "gpt-4o-mini-tts")
    monkeypatch.setitem(addon.config, "speech_speed", 1.25)
    monkeypatch.setattr(addon, "__file__", str(tmp_path / "__init__.py"))
    monkeypatch.setattr(addon, "mw", SimpleNamespace(col=SimpleNamespace(media=SimpleNamespace(addFile=lambda path: added_files.append(path.name) or "qwen.wav"))))

    class Response:
        content = b"wav"

        def raise_for_status(self):
            return None

    captured = {}

    def fake_post(url, headers, json, timeout):
        captured.update({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return Response()

    monkeypatch.setattr(addon.requests, "post", fake_post)

    assert addon.generate_speech("apple", retries=1) == "qwen.wav"
    assert added_files[0].endswith(".wav")
    assert captured["url"] == "http://your-litellm-server:4000/v1/audio/speech"
    # The stale speech_api_key must be ignored; qwen rides the chat LiteLLM key.
    assert captured["headers"]["Authorization"] == "Bearer litellm-key"
    assert captured["json"] == {
        "model": "qwen-tts",
        "voice": "Vivian",
        "input": "apple",
        "response_format": "wav",
        "speed": 1.25,
    }


def test_qwen_speech_random_voice_from_qwen_list(monkeypatch):
    monkeypatch.setitem(addon.config, "speech_provider", "qwen")
    monkeypatch.setitem(addon.config, "custom_api_key", "litellm-key")
    monkeypatch.setitem(addon.config, "speech_voice", "")
    monkeypatch.setattr(addon.random, "choice", lambda choices: choices[0])

    provider, api_key, url, model, voice, response_format = addon.speech_settings()

    assert provider == "qwen"
    assert api_key == "litellm-key"
    assert voice == "Vivian"
    assert voice in addon.QWEN_TTS_VOICES
    assert model == "qwen-tts"
    assert response_format == "wav"
    assert url.endswith("/audio/speech")


def test_qwen_speech_falls_back_to_custom_base_default(monkeypatch):
    monkeypatch.setitem(addon.config, "speech_provider", "qwen")
    monkeypatch.setitem(addon.config, "custom_api_key", "litellm-key")
    monkeypatch.setitem(addon.config, "custom_base_url", "")
    monkeypatch.setitem(addon.config, "speech_voice", "Serena")
    monkeypatch.setitem(addon.config, "speech_model", "speaches-ai/Kokoro-82M-v1.0-ONNX")

    _provider, _api_key, url, model, voice, _fmt = addon.speech_settings("近い")

    assert url == addon.CONFIG_DEFAULTS["custom_base_url"].rstrip("/") + "/audio/speech"
    assert model == "qwen-tts"
    assert voice == "Serena"


def test_migrate_config_keeps_qwen_speech_provider():
    migrated = addon.migrate_config({"speech_provider": "qwen"})

    assert migrated["speech_provider"] == "qwen"

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
    }
    monkeypatch.setattr(addon, "generate_vocab_note", lambda word, notify=None: json.dumps(payload))
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
    }
    monkeypatch.setattr(addon, "generate_vocab_note", lambda word, notify=None: json.dumps(payload))
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
    monkeypatch.setattr(addon, "generate_vocab_note", lambda word, notify=None: json.dumps({"word": "apple"}))
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
    assert migrated["speech_provider"] == addon.CONFIG_DEFAULTS["speech_provider"]
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

    japanese_prompt = addon.prompt_for_vocab("近い")

    assert "You are a Japanese dictionary engine" in japanese_prompt
    assert "Generation mode: Japanese" in japanese_prompt

    # English words must not get the Japanese schema; it produces empty cards.
    english_prompt = addon.prompt_for_vocab("apple")

    assert "You are a bilingual dictionary engine" in english_prompt
    assert "Generation mode: Standard" in english_prompt


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


README_STYLE_FIELDS = {
    "vocabulary": "Vocabulary",
    "detail definition": "Detail definition",
    "Pronunciations": "Pronunciations",
    "Sound": "Sound",
    "Etymology, Synonyms and Antonyms": "Etymology, Synonyms, and Antonyms",
    "Real-world examples": "Real-world examples",
}


def test_format_examples_bolds_whole_words_only():
    html = addon.format_examples_html("at", ["The cat sat at the mat"])

    assert html.count("<strong>") == 1
    assert "<strong>at</strong> the mat" in html
    assert "c<strong>at</strong>" not in html


def test_html_text_escapes_and_falls_back_on_blank():
    assert addon.html_text("", "N/A") == "N/A"
    assert addon.html_text("   ", "N/A") == "N/A"
    assert addon.html_text("<b>&</b>") == "&lt;b&gt;&amp;&lt;/b&gt;"


def test_clean_vocab_input_strips_editor_html():
    assert addon.clean_vocab_input("<div>apple</div>") == "apple"
    assert addon.clean_vocab_input("a &amp; b&nbsp;") == "a & b"
    assert addon.clean_vocab_input("") == ""


def test_resolve_note_fields_matches_readme_field_names():
    note = DummyNote(["apple"])
    for actual in README_STYLE_FIELDS.values():
        note[actual] = ""

    mapping = addon.resolve_note_fields(note)

    assert mapping["vocabulary"] == "Vocabulary"
    assert mapping["Etymology, Synonyms and Antonyms"] == "Etymology, Synonyms, and Antonyms"


def test_populate_english_note_writes_readme_style_field_names(monkeypatch):
    monkeypatch.setattr(addon, "generate_speech", lambda word: None)
    editor = DummyEditor("apple")
    for actual in README_STYLE_FIELDS.values():
        editor.note[actual] = ""

    addon.populate_english_note(editor, {"word": "apple"})

    assert editor.note["Vocabulary"] == "<h2>apple</h2>"
    assert editor.note["Sound"].startswith("<h3>Sound:</h3>")
    assert "vocabulary" not in editor.note


def test_on_add_note_reports_missing_note_fields_before_any_api_call(monkeypatch):
    messages = []
    editor = DummyEditor("apple")
    editor.note["Vocabulary"] = ""  # incomplete note type

    def fail(*args, **kwargs):
        raise AssertionError("LLM must not be called when fields are missing")

    monkeypatch.setattr(addon, "generate_vocab_note", fail)
    monkeypatch.setattr(addon, "showInfo", messages.append)

    addon.on_add_note(editor)

    assert any("missing fields" in message for message in messages)
    assert editor.loaded is False


def test_llm_api_request_does_not_retry_client_errors(monkeypatch):
    calls = []

    class Response:
        status_code = 401
        text = "unauthorized"

        def raise_for_status(self):
            raise addon.requests.exceptions.HTTPError("unauthorized")

        def json(self):
            return {"error": "invalid api key"}

    def fake_post(*args, **kwargs):
        calls.append(1)
        return Response()

    messages = []
    monkeypatch.setattr(addon.requests, "post", fake_post)
    monkeypatch.setattr(addon, "showInfo", messages.append)

    assert addon.llm_api_request({}, "bad-key", "https://api.openai.com/v1", retries=3) is None

    assert len(calls) == 1
    assert "LLM HTTP error" in messages[0]


def test_custom_speech_respects_configured_full_list_voice(monkeypatch):
    monkeypatch.setitem(addon.config, "speech_provider", "custom")
    monkeypatch.setitem(addon.config, "speech_api_key", "speaches-key")
    monkeypatch.setitem(addon.config, "speech_voice", "af_heart")

    _provider, _api_key, _url, _model, voice, _fmt = addon.speech_settings("apple")

    assert voice == "af_heart"
    assert voice in addon.KOKORO_AMERICAN_VOICES


def test_generate_speech_reuses_prewarmed_audio(monkeypatch, tmp_path):
    calls = []
    added_files = []
    monkeypatch.setitem(addon.config, "speech_provider", "openai")
    monkeypatch.setitem(addon.config, "speech_api_key", "your-speech-key")
    monkeypatch.setitem(addon.config, "openai_api_key", "test-key")
    monkeypatch.setattr(addon, "__file__", str(tmp_path / "__init__.py"))
    monkeypatch.setattr(
        addon,
        "mw",
        SimpleNamespace(col=SimpleNamespace(media=SimpleNamespace(addFile=lambda path: added_files.append(path.name) or "audio.mp3"))),
    )

    class Response:
        content = b"mp3"

        def raise_for_status(self):
            return None

    def fake_post(*args, **kwargs):
        calls.append(1)
        return Response()

    monkeypatch.setattr(addon.requests, "post", fake_post)

    assert addon.prewarm_speech("apple") is not None
    assert addon.generate_speech("apple") == "audio.mp3"

    assert len(calls) == 1  # TTS fetched once; generate_speech reused the cache
    assert added_files and added_files[0].endswith(".mp3")


def test_japanese_grammar_prompt_contract():
    assert "Return exactly one valid JSON object" in prompts.JPG_PROMPT
    assert '"grammarPoints"' in prompts.JPG_PROMPT
    assert '"reading"' in prompts.JPG_PROMPT and '"translation"' in prompts.JPG_PROMPT
    assert "Traditional Chinese" in prompts.JPG_PROMPT

    styled = addon.with_generation_mode(prompts.JPG_PROMPT, "concise")
    assert "Generation mode: Concise" in styled


def test_normalize_japanese_grammar_data_maps_variants():
    normalized = addon.normalize_japanese_grammar_data(
        {
            "sentence": "行かなければならない。",
            "translationInZhTw": "必須去。",
            "grammarPoints": [
                {
                    "fragment": "なければならない",
                    "name": "〜なければならない",
                    "explanation": "表示義務",
                    "formation": "動詞ない形 + なければならない",
                    "note": "口語可用「なきゃ」",
                },
                "を",
            ],
            "relatedGrammar": ["〜なきゃ", 42],
            "exampleSentences": [
                {"sentence": "宿題をしなきゃ。", "furigana": "しゅくだいをしなきゃ。", "translation": "必須寫作業。"}
            ],
        }
    )

    assert normalized["sentence"] == "行かなければならない。"
    assert normalized["translation"] == "必須去。"
    first_point = normalized["grammarPoints"][0]
    assert first_point == {
        "expression": "なければならない",
        "grammarName": "〜なければならない",
        "meaning": "表示義務",
        "structure": "動詞ない形 + なければならない",
        "notes": "口語可用「なきゃ」",
    }
    assert normalized["grammarPoints"][1] == {
        "expression": "を",
        "grammarName": "",
        "meaning": "",
        "structure": "",
        "notes": "",
    }
    assert normalized["relatedGrammar"] == ["〜なきゃ"]
    example = normalized["exampleSentences"][0]
    assert example["sentence"] == "宿題をしなきゃ。"
    assert example["reading"] == "しゅくだいをしなきゃ。"
    assert example["translation"] == "必須寫作業。"


def test_format_grammar_points_renders_escapes_and_variants():
    html = addon.format_grammarPoints_html(
        [
            {
                "expression": "て<span>も</span>",
                "grammarName": "〜てもいい",
                "meaning": "可以(許可)",
                "structure": "動詞て形 + もいい",
                "notes": "口語常講「てもいい?」",
            },
            "plain fragment",
        ]
    )

    assert "<strong>〜てもいい</strong>" in html
    assert "&lt;span&gt;" in html
    assert "Structure: 動詞て形 + もいい" in html
    assert "Meaning: 可以(許可)" in html
    assert "Notes: 口語常講「てもいい?」" in html
    assert "<strong>plain fragment</strong>" in html


def test_format_grammar_points_and_related_handle_empty():
    assert "No grammar points found." in addon.format_grammarPoints_html(None)
    assert addon.format_relatedGrammar_html(None) == ""
    related = addon.format_relatedGrammar_html(["〜ば", "〜ほど"])
    assert "<li>〜ば</li>" in related and "<li>〜ほど</li>" in related


def test_populate_japanese_grammar_note_writes_all_fields(monkeypatch):
    monkeypatch.setattr(addon, "generate_speech", lambda text: "bunpo.wav")
    editor = DummyEditor("毎日単語を覚えなければならない。")
    note_data = {
        "sentence": "毎日単語を覚えなければならない。",
        "reading": "まいにちたんごをおぼえなければならない。",
        "translation": "每天必須背單字。",
        "grammarPoints": [
            {
                "expression": "なければならない",
                "grammarName": "〜なければならない",
                "meaning": "必須、非得不可",
                "structure": "動詞ない形 + なければならない",
                "notes": "正式的義務表達",
            }
        ],
        "relatedGrammar": ["〜なきゃ", "〜なくてはいけない"],
        "exampleSentences": [
            {"sentence": "薬を飲まなければならない。", "reading": "くすりをのまなければならない。", "translation": "必須吃藥。"}
        ],
    }

    addon.populate_japanese_grammar_note(editor, note_data)

    assert "<h2>毎日単語を覚えなければならない。</h2>" in editor.note["vocabulary"]
    assert "まいにちたんごをおぼえなければならない。" in editor.note["Pronunciations"]
    assert "[sound:bunpo.wav]" in editor.note["Sound"]
    assert "每天必須背單字。" in editor.note["detail definition"]
    assert "Grammar Points:" in editor.note["detail definition"]
    assert "〜なければならない" in editor.note["detail definition"]
    assert "〜なきゃ" in editor.note["Etymology, Synonyms and Antonyms"]
    assert "〜なくてはいけない" in editor.note["Etymology, Synonyms and Antonyms"]
    assert "必須吃藥。" in editor.note["Real-world examples"]


def test_generate_grammar_note_uses_japanese_prompt_and_separate_cache(monkeypatch):
    calls = []

    def fake_llm_request(payload, *args, **kwargs):
        calls.append(payload)
        content = '{"sentence": "x", "grammarPoints": []}'
        return SimpleNamespace(json=lambda: {"choices": [{"message": {"content": content}}]})

    monkeypatch.setattr(addon, "llm_api_request", fake_llm_request)

    first = addon.generate_grammar_note("〜てもいい")
    second = addon.generate_grammar_note("〜てもいい")
    addon.generate_vocab_note("〜てもいい")

    assert first == second
    assert len(calls) == 2
    assert "Japanese grammar explanation engine" in calls[0]["messages"][0]["content"]
    assert calls[0]["messages"][1]["content"] == "〜てもいい"


def test_on_add_grammar_note_populates_and_loads(monkeypatch):
    editor = DummyEditor("手伝ってもらえますか。")
    note_data = {
        "sentence": "手伝ってもらえますか。",
        "reading": "てつだってもらえますか。",
        "translation": "能請你幫忙嗎?",
        "grammarPoints": [
            {
                "expression": "てもらえる",
                "grammarName": "〜てもらえる",
                "meaning": "請別人為我做…",
                "structure": "動詞て形 + もらえる",
                "notes": "授受表現",
            }
        ],
        "relatedGrammar": [],
        "exampleSentences": [],
    }
    monkeypatch.setattr(addon, "generate_grammar_note_data", lambda text, notify=None: note_data)
    monkeypatch.setattr(addon, "prewarm_speech", lambda text, notify=None: None)
    monkeypatch.setattr(addon, "generate_speech", lambda text: None)

    addon.on_add_grammar_note(editor)

    assert editor.loaded is True
    assert "Grammar Points:" in editor.note["detail definition"]


def test_on_add_grammar_note_rejects_non_japanese_input(monkeypatch):
    messages = []
    monkeypatch.setattr(addon, "showInfo", messages.append)
    editor = DummyEditor("an apple a day")

    addon.on_add_grammar_note(editor)

    assert messages == ["Grammar explanation expects a Japanese sentence or pattern."]
    assert len(editor.note) == 0


def test_on_add_grammar_note_reports_missing_fields_before_api_call(monkeypatch):
    messages = []
    monkeypatch.setattr(addon, "showInfo", messages.append)

    class IncompleteNote(dict):
        fields = ["行かなければならない。"]

        def keys(self):
            return ["vocabulary"]

    class IncompleteEditor:
        def __init__(self):
            self.note = IncompleteNote()
            self.loaded = False

        def loadNote(self):
            self.loaded = True

    editor = IncompleteEditor()

    addon.on_add_grammar_note(editor)

    assert messages and "missing fields that VocBuilderAI writes" in messages[0]
    assert editor.loaded is False


def test_format_examples_renders_dict_translations_and_keeps_strings():
    html = addon.format_examples_html(
        "apple",
        [
            {"sentence": "I ate an apple.", "translationInZhTw": "我吃了一顆蘋果。"},
            {"sentence": "<b>apple</b> pie", "translation": "&特殊"},
            "Plain apple string.",
        ],
    )

    assert "我吃了一顆蘋果。" in html
    assert "&lt;b&gt;<strong>apple</strong>&lt;/b&gt;" in html
    assert "&amp;特殊" in html
    assert "Plain <strong>apple</strong> string." in html
    assert html.count("<li>") == 3


def test_normalize_english_examples_maps_translations():
    normalized = addon.normalize_english_note_data(
        {
            "realWorldExamples": [
                {"sentence": "I ate an apple.", "translation": "我吃了一顆蘋果。"},
                "Bare apple string.",
            ]
        }
    )
    examples = normalized["realWorldExamples"]
    assert examples[0] == {"sentence": "I ate an apple.", "reading": "", "translation": "我吃了一顆蘋果。"}
    assert examples[1] == {"sentence": "Bare apple string.", "reading": "", "translation": ""}


def test_icon_file_degrades_to_empty_on_filesystem_failure(monkeypatch):
    def raise_oserror(*args, **kwargs):
        raise OSError("TMPDIR is read-only")

    monkeypatch.setattr(pathlib.Path, "mkdir", raise_oserror)
    assert addon._icon_file("probe.svg", "<svg/>") == ""

    monkeypatch.setattr(pathlib.Path, "mkdir", lambda *a, **k: None)
    monkeypatch.setattr(pathlib.Path, "write_text", raise_oserror)
    assert addon._icon_file("probe.svg", "<svg/>") == ""


def test_module_import_survives_icon_write_failure(monkeypatch, tmp_path):
    def raise_oserror(self, *args, **kwargs):
        raise OSError("TMPDIR gone")

    monkeypatch.setattr(pathlib.Path, "mkdir", raise_oserror)

    spec = importlib.util.spec_from_file_location(
        "vbai_import_probe", Path(__file__).resolve().parents[1] / "__init__.py"
    )
    module = importlib.util.module_from_spec(spec)

    spec.loader.exec_module(module)  # must not raise

    assert module.VOCAI_BUTTON_ICON == ""
    assert module.GRAMMAR_BUTTON_ICON == ""


def test_math_prompt_contract():
    assert "Return exactly one valid JSON object" in prompts.MATH_PROMPT
    assert "\\( ... \\)" in prompts.MATH_PROMPT
    assert "\\[ ... \\]" in prompts.MATH_PROMPT
    assert "Traditional Chinese, not Simplified Chinese" in prompts.MATH_PROMPT
    assert '"explanation"' in prompts.MATH_PROMPT
    assert '"calculation"' in prompts.MATH_PROMPT
    assert '"example"' in prompts.MATH_PROMPT
    assert '"notes"' in prompts.MATH_PROMPT


def test_normalize_math_note_data_maps_variants():
    normalized = addon.normalize_math_note_data(
        {"front": "E=mc^2", "derivation": "推導", "note": "備註"}
    )

    assert normalized == {
        "front": "E=mc^2",
        "explanation": "",
        "calculation": "推導",
        "example": "",
        "notes": "備註",
    }


def test_format_math_back_html_keeps_mathjax_and_line_breaks():
    html = addon.format_math_back_html(
        {
            "explanation": "質能等價 \\(E=mc^2\\)",
            "calculation": "令 a=3, b=4\n則 c=5",
            "example": "面積為 2 的正方形。",
            "notes": "僅適用於直角三角形。",
        }
    )

    assert "<h3>Explanation:</h3><p>質能等價 \\(E=mc^2\\)</p>" in html
    assert "<h3>Calculation:</h3><p>令 a=3, b=4<br>則 c=5</p>" in html
    assert "<h3>Example:</h3><p>面積為 2 的正方形。</p>" in html
    assert "<h3>Notes:</h3><p>僅適用於直角三角形。</p>" in html


def test_format_math_back_html_renders_empty_fallbacks():
    html = addon.format_math_back_html({})

    assert html.count("N/A") == 4


def test_resolve_note_fields_matches_basic_note_fields():
    class BasicNote(dict):
        fields = ["\\(x^2\\)"]

        def keys(self):
            return ["Front", "Back"]

    mapping = addon.resolve_note_fields(BasicNote(), required_fields=addon.MATH_CANONICAL_NOTE_FIELDS)

    assert mapping == {"Front": "Front", "Back": "Back"}


def test_generate_math_note_uses_math_prompt_and_separate_cache(monkeypatch):
    captured = []

    def fake_generate(word, system_prompt, retries=3, notify=None, cache_namespace=None):
        captured.append(
            {"word": word, "prompt": system_prompt, "cache_namespace": cache_namespace}
        )
        return "raw response"

    monkeypatch.setattr(addon, "_generate_llm_content", fake_generate)

    assert addon.generate_math_note("Pythagorean theorem") == "raw response"
    assert captured[0]["prompt"] is prompts.MATH_PROMPT
    assert captured[0]["cache_namespace"] == "math"


def test_generate_math_note_data_parses_llm_json(monkeypatch):
    monkeypatch.setattr(
        addon, "generate_math_note", lambda text, notify=None: '{"front": "x^2", "explanation": "平方"}'
    )

    assert addon.generate_math_note_data("x^2") == {"front": "x^2", "explanation": "平方"}


def test_on_add_math_note_populates_back_and_loads(monkeypatch):
    editor = DummyEditor("\\(a^2 + b^2 = c^2\\)")
    note_data = {
        "front": "\\(a^2 + b^2 = c^2\\)",
        "explanation": "畢氏定理說明直角三角形三邊的關係。",
        "calculation": "令 a=3, b=4\n則 c=5",
        "example": "3-4-5 直角三角形。",
        "notes": "僅適用於直角三角形。",
    }
    monkeypatch.setattr(addon, "generate_math_note_data", lambda text, notify=None: note_data)

    addon.on_add_math_note(editor)

    assert editor.loaded is True
    back = editor.note["Back"]
    assert "<h3>Explanation:</h3>" in back
    assert "畢氏定理" in back
    assert "令 a=3, b=4<br>則 c=5" in back


def test_on_add_math_note_handles_empty_input(monkeypatch):
    messages = []
    monkeypatch.setattr(addon, "showInfo", messages.append)
    editor = DummyEditor("   ")

    addon.on_add_math_note(editor)

    assert messages == [
        "No math input entered. Please enter a formula or question in the first field."
    ]
    assert editor.loaded is False


def test_on_add_math_note_reports_missing_fields_before_api_call(monkeypatch):
    messages = []
    monkeypatch.setattr(addon, "showInfo", messages.append)

    class IncompleteNote(dict):
        fields = ["a question"]

        def keys(self):
            return ["Question", "Answer"]

    class IncompleteEditor:
        def __init__(self):
            self.note = IncompleteNote()
            self.loaded = False

        def loadNote(self):
            self.loaded = True

    editor = IncompleteEditor()

    addon.on_add_math_note(editor)

    assert messages and "missing fields that VocBuilderAI writes" in messages[0]
    assert editor.loaded is False
