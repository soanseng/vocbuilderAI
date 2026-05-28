import json
import re


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


def process_response(response: str, notify=None) -> dict:
    notify = notify or (lambda message: None)
    cleaned_response = clean_response(response)
    if not cleaned_response:
        notify("No note data was returned by the LLM.")
        return {}
    try:
        parsed = json.loads(cleaned_response)
    except json.JSONDecodeError as error:
        notify(f"Failed to parse note data: {error}\nContent: {cleaned_response}")
        return {}
    return parsed if isinstance(parsed, dict) else {}


def normalize_english_note_data(note_data):
    note_data = as_dict(note_data)
    return {
        "word": note_data.get("word") or "",
        "meanings": as_dict(note_data.get("meanings")),
        "definitions": as_list(note_data.get("definitions")),
        "pronunciation": note_data.get("pronunciation") or "",
        "soundLink": note_data.get("soundLink") or "",
        "etymology": note_data.get("etymology") or "",
        "synonyms": as_list(note_data.get("synonyms")),
        "antonyms": as_list(note_data.get("antonyms")),
        "realWorldExamples": as_list(note_data.get("realWorldExamples")),
    }


def normalize_japanese_note_data(note_data):
    note_data = as_dict(note_data)
    explanations = as_dict(note_data.get("explanations"))
    example_sentences = []
    for example in as_list(note_data.get("exampleSentences")):
        if isinstance(example, str):
            example_sentences.append({"sentence": example, "reading": "", "translation": ""})
            continue
        example = as_dict(example)
        example_sentences.append(
            {
                "sentence": example.get("sentence", ""),
                "reading": (
                    example.get("reading")
                    or example.get("furigana")
                    or example.get("pronunciation")
                    or example.get("pronunciations")
                    or ""
                ),
                "translation": (
                    example.get("translation")
                    or example.get("translation in zh-tw")
                    or example.get("translationInZhTw")
                    or ""
                ),
            }
        )

    return {
        "vocabulary": note_data.get("vocabulary") or note_data.get("word") or "",
        "kanji": note_data.get("kanji") or note_data.get("vocabulary") or note_data.get("word") or "",
        "furigana": note_data.get("furigana") or "",
        "pitchPattern": note_data.get("pitchPattern") or "",
        "pronunciations": note_data.get("pronunciations") or "",
        "explanations": {
            "en-US": explanations.get("en-US") or explanations.get("english") or "",
            "zh-TW": explanations.get("zh-TW") or explanations.get("traditionalChinese") or "",
        },
        "partsOfSpeech": note_data.get("partsOfSpeech") or "",
        "grammaticalRules": as_dict(note_data.get("grammaticalRules")),
        "sound": note_data.get("sound") or "",
        "exampleSentences": example_sentences,
    }
