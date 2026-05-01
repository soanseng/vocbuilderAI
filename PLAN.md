# VocBuilderAI Improvement Plan

This plan captures the next practical improvements for the add-on. `CLAUDE.md`
remains the canonical source of truth for agent instructions.

## Goals

- Reduce provider/model-related crashes.
- Make settings easier to validate before generating cards.
- Improve Japanese and multilingual card quality.
- Keep user-specific Anki configuration, especially `meta.json`, safe and local.
- Make future provider changes easier to maintain and test.

## Phase 1: Settings Health Checks

Add validation tools directly to the settings dialog.

### Work

- Add a `Test API` button for the selected provider/model.
- Add a `Test Japanese JSON` button that verifies multilingual JSON generation and parsing.
- Add a `Test TTS` button for speech configuration.
- Show actionable error messages with provider, model, HTTP status, and response message.
- Ensure API keys are never logged or shown in dialogs.

### Acceptance Criteria

- A user can confirm whether OpenAI, Groq, or OpenRouter is usable without creating a card.
- A failing model/provider produces a clear message instead of an Anki crash.
- Japanese JSON failures are caught before note creation.

### Tests

- Unit test successful API health check payloads.
- Unit test HTTP error formatting.
- Unit test Japanese JSON health-check parsing.
- Unit test that API keys are redacted from displayed errors.

## Phase 2: Configuration Migration

Make upgrades from older versions safer.

### Work

- Add a configuration migration layer.
- Drop unsupported providers from old user config.
- Fallback to `openai` when the stored provider no longer exists.
- Treat an empty model as "use provider default".
- Ignore removed fields such as old provider API keys without crashing.
- Preserve user-owned Anki `meta.json` in the installed add-on directory.

### Acceptance Criteria

- Old config containing removed providers still loads.
- Existing user API keys are not overwritten.
- Invalid provider/model settings recover to a working default.

### Tests

- Migration test for removed providers.
- Migration test for missing model values.
- Migration test for unknown fields.
- Regression test to ensure `meta.json` is not part of repo-managed config.

## Phase 3: LLM Provider Layer

Separate provider-specific request behavior from Anki UI logic.

### Work

- Move provider definitions and payload building into `llm.py`.
- Keep provider-specific token parameters isolated:
  - OpenAI: `max_completion_tokens`
  - OpenRouter/Groq: `max_tokens`
- Keep provider-specific `response_format` behavior isolated.
- Normalize HTTP and JSON errors into typed internal results.

### Acceptance Criteria

- Adding or changing a provider does not require editing settings UI code.
- Provider payload rules are covered by focused tests.
- OpenAI/OpenRouter/Groq failures return structured errors instead of raising raw exceptions into UI code.

### Tests

- Snapshot-style tests for each provider payload.
- Tests for OpenAI completion token parameter.
- Tests for OpenRouter without `response_format`.
- Retry and timeout tests.

## Phase 4: Parsing And Normalization

Make model output tolerant but strict at the boundary.

### Work

- Move JSON cleanup and parsing into `parsing.py`.
- Add schema normalization for English and Japanese responses.
- Convert missing optional fields into empty strings or arrays.
- Reject unrecoverable responses with a clear error.
- Keep raw malformed responses out of Anki note fields.

### Acceptance Criteria

- Markdown-fenced JSON, minor surrounding text, and missing optional fields do not crash note creation.
- Bad responses fail with a useful message.
- Japanese responses consistently map to expected Anki fields.

### Tests

- Malformed JSON corpus tests.
- Japanese partial-response tests.
- English partial-response tests.
- Tests for Markdown fences and extra prose around JSON.

## Phase 5: Prompt And Card Quality Modes

Give users simple quality controls instead of requiring prompt edits.

### Work

- Add a generation mode setting:
  - `Concise`
  - `Standard`
  - `Deep`
  - `Japanese`
- Map each mode to explicit prompt constraints.
- Limit examples, synonyms, antonyms, and explanations by mode.
- Require stable field names in Japanese prompts, especially `translation`.

### Acceptance Criteria

- Users can choose shorter or richer cards from settings.
- Japanese generation produces stable fields across supported providers.
- Prompt changes remain easy to test without calling real APIs.

### Tests

- Prompt contract tests for each mode.
- Tests that Japanese prompts require fixed field names.
- Tests that mode-specific limits are present in prompt text.

## Phase 6: Formatting And Note Integration

Make final Anki note writing resilient.

### Work

- Move field formatting into `formatters.py`.
- Validate note type fields before writing.
- Show missing-field diagnostics if the Anki note type is incomplete.
- Keep formatting stable for empty or partial data.

### Acceptance Criteria

- Missing optional content does not crash generation.
- Missing required Anki fields are reported clearly.
- English and Japanese notes produce readable card fields.

### Tests

- Fake Anki note integration tests.
- Missing-field tests.
- Formatter tests for empty arrays, strings, and partial dictionaries.

## Phase 7: Cost And Debugging Improvements

Reduce repeated API calls and improve supportability.

### Work

- Add a short-lived generation cache keyed by word, language, provider, model, and generation mode.
- Add safe debug logging for provider errors and parse failures.
- Redact API keys and authorization headers from logs.
- Consider a `Regenerate examples only` path after the main architecture is split.

### Acceptance Criteria

- Repeating the same generation shortly after a success can reuse cached content.
- Debug output helps diagnose provider/model failures without leaking secrets.
- Cache can be disabled or bypassed when needed.

### Tests

- Cache hit/miss tests.
- Redaction tests.
- Debug logging tests for HTTP and parse errors.

## Suggested Order

1. Implement Phase 2 first if upgrade safety is the priority.
2. Implement Phase 3 and Phase 4 together if crash reduction is the priority.
3. Implement Phase 1 after provider/parsing boundaries are clean.
4. Implement Phase 5 after the parser can enforce stable schemas.
5. Implement Phase 6 before adding more card output variants.
6. Implement Phase 7 last, after behavior is stable enough to cache.

## Release Checklist

- Run `uv run pytest -q`.
- Run coverage with `uv run --with pytest-cov pytest --cov=. --cov-report=term-missing -q`.
- Run `python -m py_compile __init__.py prompts.py tests/test___init__.py`.
- Verify removed provider names do not reappear in user-facing settings or docs.
- Confirm `meta.json` is not tracked by git.
- Restart Anki after symlink-installed code changes.
