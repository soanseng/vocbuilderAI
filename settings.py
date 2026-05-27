CONFIG_DEFAULTS = {
    "openai_api_key": "your-openai-key",
    "groq_api_key": "your-groq-key",
    "openrouter_api_key": "your-openrouter-key",
    "custom_api_key": "your-custom-key",
    "custom_base_url": "http://your-litellm-server:4000/v1",
    "custom_supports_response_format": False,
    "custom_disable_thinking": True,
    "default_deck": "Big",
    "default_tag": "vocabulary::wordoftheday",
    "note_type": "vocbuilderAI",
    "model": "",
    "max_tokens": 15000,
    "temperature": 0.5,
    "speech_voice": "",
    "speech_model": "gpt-4o-mini-tts",
    "speech_speed": 1.0,
    "provider": "openai",
    "generation_mode": "standard",
    "cache_enabled": True,
}

PROVIDER_DEFAULTS = {
    "openai": {
        "model": "5.4-nano",
        "base_url": "https://api.openai.com/v1",
        "api_key_config": "openai_api_key",
        "supports_response_format": True,
        "token_param": "max_completion_tokens",
    },
    "groq": {
        "model": "llama-3.3-70b-versatile",
        "base_url": "https://api.groq.com/openai/v1/chat/completions",
        "api_key_config": "groq_api_key",
        "supports_response_format": True,
        "token_param": "max_tokens",
    },
    "openrouter": {
        "model": "openai/gpt-4o-mini",
        "base_url": "https://openrouter.ai/api/v1/chat/completions",
        "api_key_config": "openrouter_api_key",
        "supports_response_format": False,
        "token_param": "max_tokens",
    },
    "custom": {
        "model": "qwen36-fast",
        "base_url": CONFIG_DEFAULTS["custom_base_url"],
        "api_key_config": "custom_api_key",
        "supports_response_format": CONFIG_DEFAULTS["custom_supports_response_format"],
        "supports_disable_thinking": True,
        "token_param": "max_tokens",
    },
}

GENERATION_MODES = {
    "concise": {
        "label": "Concise",
        "description": "Short learner card with fewer examples.",
    },
    "standard": {
        "label": "Standard",
        "description": "Balanced card for everyday vocabulary study.",
    },
    "deep": {
        "label": "Deep",
        "description": "Richer definitions, usage notes, and examples.",
    },
    "japanese": {
        "label": "Japanese",
        "description": "Japanese-focused card with stable readings and translations.",
    },
}

PLACEHOLDER_KEYS = {
    "your-openai-key",
    "your-groq-key",
    "your-openrouter-key",
    "your-custom-key",
}

def get_provider_defaults(provider):
    return PROVIDER_DEFAULTS.get(provider, PROVIDER_DEFAULTS["openai"])


def resolve_provider_defaults(addon_config):
    provider = addon_config.get("provider", CONFIG_DEFAULTS["provider"])
    defaults = dict(get_provider_defaults(provider))
    if provider == "custom":
        defaults["base_url"] = (addon_config.get("custom_base_url") or defaults["base_url"]).strip()
        defaults["supports_response_format"] = bool(
            addon_config.get("custom_supports_response_format", defaults["supports_response_format"])
        )
        if defaults.get("supports_disable_thinking"):
            defaults["disable_thinking"] = bool(addon_config.get("custom_disable_thinking", True))
    return defaults


def normalize_api_key(api_key):
    api_key = (api_key or "").strip()
    if not api_key or api_key in PLACEHOLDER_KEYS:
        return ""
    return api_key


def normalize_generation_mode(mode):
    mode = (mode or "").strip().lower()
    if mode not in GENERATION_MODES:
        return CONFIG_DEFAULTS["generation_mode"]
    return mode


def migrate_config(raw_config=None):
    raw_config = raw_config or {}
    supported_config = {key: raw_config[key] for key in CONFIG_DEFAULTS if key in raw_config}
    migrated = {**CONFIG_DEFAULTS, **supported_config}

    if migrated.get("provider") not in PROVIDER_DEFAULTS:
        migrated["provider"] = CONFIG_DEFAULTS["provider"]

    migrated["model"] = (migrated.get("model") or "").strip()
    migrated["custom_base_url"] = (migrated.get("custom_base_url") or CONFIG_DEFAULTS["custom_base_url"]).strip()
    migrated["custom_supports_response_format"] = bool(migrated.get("custom_supports_response_format", False))
    migrated["custom_disable_thinking"] = bool(migrated.get("custom_disable_thinking", True))
    migrated["generation_mode"] = normalize_generation_mode(migrated.get("generation_mode"))

    try:
        migrated["max_tokens"] = int(migrated.get("max_tokens", CONFIG_DEFAULTS["max_tokens"]))
    except (TypeError, ValueError):
        migrated["max_tokens"] = CONFIG_DEFAULTS["max_tokens"]

    try:
        migrated["temperature"] = float(migrated.get("temperature", CONFIG_DEFAULTS["temperature"]))
    except (TypeError, ValueError):
        migrated["temperature"] = CONFIG_DEFAULTS["temperature"]

    try:
        migrated["speech_speed"] = float(migrated.get("speech_speed", CONFIG_DEFAULTS["speech_speed"]))
    except (TypeError, ValueError):
        migrated["speech_speed"] = CONFIG_DEFAULTS["speech_speed"]

    return migrated


def config_for_storage(current_config):
    config = migrate_config(current_config)
    return {key: config[key] for key in CONFIG_DEFAULTS}
