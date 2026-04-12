# LLM Model API Reference

A quick-reference of major LLM models and the exact string identifiers used in API calls.

---

## OpenAI

| Model | API String | Context Window | Notes |
|-------|-----------|----------------|-------|
| GPT-5.3 | `gpt-5.3` | 1M tokens | Latest flagship (Feb 2026) |
| GPT-5 | `gpt-5` | 1M tokens | GPT-5 base model |
| Codex | `codex` | 1M tokens | Autonomous coding agent model |
| GPT-4.1 | `gpt-4.1` | 1M tokens | Strong coding & instruction following |
| GPT-4.1 mini | `gpt-4.1-mini` | 1M tokens | Balanced cost/performance |
| GPT-4.1 nano | `gpt-4.1-nano` | 1M tokens | Fastest, lowest cost |
| GPT-4o | `gpt-4o` | 128K tokens | Multimodal (text + vision + audio) |
| GPT-4o mini | `gpt-4o-mini` | 128K tokens | Lightweight multimodal |
| GPT-4 Turbo | `gpt-4-turbo` | 128K tokens | Legacy |
| GPT-4 | `gpt-4` | 8K tokens | Legacy |
| GPT-3.5 Turbo | `gpt-3.5-turbo` | 16K tokens | Legacy, low cost |
| o4-mini | `o4-mini` | 200K tokens | Reasoning model, fast |
| o3 | `o3` | 200K tokens | Reasoning model, powerful |
| o3-mini | `o3-mini` | 200K tokens | Reasoning model, efficient |
| o1 | `o1` | 200K tokens | First reasoning model |
| o1-mini | `o1-mini` | 128K tokens | Lightweight reasoning |
| o1-pro | `o1-pro` | 200K tokens | Enhanced reasoning (ChatGPT Pro) |

### OpenAI Embeddings

| Model | API String | Dimensions | Notes |
|-------|-----------|------------|-------|
| text-embedding-3-large | `text-embedding-3-large` | 3072 | Best quality |
| text-embedding-3-small | `text-embedding-3-small` | 1536 | Cost-efficient |
| text-embedding-ada-002 | `text-embedding-ada-002` | 1536 | Legacy |

---

## Anthropic (Claude)

| Model | API String | Context Window | Notes |
|-------|-----------|----------------|-------|
| Claude Opus 4.6 | `claude-opus-4-6-20260210` | 200K tokens | Latest flagship (Feb 2026) |
| Claude Sonnet 4.6 | `claude-sonnet-4-6-20260210` | 200K tokens | Latest balanced (Feb 2026) |
| Claude Opus 4 | `claude-opus-4-20250514` | 200K tokens | Previous flagship |
| Claude Sonnet 4 | `claude-sonnet-4-20250514` | 200K tokens | Previous balanced |
| Claude 3.5 Sonnet (v2) | `claude-3-5-sonnet-20241022` | 200K tokens | Legacy |
| Claude 3.5 Haiku | `claude-3-5-haiku-20241022` | 200K tokens | Fast & affordable |
| Claude 3 Opus | `claude-3-opus-20240229` | 200K tokens | Legacy |
| Claude 3 Haiku | `claude-3-haiku-20240307` | 200K tokens | Legacy fast |

---

## Google (Gemini)

| Model | API String | Context Window | Notes |
|-------|-----------|----------------|-------|
| Gemini 2.5 Pro | `gemini-2.5-pro` | 1M tokens | Latest flagship with thinking |
| Gemini 2.5 Flash | `gemini-2.5-flash` | 1M tokens | Fast with thinking |
| Gemini 2.0 Flash | `gemini-2.0-flash` | 1M tokens | Multimodal, agentic |
| Gemini 2.0 Flash Lite | `gemini-2.0-flash-lite` | 1M tokens | Cost-efficient |
| Gemini 1.5 Pro | `gemini-1.5-pro` | 2M tokens | Long context |
| Gemini 1.5 Flash | `gemini-1.5-flash` | 1M tokens | Fast |
| Gemini 1.5 Flash-8B | `gemini-1.5-flash-8b` | 1M tokens | Smallest Gemini |

### Google Embeddings

| Model | API String | Dimensions | Notes |
|-------|-----------|------------|-------|
| text-embedding-004 | `text-embedding-004` | 768 | Latest |
| embedding-001 | `embedding-001` | 768 | Legacy |

---

## Meta (Llama) — via API providers

