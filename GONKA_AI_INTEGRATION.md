# Gonka AI API — Integration Guide for Claude Code

> A reference playbook for integrating the **Gonka** decentralized AI network into any
> project. Gonka exposes an **OpenAI-compatible API**, so if a project can call OpenAI,
> it can call Gonka with a base-URL + key swap. Drop this file into a repo (e.g. as
> `docs/GONKA_AI_INTEGRATION.md` or reference it from `CLAUDE.md`) so the coding agent
> has the full contract on hand.

---

## 1. What Gonka is (in one paragraph)

Gonka is a decentralized network for AI inference. Instead of one company hosting the
models, inference is load-balanced across independent hardware providers, billed and
settled on-chain, and spot-checked for correctness. The models are **open-source LLMs**
(Qwen, Kimi, MiniMax, etc.). Under the hood Gonka runs **vLLM**, which implements the
**OpenAI Chat Completions spec** — that's why any OpenAI SDK or OpenAI-compatible tool
works against it. The main practical wins are lower cost and provider independence.

**What this means for integration:** you do **not** need a Gonka-specific SDK. Use the
standard `openai` client (Python/JS/Go) or any framework's "OpenAI-compatible provider"
option, and point it at a Gonka endpoint.

---

## 2. Two ways to access the network

| Path | Who it's for | What you deal with |
|------|--------------|--------------------|
| **Community broker** (recommended) | Almost everyone | Sign up on a broker site, get an API key, pay in USD or crypto. Behaves exactly like an OpenAI endpoint. |
| **Self-hosted gateway** (advanced) | High-throughput / infra teams | Run a Docker gateway, hold GNK, pay on-chain per request. Requires an on-chain **allow-listed** address (governance-gated). |

**Default assumption for integration work: use a broker.** Only go the gateway route if
the project explicitly needs to own keys / settle on-chain and the operator address is
already allow-listed. The rest of this guide assumes the broker path unless noted.

### Brokers are third parties
Each broker sets its own pricing, payment methods, rate limits, supported models, SLAs,
refund and data-handling policies. Always read the specific broker's terms before going
to production. The broker choice only changes the **base URL, key format, model list, and
limits** — the request/response shape stays OpenAI-compatible.

### Known community brokers (verify current list at `gonka.ai/docs/developer/quickstart`)
- `https://gonkagate.com/` — USD prepaid billing, keys prefixed `gp-`, base URL `https://api.gonkagate.com/v1`
- `https://gonka24.com/`
- `https://proxy.gonka.gg/`
- `https://gate.joingonka.ai/`
- `https://router.gonkascan.com/`
- `https://gonka-api.org/`
- `https://gonkabroker.com/`
- `https://router.mingles.ai/`
- `https://console.hyperfusion.io/`
- `https://inference.dahl.global`

Community observability dashboards (uptime/latency/price comparison) live at
`meter.gonka.gg` and `power.gnk.space`. Treat these as community tools, not ground truth —
verify against your own testing.

---

## 3. The three things you always need

Every integration comes down to obtaining these from your chosen broker:

1. **Base URL** — the broker URL with `/v1` appended, e.g. `https://api.<broker>.com/v1`.
   Wherever an app asks for "OpenAI Base URL" / "Custom Endpoint", this goes there.
2. **API key** — generated in the broker dashboard. Sent as `Authorization: Bearer <KEY>`.
   Use it even where a field literally says "OpenAI API Key".
3. **Model ID** — an exact, **case-sensitive** string, e.g. `MiniMaxAI/MiniMax-M2.7`.
   Copy it verbatim from the broker's model list; do not guess or reformat it.

### Environment variable convention (use this across all projects)
```bash
export GONKA_BASE_URL="https://api.<broker>.com/v1"
export GONKA_API_KEY="<your-broker-api-key>"
export GONKA_MODEL="MiniMaxAI/MiniMax-M2.7"   # or any model the broker lists
```
Never hardcode the key. Put it in `.env` (git-ignored), a secrets manager, or CI secrets.

---

## 4. Discover available models before hardcoding one

Model availability changes per broker and over time. Query it at runtime rather than
assuming — this also validates the base URL + key in one call.

```bash
curl "$GONKA_BASE_URL/models" \
  -H "Authorization: Bearer $GONKA_API_KEY"
```

