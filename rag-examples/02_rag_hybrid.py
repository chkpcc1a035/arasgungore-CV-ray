"""
02_rag_hybrid.py
================
Production-shaped RAG with the three upgrades that move quality the most:

    1. Hybrid retrieval   — dense embeddings + BM25 keyword search, fused
    2. Cross-encoder rerank — re-score top candidates with a smarter model
    3. Citations + refuse-to-answer behaviour

Run:
    pip install -r requirements.txt
    $env:ANTHROPIC_API_KEY="sk-ant-..."
    python 02_rag_hybrid.py "Which technologies power the eMPF platform?"

Why this matters in interview:
  - Pure cosine often returns plausible-but-wrong chunks. BM25 catches the
    cases where the exact term matters ("Oracle", "RHSSO", "e-HKD").
  - Cross-encoder reranking is a separate model that scores (query, chunk)
    PAIRS — much more accurate than bi-encoder cosine, but too slow to run
    over the whole corpus. So: retrieve wide with cheap methods, rerank narrow.
"""
from __future__ import annotations

import os
import sys
import glob
from dataclasses import dataclass

import numpy as np
from sentence_transformers import SentenceTransformer, CrossEncoder
from rank_bm25 import BM25Okapi
from anthropic import Anthropic


# ----------------------------------------------------------------------------
# Reuse the same chunking from 01 — copied inline so this file is standalone.
# ----------------------------------------------------------------------------
@dataclass
class Chunk:
    text: str
    source: str
    header: str
    chunk_id: int


def load_and_chunk(folder: str, target_words: int = 120) -> list[Chunk]:
    chunks: list[Chunk] = []
    cid = 0
    for path in glob.glob(os.path.join(folder, "*.md")):
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        source = os.path.basename(path)
        current_header = "(intro)"
        buffer: list[str] = []
        word_count = 0

        def flush():
            nonlocal buffer, word_count, cid
            if buffer:
                chunks.append(Chunk(
                    text=f"[{current_header}] " + " ".join(buffer).strip(),
                    source=source,
                    header=current_header,
                    chunk_id=cid,
                ))
                cid += 1
                buffer = []
                word_count = 0

        for line in text.splitlines():
            if line.startswith("#"):
                flush()
                current_header = line.lstrip("#").strip()
                continue
            if not line.strip():
                if word_count >= target_words:
                    flush()
                continue
            buffer.append(line.strip())
            word_count += len(line.split())
        flush()
    return chunks


# ----------------------------------------------------------------------------
# Hybrid retrieval
# ----------------------------------------------------------------------------
def tokenize(text: str) -> list[str]:
    """Cheap tokeniser for BM25 — lowercased alphanumerics."""
    return [t for t in "".join(c.lower() if c.isalnum() else " " for c in text).split() if t]


def embed_normalized(model: SentenceTransformer, texts: list[str]) -> np.ndarray:
    v = model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
    return v / np.clip(np.linalg.norm(v, axis=1, keepdims=True), 1e-12, None)


def reciprocal_rank_fusion(
    ranked_lists: list[list[int]],
    k: int = 60,
) -> list[tuple[int, float]]:
    """Combine ranked lists with RRF — robust, no score-scale calibration needed.

    Each chunk gets score = sum over lists of 1 / (k + rank_in_list).
    Items not present in a list contribute 0 for that list.
    """
    scores: dict[int, float] = {}
    for ranked in ranked_lists:
        for rank, idx in enumerate(ranked):
            scores[idx] = scores.get(idx, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda kv: -kv[1])


# ----------------------------------------------------------------------------
# Reranking
# ----------------------------------------------------------------------------
# Bi-encoders (the embedding model above) embed query and document separately.
# Cross-encoders take (query, document) AS A PAIR and output a relevance score.
# Slower but much more accurate. Standard pattern: retrieve top-30 cheaply,
# rerank to top-3 with a cross-encoder.
RERANKER_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"


def rerank(
    reranker: CrossEncoder,
    query: str,
    candidates: list[Chunk],
    top_k: int = 3,
) -> list[tuple[Chunk, float]]:
    pairs = [(query, c.text) for c in candidates]
    scores = reranker.predict(pairs, show_progress_bar=False)
    ranked = sorted(zip(candidates, scores), key=lambda cs: -cs[1])
    return [(c, float(s)) for c, s in ranked[:top_k]]


# ----------------------------------------------------------------------------
# Prompt — note the refuse-to-answer clause
# ----------------------------------------------------------------------------
PROMPT_TEMPLATE = """You are a careful research assistant.

Answer the user's question using ONLY the numbered context blocks below.
Rules:
  - If the answer is not fully supported by the context, reply exactly:
    "I don't have enough information in the provided context to answer."
  - Cite chunk_id(s) you used in square brackets, e.g. [3].
  - Do not invent facts, sources, or chunk_ids.

--- CONTEXT ---
{context}
--- END CONTEXT ---

Question: {question}
"""


def build_prompt(question: str, retrieved: list[tuple[Chunk, float]]) -> str:
    blocks = [
        f"[chunk_id={c.chunk_id}] (source={c.source}, section={c.header})\n{c.text}"
        for c, _ in retrieved
    ]
    return PROMPT_TEMPLATE.format(context="\n\n".join(blocks), question=question)


def generate(client: Anthropic, prompt: str) -> str:
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
def main():
    question = " ".join(sys.argv[1:]) or "Which technologies power the eMPF platform?"
    here = os.path.dirname(os.path.abspath(__file__))
    docs_folder = os.path.join(here, "sample_docs")

    print(f"\n>>> Question: {question}\n")

    print("[1] Load + chunk")
    chunks = load_and_chunk(docs_folder)
    print(f"    {len(chunks)} chunks")

    print("[2] Build dense + sparse indexes")
    embed_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    chunk_vecs = embed_normalized(embed_model, [c.text for c in chunks])
    bm25 = BM25Okapi([tokenize(c.text) for c in chunks])

    print("[3] Retrieve wide (top-10 from each channel)")
    q_vec = embed_normalized(embed_model, [question])[0]
    dense_scores = chunk_vecs @ q_vec
    dense_rank = np.argsort(-dense_scores)[:10].tolist()

    bm25_scores = bm25.get_scores(tokenize(question))
    bm25_rank = np.argsort(-bm25_scores)[:10].tolist()

    print(f"    dense top-3: {dense_rank[:3]}")
    print(f"    bm25  top-3: {bm25_rank[:3]}")

    print("[4] Fuse with Reciprocal Rank Fusion -> top-10 candidates")
    fused = reciprocal_rank_fusion([dense_rank, bm25_rank])[:10]
    candidates = [chunks[idx] for idx, _ in fused]

    print("[5] Rerank with cross-encoder -> top-3")
    reranker = CrossEncoder(RERANKER_NAME)
    reranked = rerank(reranker, question, candidates, top_k=3)
    for c, s in reranked:
        print(f"    score={s:+.3f} id={c.chunk_id} "
              f"source={c.source} section={c.header!r}")

    print("[6] Generate")
    client = Anthropic()
    answer = generate(client, build_prompt(question, reranked))

    print("\n" + "=" * 60)
    print("ANSWER")
    print("=" * 60)
    print(answer)
    print()


if __name__ == "__main__":
    main()
