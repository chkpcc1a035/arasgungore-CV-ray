# RAG Examples — Learning Path

Three scripts, increasing in realism. Read in order, then run each.

| # | File | What it demonstrates |
|---|---|---|
| 1 | `01_rag_minimal.py` | End-to-end RAG with numpy cosine similarity — no vector DB. See every step. |
| 2 | `02_rag_hybrid.py` | Hybrid retrieval (dense + BM25), Reciprocal Rank Fusion, cross-encoder rerank. |
| 3 | `03_rag_eval.py`   | Golden-set evaluation — the discipline that makes RAG honest. |
| 4 | `04_query_router.py` | Classify a query as LOCAL vs GLOBAL — the routing decision GraphRAG needs. |
| 5 | `05_rag_pgvector.py` | Same pipeline as 01, but using Postgres + pgvector — persistent, indexable, filterable in SQL. |

## Setup (Windows / PowerShell)

```powershell
cd rag-examples
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:ANTHROPIC_API_KEY = "sk-ant-..."   # your key
```

## Run

```powershell
python 01_rag_minimal.py "What is the e-HKD pilot?"
python 02_rag_hybrid.py  "Which technologies power the eMPF platform?"
python 03_rag_eval.py
```

First run will download ~80MB for the embedding model and ~80MB for the
cross-encoder reranker — both cached after that.

## What to study in each file

**`01_rag_minimal.py`** — the mental model:
- Step 2 (`chunk_markdown`): how chunking decisions shape retrieval quality.
- Step 3 (`embed_texts`): why we L2-normalise (so cosine == dot product).
- Step 4 (`retrieve`): cosine similarity is literally `matrix @ vector`.
- Step 5 (`PROMPT_TEMPLATE`): the prompt is the contract — citations, refusal.

**`02_rag_hybrid.py`** — why production RAG looks different:
- BM25 catches terms cosine misses ("Oracle", "RHSSO" — proper nouns).
- RRF fuses ranked lists without fragile score-scale calibration.
- Cross-encoder reranks the top-10 down to top-3 with much higher precision.
- Refuse-to-answer clause prevents hallucination on out-of-scope questions.

**`03_rag_eval.py`** — how you'd actually defend this in interview:
- Golden questions with expected sources + expected substrings.
- The last case is *intentionally out-of-scope* — passes only if the LLM refuses.
- In a real CI: this script's exit code gates deploy.

## Common pitfalls you'll hit while playing with this

1. **Bad chunking destroys recall.** Try setting `target_words=400` in
   `chunk_markdown` and re-run eval — recall drops because chunks contain
   too many topics.
2. **Cosine alone misses specific terms.** Ask `01_rag_minimal.py` about
   "RHSSO" — the minimal pipeline may miss it; `02_rag_hybrid.py` finds it
   because BM25 weights rare tokens.
3. **The LLM lies about citations** when not constrained. The prompt in
   `02_rag_hybrid.py` explicitly forbids inventing chunk_ids.
4. **Embedding model upgrades silently break things.** If you change
   `EMBED_MODEL_NAME`, you MUST re-embed everything — never mix.

## Where this stops and a real system begins

Things deliberately left out for clarity:
- A real vector DB (Qdrant / Weaviate) — needed once corpus > ~10k chunks.
- Persistence — these scripts re-embed on every run.
- Streaming — production should stream tokens to the front-end.
- Query rewriting (HyDE, multi-query) — adds quality at the cost of latency.
- Observability — OpenTelemetry spans around retrieve, rerank, generate.
- Caching — semantic cache at the question level cuts cost dramatically.

Once you've internalised these three files, those upgrades are mechanical.
