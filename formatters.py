try:
    from .parsing import as_dict, as_list
except ImportError:
    from parsing import as_dict, as_list


def html_text(value, fallback=""):
    if value is None:
        return fallback
    return str(value)


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
            reading = ""
            translation = ""
        else:
            exampleSentence = as_dict(exampleSentence)
            sentence = exampleSentence.get("sentence", "")
            reading = (
                exampleSentence.get("reading")
                or exampleSentence.get("furigana")
                or exampleSentence.get("pronunciation")
                or exampleSentence.get("pronunciations")
                or ""
            )
            translation = (
                exampleSentence.get("translation")
                or exampleSentence.get("translation in zh-tw")
                or exampleSentence.get("translationInZhTw")
                or ""
            )
        html_content += f"<li><strong>{html_text(sentence)}</strong>"
        if reading:
            html_content += f"<br><span><em>{html_text(reading)}</em></span>"
        if translation:
            html_content += f" - {html_text(translation)}"
        html_content += "</li>"
    html_content += "</ol>"
    return html_content
