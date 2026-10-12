# Deployment

How the system is packaged and served, and the reasoning trail behind the
hosting choice. The LLM step and API design are described in
[`architecture.md`](architecture.md#answer-generation).

## Contents of a deployment

| Component | Notes |
|---|---|
| FastAPI app (`api/`) | `GET /health`, `GET /books`, `POST /query` |
| Static frontend | `api/static/index.html`, served at `/` |
| Corpus graphs | Built offline by `scripts/build_pipeline.py` |
| Vector store | ChromaDB persistent collection `arf_relations` |
| Resolution maps | `corpus_resolution.pkl`, loaded at startup if present |
| LLM | Groq, `openai/gpt-oss-20b`, via the `GROQ_API_KEY` environment variable |

`data/` and `model_cache/` are git-ignored and fully reproducible via
`scripts/build_pipeline.py` plus the documented model-cache step.
`requirements.txt` is slim and deploy-only; `requirements-dev.txt` is the full
local environment.

The serving image never needs offline tooling. Graph, embeddings and the
resolution map are built ahead of time and only *read* by the API. The same
split keeps heavy research dependencies (such as `fastcoref`, which conflicts
with the current `transformers` version; see
[`v2-entity-resolution-findings.md`](v2-entity-resolution-findings.md)) out of
the serving environment, in a separate virtual environment.

## API behavior

- `POST /query` takes a `book_id` and a question and returns an answer plus
  cited sources, including `chunk_id` provenance for each fact and the chain
  facts (`ChainFact`, including its `answer` field).
- `api/main.py` loads `corpus_resolution.pkl` at startup and falls back
  gracefully if it is absent. A `USE_RESOLUTION` toggle was proposed as a
  stop-gap while the resolution layer's yardstick regression is open; whether it
  is applied is unconfirmed.
- Hop depth is estimated dynamically from the question
  (`estimate_hop_depth`). A real off-by-one in hop-budget compensation was caught
  only by testing through the actual API endpoint with a dynamically estimated
  depth, not with a hand-picked test value.

## Running the demo

```bash
docker build -t nie-api:local .
docker run -p 7860:7860 -e GROQ_API_KEY=your_key nie-api:local
# in a second terminal:
cloudflared tunnel --url http://localhost:7860
```

The container and tunnel are started only when the project is being shown and
stopped afterwards. Cloudflare Quick Tunnels generate a fresh public URL each
time, so the address is ephemeral. A named tunnel with a domain would give a
permanent link if one is ever needed.

## Hosting decision: the path taken, including dead ends

Most of the effort here went into verifying platform claims rather than writing
code. The observations below were made during the v1 build and are
time-sensitive; verify current terms before relying on them.

| # | Option | Finding | Outcome |
|---|---|---|---|
| 1 | Hugging Face Spaces (the original plan) | Mid-build, the Docker and Gradio SDKs were found locked behind a paid plan for new Spaces, and free accounts were restricted to a GPU-burst tier (ZeroGPU), unsuited to an always-on CPU-only service | Ruled out |
| 2 | Koyeb | Free, no card required, but a true swap-disabled memory test showed the stack does not fit in its 512 MB instance | Ruled out by a local test before attempting a real deploy |
| 3 | Modal | No card required (OAuth-only signup) and architecturally a good fit (usage-metered), but the free credit granted at signup was far smaller than several independent articles described, too small for meaningful uptime | Ruled out |
| 4 | **Self-hosted Docker plus Cloudflare Tunnel, on demand** | Zero cost, no card, no platform dependency, and no background resource cost between demos (the deciding factor over leaving it always on) | **Chosen** |

Trade-off accepted: the public URL is ephemeral, which suits a demo shown live.

## Memory footprint

Memory is driven mainly by PyTorch, which `sentence-transformers` pulls in as its
default backend, rather than by the embedding model or the vector data. An ONNX
Runtime backend would likely shrink it substantially and reopen tighter-memory
free hosting options. It was not done: it was unnecessary once self-hosting was
chosen, and reshaping the runtime would not carry over cleanly to v2.

## Planned hosted demo

A hosted v2 demo with usage limits (to avoid exhausting a free tier) is intended
only once v2 meets its quality bar, and would cover a single curated
public-domain book rather than arbitrary uploads. See
[`roadmap.md`](roadmap.md). Arbitrary-book support would run as a self-hosted or
cloned-repo capability, not in a hosted demo.
