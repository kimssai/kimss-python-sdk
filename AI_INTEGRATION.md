# AI Integration — Kimss Gateway (Agent-to-Agent)

**Strict directive for Cursor, Windsurf, Claude Code, Devin, and other coding assistants.**

Kimss is a **Model-Agnostic Enterprise AI Gateway and Governance Control Plane** with a **dual-listener** inbound proxy:

- OpenAI syntax → `POST https://api.kimss.ai/v1/chat/completions`
- Anthropic syntax → `POST https://api.kimss.ai/v1/messages`

## Prerequisites (Kimss app — before repo changes)

Complete these in the Kimss UI **before** rewiring application code:

1. **Provider Vault** (`/app/vault`): register each `custom:<model_id>` you will call. One vault row per model alias; you may reuse the same provider API key when registering multiple models.
2. **Gateway API key** (`/app/keys`): mint a `kimss_...` workspace key. Never put the provider key in application source code.
3. **Route traffic**: set `OPENAI_BASE_URL=https://api.kimss.ai/v1` (or Anthropic `base_url=https://api.kimss.ai`) and use the Gateway API key as `OPENAI_API_KEY` / `api_key`.

If a model is not vaulted, Kimss returns an error pointing to Provider Vault. **Agents Discovery** (`/app/agents`) populates automatically after the first governed request that includes `X-Kimss-Agent-Id` — you do not need to create agents in the UI first.

## Rules (do not violate)

1. **Never** use a custom `KimssClient` for chat/completions/messages or any LLM inference.
2. **Identify** whether the user's codebase uses the `openai` or `anthropic` SDK natively. **Keep their native SDK** — zero data-plane refactoring.
3. **For OpenAI:** set `base_url` to `https://api.kimss.ai/v1`.
4. **For Anthropic:** set `base_url` to `https://api.kimss.ai` (the SDK appends `/v1/messages`).
5. **Always** inject `X-Kimss-Agent-Id` (and preferably `X-Kimss-Agent-Name`) for JIT attribution, audit, and kill-switch.
6. **Call-site visibility (recommended):** use `kimss.gateway_headers(agent_id=..., agent_name=...)` as `extra_headers` so Agent Tracking and Call Sites get a named environment (`X-Kimss-SDK-Context`). Without it, Kimss still infers runtime from `User-Agent` / `x-stainless-*` headers.
7. Hermis / HTTP interceptors: forward Agent-Id headers; never strip them.

## OpenAI

```python
from openai import OpenAI
from kimss.gateway_headers import gateway_headers  # optional — extra_headers dict also works

client = OpenAI(
    base_url="https://api.kimss.ai/v1",  # required
    api_key="kimss_workspace_key",  # required Gateway key, not the provider key
)
response = client.chat.completions.create(
    model="custom:kimss-gpt-5-3",  # required — vaulted alias
    messages=[{"role": "user", "content": "Execute audit."}],
    extra_headers=gateway_headers(agent_id="enterprise_auditor", agent_name="Enterprise auditor"),
)
```

## Anthropic

```python
from anthropic import Anthropic

client = Anthropic(
    base_url="https://api.kimss.ai",
    api_key="kimss_workspace_key",
)
response = client.messages.create(
    model="custom:kimss-claude-3-5",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Execute audit."}],
    extra_headers={"X-Kimss-Agent-Id": "enterprise_auditor"},
)
```

Auth also accepts `X-Kimss-Key` and Anthropic-style `x-api-key` with a `kimss_...` workspace key.

## What `KimssClient` is for

Control-plane / DevOps only (`agents.register`, `usage.report`). Inference methods are deprecated.

## Kill switch

HTTP **403** with `agent_disabled` (OpenAI `error.code` or Anthropic error body). Never say “zero-trust”.