```python
from openai import OpenAI
import os

client = OpenAI(base_url=os.environ["GONKA_BASE_URL"], api_key=os.environ["GONKA_API_KEY"])
for m in client.models.list().data:
    print(m.id)
```

Use `GET /v1/models` in CI or on startup to fail fast if a configured `GONKA_MODEL` is no
longer served by the broker.

---

## 5. Minimal integration by language

### Python
```bash
pip install openai
```
```python
import os
from openai import OpenAI

client = OpenAI(
    base_url=os.environ["GONKA_BASE_URL"],
    api_key=os.environ["GONKA_API_KEY"],
)

resp = client.chat.completions.create(
    model=os.environ["GONKA_MODEL"],
    messages=[{"role": "user", "content": "Write a one-sentence bedtime story about a unicorn."}],
)
print(resp.choices[0].message.content)
```

### TypeScript / JavaScript
```bash
npm install openai
```
```ts
import OpenAI from "openai";

const client = new OpenAI({
  baseURL: process.env.GONKA_BASE_URL,
  apiKey: process.env.GONKA_API_KEY,
});

const resp = await client.chat.completions.create({
  model: process.env.GONKA_MODEL!,
  messages: [{ role: "user", content: "Tell me a short joke." }],
});
console.log(resp.choices[0].message.content);
```

### Go
```go
package main

import (
    "context"
    "log"
    "os"

    "github.com/openai/openai-go"
    "github.com/openai/openai-go/option"
)

func main() {
    client := openai.NewClient(
        option.WithBaseURL(os.Getenv("GONKA_BASE_URL")),
        option.WithAPIKey(os.Getenv("GONKA_API_KEY")),
    )
    r, err := client.Chat.Completions.New(context.Background(), openai.ChatCompletionNewParams{
        Model:    os.Getenv("GONKA_MODEL"),
        Messages: []openai.ChatCompletionMessageParamUnion{openai.UserMessage("Write a haiku about programming")},
    })
    if err != nil {
        log.Fatal(err)
    }
    log.Println(r.Choices[0].Message.Content)
}
```

### Raw cURL
```bash
curl "$GONKA_BASE_URL/chat/completions" \
  -H "Authorization: Bearer $GONKA_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"model\": \"$GONKA_MODEL\",
    \"messages\": [{\"role\": \"user\", \"content\": \"Hello\"}]
  }"
```

---

## 6. Streaming

Same endpoint, `stream: true`. Works identically to OpenAI streaming.

```python
stream = client.chat.completions.create(
    model=os.environ["GONKA_MODEL"],
    messages=[{"role": "user", "content": "Explain diffusion models in 3 sentences."}],
    stream=True,
)
for chunk in stream:
    delta = chunk.choices[0].delta.content
    if delta:
        print(delta, end="", flush=True)
```

```ts
const stream = await client.chat.completions.create({
  model: process.env.GONKA_MODEL!,
  messages: [{ role: "user", content: "Explain diffusion models in 3 sentences." }],
  stream: true,
});
for await (const chunk of stream) {
  process.stdout.write(chunk.choices[0]?.delta?.content ?? "");
}
```

---

## 7. Tool / function calling

Supported through the same chat endpoint. **Only `type: "function"` tools work.** The
Assistants-API tools (`code_interpreter`, `file_search`) are **not** available, because
Gonka is a vLLM chat-completions backend, not the Assistants API.

```python
import json

tools = [{
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get the current weather for a city",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string", "description": "City name"}},
            "required": ["city"],
        },
    },
}]

resp = client.chat.completions.create(
    model=os.environ["GONKA_MODEL"],
    messages=[{"role": "user", "content": "What's the weather in Paris?"}],
    tools=tools,
    tool_choice="auto",
)

msg = resp.choices[0].message
if msg.tool_calls:
    call = msg.tool_calls[0]
    args = json.loads(call.function.arguments)
    # 1) run your real function here -> result
    # 2) append the assistant tool_call msg + a {"role":"tool", ...} result msg
    # 3) call chat.completions.create again to get the final answer
    print(call.function.name, args)
```