| Model | API String | Context Window | Notes |
|-------|-----------|----------------|-------|
| Llama 4 Maverick | `meta-llama/Llama-4-Maverick-17Bx128E` | 1M tokens | MoE, 128 experts |
| Llama 4 Scout | `meta-llama/Llama-4-Scout-17Bx16E` | 10M tokens | MoE, 16 experts |
| Llama 3.3 70B | `meta-llama/Llama-3.3-70B-Instruct` | 128K tokens | Best open-weight |
| Llama 3.1 405B | `meta-llama/Meta-Llama-3.1-405B-Instruct` | 128K tokens | Largest Llama |
| Llama 3.1 70B | `meta-llama/Meta-Llama-3.1-70B-Instruct` | 128K tokens | |
| Llama 3.1 8B | `meta-llama/Meta-Llama-3.1-8B-Instruct` | 128K tokens | Lightweight |

> **Note:** Llama API strings vary by provider. Above are HuggingFace-style IDs. Provider-specific mappings:
> - **Together AI:** `meta-llama/Llama-3.3-70B-Instruct-Turbo`
> - **Fireworks:** `accounts/fireworks/models/llama-v3p3-70b-instruct`
> - **Groq:** `llama-3.3-70b-versatile`
> - **AWS Bedrock:** `meta.llama3-1-70b-instruct-v1:0`

---

## Azure OpenAI

| Model | Deployment Name (typical) | API String | Notes |
|-------|--------------------------|-----------|-------|
| GPT-5.3 | `gpt-5.3` | `gpt-5.3` | Latest flagship |
| Codex | `codex` | `codex` | Autonomous coding agent |
| GPT-4.1 | `gpt-4.1` | `gpt-4.1` | Strong coding & instruction following |
| GPT-4o | `gpt-4o` | `gpt-4o` | Multimodal |
| GPT-4o mini | `gpt-4o-mini` | `gpt-4o-mini` | |
| o4-mini | `o4-mini` | `o4-mini` | Reasoning |
| o3-mini | `o3-mini` | `o3-mini` | Reasoning |

> **Note:** Azure uses **deployment names** (user-defined) rather than model IDs directly. The API string you pass is your deployment name, which maps to the underlying model version.

---

## Mistral

| Model | API String | Context Window | Notes |
|-------|-----------|----------------|-------|
| Mistral Large (25.01) | `mistral-large-latest` | 128K tokens | Flagship |
| Mistral Small (25.01) | `mistral-small-latest` | 32K tokens | Efficient |
| Codestral (25.01) | `codestral-latest` | 256K tokens | Code-specialized |
| Mistral Embed | `mistral-embed` | 8K tokens | Embeddings |
| Ministral 8B | `ministral-8b-latest` | 128K tokens | Edge/mobile |
| Ministral 3B | `ministral-3b-latest` | 128K tokens | Smallest |
| Pixtral Large | `pixtral-large-latest` | 128K tokens | Multimodal |

---

## Cohere

| Model | API String | Context Window | Notes |
|-------|-----------|----------------|-------|
| Command R+ (08-2024) | `command-r-plus-08-2024` | 128K tokens | Best RAG model |
| Command R+ | `command-r-plus` | 128K tokens | RAG-optimized |
| Command R (08-2024) | `command-r-08-2024` | 128K tokens | Balanced |
| Command R | `command-r` | 128K tokens | |
| Command | `command` | 4K tokens | Legacy |

### Cohere Embeddings

| Model | API String | Dimensions | Notes |
|-------|-----------|------------|-------|
| embed-v4.0 | `embed-v4.0` | 1024 | Latest, multimodal |
| embed-english-v3.0 | `embed-english-v3.0` | 1024 | English-only |
| embed-multilingual-v3.0 | `embed-multilingual-v3.0` | 1024 | 100+ languages |

---

## DeepSeek

| Model | API String | Context Window | Notes |
|-------|-----------|----------------|-------|
| DeepSeek-V3 | `deepseek-chat` | 64K tokens | General chat |
| DeepSeek-R1 | `deepseek-reasoner` | 64K tokens | Reasoning model |

---

## xAI (Grok)

| Model | API String | Context Window | Notes |
|-------|-----------|----------------|-------|
| Grok 3 | `grok-3` | 128K tokens | Flagship |
| Grok 3 mini | `grok-3-mini` | 128K tokens | Fast reasoning |
| Grok 2 | `grok-2-1212` | 128K tokens | |

---

## Amazon (Nova) — via Bedrock

| Model | API String (Bedrock Model ID) | Context Window | Notes |
|-------|------------------------------|----------------|-------|
| Nova Pro | `amazon.nova-pro-v1:0` | 300K tokens | Best quality |
| Nova Lite | `amazon.nova-lite-v1:0` | 300K tokens | Multimodal, fast |
| Nova Micro | `amazon.nova-micro-v1:0` | 128K tokens | Text-only, lowest cost |

---

*Last updated: February 2026*
