"""
04_query_router.py
==================
How to decide whether a user query is LOCAL or GLOBAL — the routing
decision GraphRAG needs at query time. Vector storage is identical
for both; only the retrieval strategy changes.

Four strategies, increasing in sophistication:

    A. Heuristic rules         — keyword/shape patterns, <1ms
    B. Exemplar similarity     — cosine to labelled examples, ~5ms
    C. Score-distribution      — use the retrieval scores themselves
    D. LLM classifier          — one cheap LLM call, most accurate

Real systems combine them: heuristic short-circuit -> exemplar fallback
-> LLM tie-break, with the score distribution as a sanity check after
retrieval.

Run:
    $env:ANTHROPIC_API_KEY="sk-ant-..."
    python 04_query_router.py
"""
from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass

import numpy as np
from sentence_transformers import SentenceTransformer
from anthropic import Anthropic

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from importlib import import_module
hybrid = import_module("02_rag_hybrid")


QueryMode = str  # "local" | "global"


# ----------------------------------------------------------------------------
# A. Heuristic rules — cheapest, useful as a fast path / pre-filter
# ----------------------------------------------------------------------------
GLOBAL_HINTS = re.compile(
    r"\b(summari[sz]e|overall|themes?|compare|contrast|across|"
    r"main (ideas?|points?|topics?)|trend|overview|in general|"
    r"what are the|landscape|holistic)\b",
    re.IGNORECASE,
)
LOCAL_HINTS = re.compile(
    r"\b(what is|who is|when did|where is|which|how many|"
    r"define|definition of|value of)\b",
    re.IGNORECASE,
)


def classify_heuristic(query: str) -> tuple[QueryMode, float, str]:
    """Return (mode, confidence in [0,1], reason)."""
    g = bool(GLOBAL_HINTS.search(query))
    l = bool(LOCAL_HINTS.search(query))
    if g and not l:
        return "global", 0.8, "matched global keyword pattern"
    if l and not g:
        return "local", 0.8, "matched local question-shape pattern"
    # Short queries (< 6 words) with a proper noun lean local.
    if len(query.split()) < 8 and re.search(r"\b[A-Z]{2,}\b|\b[A-Z][a-z]+ [A-Z][a-z]+\b", query):
        return "local", 0.6, "short query with proper noun"
    return "local", 0.4, "no strong signal (default local)"


# ----------------------------------------------------------------------------
# B. Exemplar similarity — embed query, compare to labelled examples
# ----------------------------------------------------------------------------
@dataclass
class Exemplar:
    text: str
    label: QueryMode


EXEMPLARS: list[Exemplar] = [
    # local
    Exemplar("What database does the eMPF platform use?", "local"),
    Exemplar("When was the HKMA established?", "local"),
    Exemplar("Which model is used for embeddings?", "local"),
    Exemplar("What is the peg rate of HKD to USD?", "local"),
    # global
    Exemplar("Summarise the main themes of HKMA's strategy.", "global"),
    Exemplar("Compare the goals of Fintech 2025 with e-HKD.", "global"),
    Exemplar("What are the overall regulatory concerns around agentic AI?", "global"),
    Exemplar("Give an overview of the eMPF programme.", "global"),
]


def classify_exemplar(
    query: str,
    embed_model: SentenceTransformer,
    exemplar_vecs: np.ndarray,
) -> tuple[QueryMode, float, str]:
    q_vec = hybrid.embed_normalized(embed_model, [query])[0]
    sims = exemplar_vecs @ q_vec
    # Average similarity per class — robust to single-outlier exemplars.
    local_sims = [s for s, ex in zip(sims, EXEMPLARS) if ex.label == "local"]
    global_sims = [s for s, ex in zip(sims, EXEMPLARS) if ex.label == "global"]
    l_mean, g_mean = float(np.mean(local_sims)), float(np.mean(global_sims))
    if g_mean > l_mean:
        return "global", g_mean - l_mean, f"exemplar avg local={l_mean:.3f} global={g_mean:.3f}"
    return "local", l_mean - g_mean, f"exemplar avg local={l_mean:.3f} global={g_mean:.3f}"


