
```json
{
    "openai_api_key": "1234",
    "other_api_key": "5678",
    "default_deck": "Big",
    "default_tag": "vocabulary::wordoftheday",
    "note_type": "vocbuilderAI",
    "model": "gpt-3.5-turbo-1106",
    "max_tokens": 15000,
    "temperature": 0.5,
    "speech_voice": "",
    "speech_model": "tts-1-hd",
    "speech_speed": 1.0,
    "provider":"openai",
    "base_url": "https://api.openai.com/v1/",
    "other_base_url": "https://api.example.com/v1/"
}
```

- openai_api_key: OpenAI API Key, can get from https://beta.openai.com/account/api-keys
- other_api_key: other llm provider's api key.
- model:  OpenAI Compatibility model (e.g., gpt-3.5-turbo-1106, groq, ollama, openrouter, etc.) 
- default_deck: Default deck for new notes
- default_tag: Default tag for new notes
- note_type: Note type for new notes
- max_tokens: The maximum number of tokens to generate
- temperature: Controls randomness. Lower temperature results in less random completions. As the temperature approaches zero, the model will become deterministic and repetitive. Higher temperature results in more random completions.
- speech_voice: The voice to use for speech synthesis; leave empty "" for random voice
- speech_speed: The speed of the generated audio. Select a value from 0.25 to 4.0. 1.0 is the default.
- base_url: for openai service, you can use openai or azure
- other_base_url: other llm provider's url.
