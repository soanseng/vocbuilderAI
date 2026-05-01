```json
{
    "openai_api_key": "your-openai-key",
    "deepseek_api_key": "your-deepseek-key",
    "groq_api_key": "your-groq-key",
    "openrouter_api_key": "your-openrouter-key",
    "default_deck": "Big",
    "default_tag": "vocabulary::wordoftheday",
    "note_type": "vocbuilderAI",
    "model": "",
    "max_tokens": 15000,
    "temperature": 0.5,
    "speech_voice": "",
    "speech_model": "gpt-4o-mini-tts",
    "speech_speed": 1.0,
    "provider": "openai"
}
```

- openai_api_key: OpenAI API key from https://platform.openai.com/api-keys
- deepseek_api_key: Deepseek API key from https://platform.deepseek.ai
- groq_api_key: Groq API key from https://console.groq.com
- openrouter_api_key: OpenRouter API key from https://openrouter.ai
- provider: LLM provider to use (openai, deepseek, groq, or openrouter)
- model: Model name for the selected provider:
  - OpenAI default: 5.4-nano
  - Deepseek: deepseek-chat
  - Groq: llama-3.3-70b-versatile
  - OpenRouter: openai/gpt-4o-mini, anthropic/claude-3.5-sonnet, etc.
  - Leave blank to use the provider default.
- default_deck: Default deck for new notes
- default_tag: Default tag for new notes
- note_type: Note type for new notes
- max_tokens: Maximum number of tokens to generate
- temperature: Controls randomness (0.0-1.0). Lower = more deterministic
- speech_voice: Voice for speech synthesis (empty for random)
- speech_speed: Speech speed (0.25-4.0, default 1.0)
