```json
{
    "openai_api_key": "your-openai-key",
    "groq_api_key": "your-groq-key",
    "openrouter_api_key": "your-openrouter-key",
    "custom_api_key": "your-custom-key",
    "custom_base_url": "http://your-litellm-server:4000/v1",
    "custom_supports_response_format": false,
    "custom_disable_thinking": true,
    "default_deck": "Big",
    "default_tag": "vocabulary::wordoftheday",
    "note_type": "vocbuilderAI",
    "model": "",
    "max_tokens": 15000,
    "temperature": 0.5,
    "speech_provider": "openai",
    "speech_api_key": "your-speech-key",
    "speech_base_url": "http://your-tts-server:8001/v1",
    "speech_voice": "",
    "speech_model": "gpt-4o-mini-tts",
    "speech_response_format": "",
    "speech_sample_rate": 24000,
    "speech_speed": 1.0,
    "provider": "openai",
    "generation_mode": "standard",
    "cache_enabled": true
}
```

- openai_api_key: OpenAI API key from https://platform.openai.com/api-keys
- groq_api_key: Groq API key from https://console.groq.com
- openrouter_api_key: OpenRouter API key from https://openrouter.ai
- custom_api_key: API key for an OpenAI-compatible custom provider, such as LiteLLM
- custom_base_url: Base URL for the custom provider. For the GB10 LiteLLM service, use `http://your-litellm-server:4000/v1`
- custom_supports_response_format: Whether to send OpenAI `response_format={"type":"json_object"}` to the custom provider
- custom_disable_thinking: Whether to send `extra_body.chat_template_kwargs.enable_thinking=false` for Qwen/vLLM custom providers
- provider: LLM provider to use (openai, groq, openrouter, or custom)
- generation_mode: Card generation style (concise, standard, deep, or japanese)
- cache_enabled: Reuse recent identical generations to avoid repeated API calls
- model: Model name for the selected provider:
  - OpenAI default: 5.4-nano
  - Groq: llama-3.3-70b-versatile
  - OpenRouter: openai/gpt-4o-mini, anthropic/claude-3.5-sonnet, etc.
  - Custom/LiteLLM: qwen36-fast, qwen36-deep, or qwen36-35b-heretic
  - Leave blank to use the provider default.
- default_deck: Default deck for new notes
- default_tag: Default tag for new notes
- note_type: Note type for new notes
- max_tokens: Maximum number of tokens to generate
- temperature: Controls randomness (0.0-1.0). Lower = more deterministic
- speech_provider: Speech provider to use (`openai` or `custom`)
- speech_api_key: Optional speech-only API key. For OpenAI speech, leave this blank/placeholder to reuse `openai_api_key`. For GB10 Kokoro TTS, set this to the Speaches API key.
- speech_base_url: Base URL for custom OpenAI-compatible TTS. For GB10 Kokoro TTS, use `http://your-tts-server:8001/v1`
- speech_voice: Voice for speech synthesis (empty for random). GB10 Kokoro random voices use the American `af_*` and `am_*` voice list.
- speech_model: Speech model. For GB10 Kokoro TTS with English and Japanese voices, use `speaches-ai/Kokoro-82M-v1.0-ONNX`
- speech_response_format: Audio format. Leave blank for provider default (`mp3` for OpenAI, `wav` for GB10 Kokoro TTS).
- speech_sample_rate: Sample rate for custom TTS, default 24000
- speech_speed: Speech speed (0.25-4.0, default 1.0)
