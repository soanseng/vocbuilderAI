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

def repair_invalid_escapes(text: str) -> str:
    """Fix backslashes that do not start a legal JSON escape sequence.

    Math generation asks the LLM for LaTeX (\\( ... \\)), and models routinely emit
    single backslashes inside JSON strings, which json.loads rejects as
    "Invalid \\escape". Consume the text in backslash pairs: legal escapes
    (including \\\\) are kept as-is; a lone backslash before any other character
    is doubled so it decodes to a literal backslash.
    """

    def fix_pair(match):
        pair = match.group(0)
        if pair[1] in '"\\/bfnrtu':
            return pair
        return "\\\\" + pair[1]

    return re.sub(r"\\.", fix_pair, text)

def repair_json_syntax(text: str) -> str:
    """Structurally repair near-valid JSON objects emitted by LLMs.

    Models behind custom providers occasionally emit JSON that is complete in
    content but invalid in syntax: a missing comma between members, a trailing
    comma, literal control characters inside a string, or output cut off
    mid-object. Walk the text once and rebuild it with only those structural
    problems fixed; content is never invented, reordered, or dropped beyond a
    dangling partial member at the point of truncation.
    """
    start = text.find("{")
    if start == -1:
        return text
    source = text[start:]

    literal_controls = {chr(code): f"\\u{code:04x}" for code in range(0x20)}
    literal_controls.update({"\n": "\\n", "\r": "\\r", "\t": "\\t"})
    out = []
    stack = []
    # state: "member" (object key or closer expected), "value" (value expected),
    # "key" (inside a key string), "colon" (after key, colon expected),
    # "value_done" (comma or closer expected next).
    state = "member"
    in_string = False
    in_literal = False
    member_start = None  # index in out where the current member's key opens

    def drop_dangling_member():
        nonlocal member_start, state
        if member_start is not None:
            del out[member_start:]
            member_start = None
        state = "value_done"

    def drop_trailing_comma():
        while out and out[-1].isspace():
            out.pop()
        if out and out[-1] == ",":
            out.pop()

    i = 0
    length = len(source)
    while i < length:
        ch = source[i]
        if not stack and state == "value_done" and not in_string and not in_literal:
            break  # top-level value already closed; ignore trailing content
        if in_string:
            if ch == "\\":
                if i + 1 < length:
                    out.append(source[i : i + 2])
                    i += 2
                else:
                    out.append("\\\\")  # dangling backslash must not escape the closer
                    i += 1
                continue
            if ch == '"':
                in_string = False
                state = "colon" if state == "key" else "value_done"
                out.append(ch)
            elif ch in literal_controls:
                out.append(literal_controls[ch])
            else:
                out.append(ch)
            i += 1
            continue

        if ch == '"':
            if in_literal or state == "value_done":
                out.append(",")  # missing comma between members
                in_literal = False
            if stack and stack[-1] == "{" and state in ("member", "value_done"):
                state = "key"
                member_start = len(out)
            else:
                state = "value"
            in_string = True
            out.append(ch)
            i += 1
            continue

        if ch in "{[":
            if in_literal:
                in_literal = False
                state = "value_done"
            if state == "value_done":
                out.append(",")  # missing comma between members
            stack.append("{" if ch == "{" else "[")
            state = "member" if ch == "{" else "value"
            out.append(ch)
            i += 1
            continue

        if in_literal and ch not in ",}]" and not ch.isspace():
            out.append(ch)
            i += 1
            continue

        if ch == ",":
            if in_literal:
                in_literal = False
                state = "value_done"
            if state == "value_done":
                out.append(ch)
                state = "member" if stack and stack[-1] == "{" else "value"
            elif state == "colon":
                drop_dangling_member()  # "key", -> drop the key, keep earlier comma
            i += 1
            continue

        if ch in "}]":
            if in_literal:
                in_literal = False
                state = "value_done"
            if state == "colon":
                drop_dangling_member()
            if not stack:
                break
            if state in ("member", "value"):
                drop_trailing_comma()
            out.append("}" if stack.pop() == "{" else "]")
            state = "value_done"
            i += 1
            continue

        if ch == ":":
            if state == "colon":
                state = "value"
                out.append(ch)
            elif state == "value" or in_literal:
                pass  # stray or duplicate colon
            else:
                out.append(ch)
            i += 1
            continue

        if ch.isspace():
            if in_literal:
                in_literal = False
                state = "value_done"
            out.append(ch)
            i += 1
            continue

        # bare token: number, true/false/null, or stray text
        if state == "value_done":
            out.append(",")  # missing comma between members
        in_literal = True
        state = "value"
        out.append(ch)
        i += 1

    if in_string:
        out.append('"')
        state = "colon" if state == "key" else "value_done"
    if in_literal:
        state = "value_done"
    if state == "colon":
        drop_dangling_member()
    drop_trailing_comma()
    while stack:
        out.append("}" if stack.pop() == "{" else "]")
    return "".join(out)

