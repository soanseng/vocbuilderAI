import importlib.util
import json
import sys
from pathlib import Path


def load_addon():
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    spec = importlib.util.spec_from_file_location("vocbuilderai_addon", root / "__init__.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


addon = load_addon()


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
    assert "response_format" not in captured["payload"]
