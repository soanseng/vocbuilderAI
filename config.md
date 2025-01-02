```json
{
    "openai_api_key": "your-openai-key",
    "deepseek_api_key": "your-deepseek-key",
    "groq_api_key": "your-groq-key",
    "default_deck": "Big",
    "default_tag": "vocabulary::wordoftheday",
    "note_type": "vocbuilderAI",
    "model": "gpt-3.5-turbo",
    "max_tokens": 15000,
    "temperature": 0.5,
    "speech_voice": "",
    "speech_model": "tts-1-hd",
    "speech_speed": 1.0,
    "provider": "openai"
}
```

- openai_api_key: OpenAI API key from https://platform.openai.com/api-keys
- deepseek_api_key: Deepseek API key from https://platform.deepseek.ai
- groq_api_key: Groq API key from https://console.groq.com
- provider: LLM provider to use (openai, deepseek, or groq)
- model: Model name for the selected provider:
  - OpenAI: gpt-3.5-turbo, gpt-4, etc.
  - Deepseek: deepseek-chat
  - Groq: mixtral-8x7b-32768
- default_deck: Default deck for new notes
- default_tag: Default tag for new notes
- note_type: Note type for new notes
- max_tokens: Maximum number of tokens to generate
- temperature: Controls randomness (0.0-1.0). Lower = more deterministic
- speech_voice: Voice for speech synthesis (empty for random)
- speech_speed: Speech speed (0.25-4.0, default 1.0)