# ----------------------------------------------------------------------------
# C. Score-distribution after cheap dense retrieval
# ----------------------------------------------------------------------------
# Intuition: a local question has ONE good answer chunk -> a sharp drop after
# top-1. A global question's relevance is spread across many chunks -> flat
# distribution. Measure with the gap between top-1 and top-5 mean.
def classify_score_distribution(
    query: str,
    embed_model: SentenceTransformer,
    chunk_vecs: np.ndarray,
) -> tuple[QueryMode, float, str]:
    q_vec = hybrid.embed_normalized(embed_model, [query])[0]
    scores = chunk_vecs @ q_vec
    top = np.sort(scores)[::-1][:5]
    gap = float(top[0] - top[1:].mean())  # sharpness
    # Tunable threshold — calibrate on your golden set.
    if gap > 0.06:
        return "local", gap, f"sharp top-1 (gap={gap:.3f}) -> single relevant chunk"
    return "global", -gap, f"flat distribution (gap={gap:.3f}) -> answer is spread"


# ----------------------------------------------------------------------------
# D. LLM classifier — most accurate, ~200ms, ~$0.0001 per call with Haiku
# ----------------------------------------------------------------------------
ROUTER_PROMPT = """Classify the user's question as either LOCAL or GLOBAL.

LOCAL  = answerable from a single specific fact or passage
         (e.g. "what is X", "when did Y", "which database does Z use").
GLOBAL = requires aggregating or summarising across many documents
         (e.g. "summarise themes", "compare strategies", "give an overview").

Respond with exactly one word: LOCAL or GLOBAL.

Question: {q}
"""


def classify_llm(client: Anthropic, query: str) -> tuple[QueryMode, float, str]:
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4,
        messages=[{"role": "user", "content": ROUTER_PROMPT.format(q=query)}],
    )
    label = resp.content[0].text.strip().upper()
    mode = "global" if "GLOBAL" in label else "local"
    return mode, 0.95, f"LLM said {label!r}"


# ----------------------------------------------------------------------------
# Stacked router — what you'd actually deploy
# ----------------------------------------------------------------------------
def route(
    query: str,
    embed_model: SentenceTransformer,
    exemplar_vecs: np.ndarray,
    chunk_vecs: np.ndarray,
    client: Anthropic,
) -> dict:
    """Stacked routing: cheap signals first, LLM only when uncertain."""
    h_mode, h_conf, h_reason = classify_heuristic(query)
    if h_conf >= 0.8:
        decision = h_mode
        path = "heuristic"
    else:
        e_mode, e_conf, e_reason = classify_exemplar(query, embed_model, exemplar_vecs)
        if e_conf >= 0.05:
            decision = e_mode
            path = "exemplar"
        else:
            l_mode, _, _ = classify_llm(client, query)
            decision = l_mode
            path = "llm"

    # Score-distribution as an after-the-fact sanity check / alarm signal.
    s_mode, _, s_reason = classify_score_distribution(query, embed_model, chunk_vecs)
    disagreement = s_mode != decision

    return {
        "decision": decision,
        "path": path,
        "score_signal": s_mode,
        "score_disagrees": disagreement,
        "reasons": {
            "heuristic": h_reason,
            "score_distribution": s_reason,
        },
    }


# ----------------------------------------------------------------------------
# Demo
# ----------------------------------------------------------------------------
def main():
    docs_folder = os.path.join(HERE, "sample_docs")
    chunks = hybrid.load_and_chunk(docs_folder)

    embed_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    chunk_vecs = hybrid.embed_normalized(embed_model, [c.text for c in chunks])
    exemplar_vecs = hybrid.embed_normalized(embed_model, [e.text for e in EXEMPLARS])
    client = Anthropic()

    test_queries = [
        "What database does the eMPF platform use?",
        "Summarise the overall themes of HKMA's fintech direction.",
        "When did Fintech 2025 launch?",
        "Compare local vs global retrieval in GraphRAG.",
        "RHSSO",  # ambiguous fragment
        "Tell me about agentic AI considerations for regulators.",
    ]

    for q in test_queries:
        r = route(q, embed_model, exemplar_vecs, chunk_vecs, client)
        flag = "  [!] score channel disagrees" if r["score_disagrees"] else ""
        print(f"\nQ: {q}")
        print(f"  decision: {r['decision'].upper():6} via {r['path']}{flag}")
        print(f"  heuristic: {r['reasons']['heuristic']}")
        print(f"  score-dist: {r['reasons']['score_distribution']}")


if __name__ == "__main__":
    main()