def process_response(response: str, notify=None) -> dict:
    notify = notify or (lambda message: None)
    cleaned_response = clean_response(response)
    if not cleaned_response:
        notify("No note data was returned by the LLM.")
        return {}
    raw_response = str(response).strip()
    candidates = [
        cleaned_response,
        repair_invalid_escapes(cleaned_response),
        repair_json_syntax(cleaned_response),
        repair_json_syntax(repair_invalid_escapes(cleaned_response)),
    ]
    if raw_response and raw_response != cleaned_response:
        # Without fences clean_response slices up to the last "}", which cuts
        # truncated output early; the state machine can recover past it.
        candidates.append(repair_json_syntax(raw_response))
        candidates.append(repair_json_syntax(repair_invalid_escapes(raw_response)))
    error = None
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError as parse_error:
            error = error or parse_error
            continue
        return parsed if isinstance(parsed, dict) else {}
    preview = cleaned_response if len(cleaned_response) <= 500 else cleaned_response[:500] + "\n…(truncated)"
    context = ""
    pos = getattr(error, "pos", None) if error is not None else None
    if isinstance(pos, int):
        lo = max(0, pos - 120)
        hi = min(len(cleaned_response), pos + 120)
        window = cleaned_response[lo:hi]
        prefix = "…" if lo > 0 else ""
        suffix = "…" if hi < len(cleaned_response) else ""
        context = f"\nContext: {prefix}{window}{suffix}"
    notify(f"Failed to parse note data: {error}{context}\nContent: {preview}")
    return {}


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
        "realWorldExamples": _normalize_japanese_examples(note_data.get("realWorldExamples")),
    }


def normalize_japanese_note_data(note_data):
    note_data = as_dict(note_data)
    explanations = as_dict(note_data.get("explanations"))
    example_sentences = _normalize_japanese_examples(note_data.get("exampleSentences"))

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


def _normalize_japanese_examples(raw_examples):
    examples = []
    for example in as_list(raw_examples):
        if isinstance(example, str):
            examples.append({"sentence": example, "reading": "", "translation": ""})
            continue
        example = as_dict(example)
        examples.append(
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
    return examples


def normalize_japanese_grammar_data(grammar_data):
    grammar_data = as_dict(grammar_data)
    grammar_points = []
    for point in as_list(grammar_data.get("grammarPoints")):
        if isinstance(point, str):
            grammar_points.append(
                {"expression": point, "grammarName": "", "meaning": "", "structure": "", "notes": ""}
            )
            continue
        point = as_dict(point)
        grammar_points.append(
            {
                "expression": point.get("expression") or point.get("fragment") or "",
                "grammarName": point.get("grammarName") or point.get("name") or point.get("pattern") or "",
                "meaning": point.get("meaning") or point.get("explanation") or "",
                "structure": point.get("structure") or point.get("formation") or "",
                "notes": point.get("notes") or point.get("note") or "",
            }
        )

    related_grammar = [item for item in as_list(grammar_data.get("relatedGrammar")) if isinstance(item, str)]
    return {
        "sentence": grammar_data.get("sentence") or grammar_data.get("vocabulary") or "",
        "reading": grammar_data.get("reading") or "",
        "translation": (
            grammar_data.get("translation")
            or grammar_data.get("translation in zh-tw")
            or grammar_data.get("translationInZhTw")
            or ""
        ),
        "grammarPoints": grammar_points,
        "relatedGrammar": related_grammar,
        "exampleSentences": _normalize_japanese_examples(grammar_data.get("exampleSentences")),
    }


def normalize_math_note_data(note_data):
    note_data = as_dict(note_data)
    return {
        "front": note_data.get("front") or "",
        "explanation": note_data.get("explanation") or "",
        "calculation": note_data.get("calculation") or note_data.get("derivation") or "",
        "example": note_data.get("example") or "",
        "notes": note_data.get("notes") or note_data.get("note") or "",
    }
