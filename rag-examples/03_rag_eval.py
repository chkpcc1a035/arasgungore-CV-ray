"""
03_rag_eval.py
==============
A tiny "golden set" evaluator — the discipline that separates a real RAG
project from a vibes-driven one. This is what you'd cite in interview when
asked "how did you know your RAG actually worked?"

What it measures:
    - retrieval_hit@k : did the expected source appear in top-K retrievals?
    - answer_contains : does the LLM answer contain the expected substring?

Run:
    $env:ANTHROPIC_API_KEY="sk-ant-..."
    python 03_rag_eval.py
"""
from __future__ import annotations

import os
import sys

# Reuse pipeline from 02
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import numpy as np
from sentence_transformers import SentenceTransformer, CrossEncoder
from rank_bm25 import BM25Okapi
from anthropic import Anthropic

from importlib import import_module
hybrid = import_module("02_rag_hybrid")


# ----------------------------------------------------------------------------
# Golden set: hand-curated (question, expected_source, expected_substring)
# In a real project this lives in a versioned YAML/JSON, grows over time, and
# every prompt or retrieval change must pass it before deploy.
# ----------------------------------------------------------------------------
GOLDEN = [
    {
        "question": "What is the Hong Kong dollar pegged to?",
        "expected_source": "hkma_overview.md",
        "expected_substring": "US dollar",
    },
    {
        "question": "Which database does the eMPF platform use?",
        "expected_source": "empf_platform.md",
        "expected_substring": "Oracle",
    },
    {
        "question": "When did Fintech 2025 launch?",
        "expected_source": "hkma_overview.md",
        "expected_substring": "2021",
    },
    {
        "question": "Why is LangGraph well-suited for production agents?",
        "expected_source": "agentic_ai.md",
        "expected_substring": "stateful",
    },
    {
        "question": "What is the colour of the Hong Kong sky on a clear day?",  # out-of-scope
        "expected_source": None,
        "expected_substring": "don't have enough information",
    },
]


def run_pipeline(question, chunks, embed_model, chunk_vecs, bm25, reranker, client):
    q_vec = hybrid.embed_normalized(embed_model, [question])[0]
    dense_rank = np.argsort(-(chunk_vecs @ q_vec))[:10].tolist()
    bm25_rank = np.argsort(-bm25.get_scores(hybrid.tokenize(question)))[:10].tolist()
    fused = hybrid.reciprocal_rank_fusion([dense_rank, bm25_rank])[:10]
    candidates = [chunks[idx] for idx, _ in fused]
    reranked = hybrid.rerank(reranker, question, candidates, top_k=3)
    answer = hybrid.generate(client, hybrid.build_prompt(question, reranked))
    return reranked, answer


def main():
    docs_folder = os.path.join(HERE, "sample_docs")
    chunks = hybrid.load_and_chunk(docs_folder)
    embed_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    chunk_vecs = hybrid.embed_normalized(embed_model, [c.text for c in chunks])
    bm25 = BM25Okapi([hybrid.tokenize(c.text) for c in chunks])
    reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    client = Anthropic()

    results = []
    for case in GOLDEN:
        retrieved, answer = run_pipeline(
            case["question"], chunks, embed_model, chunk_vecs, bm25, reranker, client
        )
        sources = [c.source for c, _ in retrieved]
        hit = case["expected_source"] in sources if case["expected_source"] else True
        contains = case["expected_substring"].lower() in answer.lower()
        results.append({
            "q": case["question"],
            "hit@3": hit,
            "contains": contains,
            "sources": sources,
        })
        print(f"\n--- {case['question']}")
        print(f"    hit@3:    {hit}   (expected {case['expected_source']}, got {sources})")
        print(f"    contains: {contains}   (expected substring: {case['expected_substring']!r})")
        print(f"    answer:   {answer.strip()[:200]}...")

    hit_rate = sum(r["hit@3"] for r in results) / len(results)
    contain_rate = sum(r["contains"] for r in results) / len(results)
    print("\n" + "=" * 60)
    print(f"SUMMARY  hit@3 = {hit_rate:.0%}   answer_contains = {contain_rate:.0%}")
    print("=" * 60)


if __name__ == "__main__":
    main()