Tool-calling quality varies by model — prefer models the broker documents as tool-capable,
and always validate/parse `arguments` defensively (it's model-generated JSON).

---

## 8. Structured outputs

Structured / JSON outputs use the same chat endpoint. Support depends on the selected
model. Two robust patterns:

1. **JSON via prompt + parse** (works everywhere): instruct the model to return *only*
   JSON, then `json.loads` the content. Strip any accidental ```` ```json ```` fences first.
2. **`response_format`** (if the model/broker supports it): pass
   `response_format={"type": "json_object"}` and still parse defensively.

Because you can't assume a given model enforces a schema, always wrap parsing in
try/except and re-prompt or fall back on failure.

---

## 9. Framework integrations

Anything with an "OpenAI-compatible provider" slot works. Set base URL + key + model.

**LangChain (Python)**
```python
from langchain_openai import ChatOpenAI
llm = ChatOpenAI(
    base_url=os.environ["GONKA_BASE_URL"],
    api_key=os.environ["GONKA_API_KEY"],
    model=os.environ["GONKA_MODEL"],
)
```

**LlamaIndex (Python)**
```python
from llama_index.llms.openai_like import OpenAILike
llm = OpenAILike(
    api_base=os.environ["GONKA_BASE_URL"],
    api_key=os.environ["GONKA_API_KEY"],
    model=os.environ["GONKA_MODEL"],
    is_chat_model=True,
)
```

**Vercel AI SDK (TypeScript)**
```ts
import { createOpenAI } from "@ai-sdk/openai";
const gonka = createOpenAI({
  baseURL: process.env.GONKA_BASE_URL,
  apiKey: process.env.GONKA_API_KEY,
});
// use: gonka(process.env.GONKA_MODEL!)
```

**Chat UIs (Open WebUI, LibreChat, LobeChat):** Settings → AI Providers / Connections →
choose **OpenAI**, replace the URL with the broker URL + `/v1`, paste the key, add the
Model ID to the allowed-models list.

**AI IDEs / coding agents (Cursor, Cline, Windsurf):** Settings → Models → enable
**OpenAI-compatible** (or "Add Custom Model"), override Base URL with broker + `/v1`, paste
the key.

**No-code automations (n8n, Make.com, Flowise):** use the standard **OpenAI** node, then
open its advanced settings and override the **Base URL / Base Path** with the broker URL.
Handy when wiring Gonka into an existing n8n/Twilio/WhatsApp or webhook flow.

---

## 10. FastAPI proxy pattern (optional but recommended for frontends)

Never ship a broker key to a browser or mobile client. Put a thin server between them.
This mirrors the common "sign & forward" gateway pattern.

```python
import os
from fastapi import FastAPI
from pydantic import BaseModel
from openai import OpenAI

app = FastAPI()
client = OpenAI(base_url=os.environ["GONKA_BASE_URL"], api_key=os.environ["GONKA_API_KEY"])

class ChatIn(BaseModel):
    message: str

@app.post("/chat")
def chat(body: ChatIn):
    resp = client.chat.completions.create(
        model=os.environ["GONKA_MODEL"],
        messages=[{"role": "user", "content": body.message}],
    )
    return {"reply": resp.choices[0].message.content}
```
The frontend calls `/chat`; the key stays server-side. Add auth, rate limiting, and input
validation on this proxy before production.

---

## 11. Migrating an existing OpenAI project (drop-in swap)

If a codebase already uses the `openai` SDK, migration is usually a two-line change plus a
model rename:

```diff
  client = OpenAI(
-     api_key=os.environ["OPENAI_API_KEY"],
+     base_url=os.environ["GONKA_BASE_URL"],
+     api_key=os.environ["GONKA_API_KEY"],
  )

- model="gpt-4o"
+ model=os.environ["GONKA_MODEL"]   # e.g. "MiniMaxAI/MiniMax-M2.7"
```

Checklist for the swap:
- Replace every `model="gpt-..."` literal with a Gonka model ID (case-sensitive).
- Remove any Assistants-API usage (`code_interpreter`, `file_search`, threads, vector
  stores) — not supported. Re-implement as function tools + your own retrieval.
- Remove image/audio/video endpoints (see §12) — not supported yet.
- Re-test tool calling and any `response_format` usage against the target model.
- Update rate-limit / retry config to the broker's documented limits.

---

## 12. Capabilities & hard constraints (read before scoping)

**Supported now:** chat completions, model discovery (`/v1/models`), streaming, tool
calling (`type: "function"` only), structured/JSON outputs (model-dependent).

**Not available:**
- **Image, video, audio** generation or input — text-in/text-out only for now. Keep
  Whisper / TTS / vision on a separate provider and orchestrate in your app.
- **Assistants API** primitives — `code_interpreter`, `file_search`, threads, etc.
- Anything requiring provider-managed retrieval or code execution.

**Behavioral notes:**
- Model IDs are case-sensitive and namespaced (`Vendor/Model-Name`). A wrong case = error.
- Capabilities (tool calling, JSON mode, context length) vary **per model** — confirm with
  the broker's model page, don't assume parity with OpenAI models.
- Rate limits, quotas, and SLAs are broker-specific, not protocol guarantees.

---

## 13. Error handling & resilience

Because you're going through a decentralized network + a third-party broker, build for
transient failures from day one:

- **Wrap calls in try/except** and surface a clean fallback (retry, alternate model, or
  alternate provider).
- **Exponential backoff with jitter** on 429 / 5xx. Respect any `Retry-After` header.
- **Timeouts** on every request; don't let a slow host hang a user flow.
- **Validate model-generated JSON** (tool args, structured outputs) before using it.
- **Startup health check:** call `/v1/models` (or a 1-token completion) so misconfigured
  base URL / key / model fails loudly at boot, not mid-request.
- **Provider abstraction:** wrap the client behind a small interface so you can fail over
  between brokers (or back to OpenAI/Anthropic) by swapping base URL + key + model.

```python
import time, random
from openai import OpenAI, APIError, RateLimitError, APITimeoutError

def chat_with_retry(client, model, messages, max_retries=4):
    for attempt in range(max_retries):
        try:
            return client.chat.completions.create(
                model=model, messages=messages, timeout=60,
            )
        except (RateLimitError, APITimeoutError, APIError):
            if attempt == max_retries - 1:
                raise
            time.sleep((2 ** attempt) + random.random())
```

---

## 14. Security & cost hygiene

- **Never** commit keys or ship them to clients. Server-side only; use a proxy (§10) for
  browser/mobile.
- Rotate broker keys periodically and on any suspected leak.
- Set **spending limits / alerts** in the broker dashboard — usage is prepaid, but a
  runaway loop can still burn balance.
- Log request/response metadata (not full sensitive payloads) for cost and latency
  tracking; brokers like GonkaGate expose cost breakdowns (network cost vs. platform fee).
- For regulated data (e.g. clinical/medical text), review the specific broker's data-
  handling and retention terms before sending real PII/PHI.

---

## 15. Integration checklist (for the coding agent)

Work through this when adding Gonka to a project:

- [ ] Chosen a broker; created an account and API key.
- [ ] Recorded base URL (`.../v1`), key, and a confirmed model ID from `/v1/models`.
- [ ] Added `GONKA_BASE_URL`, `GONKA_API_KEY`, `GONKA_MODEL` to `.env` (git-ignored) and to
      the deploy/CI secret store.
- [ ] Installed the OpenAI SDK for the target language (no Gonka-specific client).
- [ ] Implemented a startup health check against `/v1/models`.
- [ ] Wrapped all inference calls with timeout + retry/backoff + error handling.
- [ ] Confirmed feature support for the chosen model (streaming? tools? JSON mode?).
- [ ] Removed any unsupported OpenAI features (images/audio/video, Assistants API).
- [ ] Kept keys server-side; added a proxy if a client app talks to the model.
- [ ] Abstracted the provider behind an interface for easy failover.
- [ ] Set spending alerts; documented the broker's limits and terms in the repo.

---

## 16. Canonical references

- Developer quickstart: `https://gonka.ai/docs/developer/quickstart/`
- Run your own gateway: `https://gonka.ai/docs/developer/gateway-developer-quickstart/`
- Errors reference: `https://gonka.ai/docs/Errors/`
- Main site / protocol docs: `https://gonka.ai/`
- Example broker docs (USD billing): `https://gonkagate.com/en/docs/quickstart`

> **One-line mental model:** *Gonka = OpenAI-compatible text inference on a decentralized
> network. Swap `base_url` + `api_key` + `model`, keep the OpenAI SDK, drop image/audio and
> Assistants features, and build for third-party/broker-level reliability.*
