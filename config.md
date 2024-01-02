
```json
{
    "openai_api_key": "",
    "default_deck": "Big",
    "default_tag": "vocabulary::wordoftheday",
    "note_type": "vocbuilderAI",
    "model": "gpt-3.5-turbo-1106",
    "max_tokens": 15000,
    "temperature": 0.5,
    "speech_voice": "",
    "speech_model":"tts-1-hd"
}
```

- `openai_api_key`: OpenAI API Key, can get from https://beta.openai.com/account/api-keys
- `model`: OpenAI model, can get from https://beta.openai.com/models
- `default_deck`: Default deck for new notes
- `default_tag`: Default tag for new notes
- `note_type`: Note type for new notes
- `max_tokens`: The maximum number of tokens to generate
- `temperature`: Controls randomness. Lower temperature results in less random completions. As the temperature approaches zero, the model will become deterministic and repetitive. Higher temperature results in more random completions.
- `speech_voice`: The voice to use for speech synthesis; leave empty "" for random voice
