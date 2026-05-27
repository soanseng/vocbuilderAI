import time
from dataclasses import dataclass

import requests

try:
    from .settings import get_provider_defaults, normalize_api_key, resolve_provider_defaults
except ImportError:
    from settings import get_provider_defaults, normalize_api_key, resolve_provider_defaults


@dataclass
class HealthCheckResult:
    ok: bool
    message: str


def chat_completions_url(base_url):
    if "/chat/completions" in base_url:
        return base_url
    return f"{base_url.rstrip('/')}/chat/completions"


def redact_secret(value):
    if not value:
        return value
    text = str(value)
    if len(text) <= 8:
        return "[redacted]"
    return f"{text[:4]}...[redacted]...{text[-4:]}"


def redact_payload(value):
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            if key.lower() in {
                "authorization",
                "api_key",
                "apikey",
                "openai_api_key",
                "groq_api_key",
                "openrouter_api_key",
                "custom_api_key",
                "speech_api_key",
            }:
                redacted[key] = "[redacted]"
            else:
                redacted[key] = redact_payload(item)
        return redacted
    if isinstance(value, list):
        return [redact_payload(item) for item in value]
    return value


def build_chat_payload(vocab_word, system_prompt, addon_config, provider_defaults):
    model = (addon_config.get("model") or "").strip() or provider_defaults["model"]
    max_tokens = int(addon_config.get("max_tokens", 15000))
    temperature = float(addon_config.get("temperature", 0.5))
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": str(vocab_word)},
        ],
        "temperature": temperature,
        provider_defaults.get("token_param", "max_tokens"): max_tokens,
    }
    if provider_defaults.get("supports_response_format"):
        payload["response_format"] = {"type": "json_object"}
    if provider_defaults.get("disable_thinking"):
        payload["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
    return payload


def provider_headers(api_key, provider):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if provider == "openrouter":
        headers.update(
            {
                "HTTP-Referer": "https://ankiweb.net/shared/info/vocbuilderai",
                "X-Title": "VocBuilderAI",
            }
        )
    return headers


def format_http_error(error, response, full_url):
    try:
        response_body = response.json()
    except ValueError:
        response_body = response.text
    return (
        "LLM HTTP error:\n"
        f"{error}\nStatus Code: {response.status_code}\nURL: {full_url}\nResponse: {response_body}"
    )


def llm_api_request(
    payload,
    api_key,
    base_url,
    retries=3,
    provider="openai",
    notify=None,
    post=None,
    sleeper=None,
):
    api_key = normalize_api_key(api_key)
    notify = notify or (lambda message: None)
    post = post or requests.post
    sleeper = sleeper or time.sleep
    if not api_key:
        notify(f"{provider.capitalize()} API key is missing. Open VocBuilderAI Settings and add it.")
        return None

    full_url = chat_completions_url(base_url)
    headers = provider_headers(api_key, provider)

    for attempt in range(retries):
        try:
            response = post(full_url, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            return response
        except requests.exceptions.HTTPError as error:
            if attempt < retries - 1:
                sleeper(2)
                continue
            notify(format_http_error(error, response, full_url))
        except requests.exceptions.RequestException as error:
            if attempt < retries - 1:
                sleeper(2)
                continue
            notify(f"LLM request error:\n{error}\nURL: {full_url}")
    return None


def extract_chat_content(response):
    response_json = response.json()
    return response_json["choices"][0]["message"]["content"]


def selected_provider(addon_config):
    provider = addon_config.get("provider", "openai")
    if provider not in {"openai", "groq", "openrouter", "custom"}:
        provider = "openai"
    defaults = resolve_provider_defaults({**addon_config, "provider": provider})
    return provider, defaults


def health_check(addon_config, system_prompt, user_content, notify=None, post=None, sleeper=None):
    provider, defaults = selected_provider(addon_config)
    api_key = addon_config.get(defaults["api_key_config"])
    payload = build_chat_payload(user_content, system_prompt, addon_config, defaults)
    response = llm_api_request(
        payload,
        api_key,
        defaults["base_url"],
        retries=1,
        provider=provider,
        notify=notify,
        post=post,
        sleeper=sleeper,
    )
    if response is None:
        return HealthCheckResult(False, "Provider request failed.")
    try:
        content = extract_chat_content(response)
    except (KeyError, IndexError, TypeError, ValueError) as error:
        return HealthCheckResult(False, f"Unexpected provider response shape: {error}")
    return HealthCheckResult(True, content)
