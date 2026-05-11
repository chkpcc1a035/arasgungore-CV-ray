"""
01_rag_minimal.py
=================
A minimal end-to-end RAG pipeline in ~150 lines, with no vector DB —
just numpy for cosine similarity, so you can SEE every step.

Pipeline:
    docs -> chunk -> embed -> store (numpy array)
    query -> embed -> cosine sim -> top-K chunks -> stuff into prompt -> LLM

Run:
    pip install -r requirements.txt
    export ANTHROPIC_API_KEY=sk-ant-...     # PowerShell: $env:ANTHROPIC_API_KEY="sk-ant-..."
    python 01_rag_minimal.py "What is the e-HKD pilot?"
"""
from __future__ import annotations

import os
import sys
import glob
import re
from dataclasses import dataclass

import numpy as np
from sentence_transformers import SentenceTransformer
from anthropic import Anthropic


# ----------------------------------------------------------------------------
# Step 1: load documents from disk
# ----------------------------------------------------------------------------
def load_docs(folder: str) -> list[dict]:
    """Return a list of {source, text} dicts — one per file."""
    docs = []
    for path in glob.glob(os.path.join(folder, "*.md")):
        with open(path, "r", encoding="utf-8") as f:
            docs.append({"source": os.path.basename(path), "text": f.read()})
    return docs


# ----------------------------------------------------------------------------
# Step 2: chunk documents
# ----------------------------------------------------------------------------
# Why chunking matters: embedding models have a max input length, and you also
# want to retrieve passages small enough to be specific but big enough to be
# self-contained. A *header-aware* splitter keeps section context attached.
@dataclass
class Chunk:
    text: str           # what gets embedded + shown to the LLM
    source: str         # original filename, for citation
    header: str         # nearest preceding markdown header, for context
    chunk_id: int       # unique id, used in citations


def chunk_markdown(docs: list[dict], target_words: int = 120) -> list[Chunk]:
    """Header-aware splitter: respects markdown headings, splits by paragraph."""
    chunks: list[Chunk] = []
    cid = 0
    for doc in docs:
        current_header = "(intro)"
        buffer: list[str] = []
        word_count = 0

        def flush():
            nonlocal buffer, word_count, cid
            if buffer:
                chunks.append(Chunk(
                    text=f"[{current_header}] " + " ".join(buffer).strip(),
                    source=doc["source"],
                    header=current_header,
                    chunk_id=cid,
                ))
                cid += 1
                buffer = []
                word_count = 0

        for line in doc["text"].splitlines():
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
# Step 3: embed chunks
# ----------------------------------------------------------------------------
# An embedding model maps text -> a fixed-length vector. Semantically similar
# text ends up close in vector space. We use a small open-source model so this
# runs locally with no API key needed for embeddings.
EMBED_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"  # 384-dim, ~80MB


def embed_texts(model: SentenceTransformer, texts: list[str]) -> np.ndarray:
    """Return an (N, D) matrix of L2-normalised embeddings."""
    vectors = model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
    # Normalise so cosine similarity == dot product (cheaper).
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.clip(norms, 1e-12, None)


# ----------------------------------------------------------------------------
# Step 4: retrieve — pure numpy cosine similarity
# ----------------------------------------------------------------------------
def retrieve(
    query_vec: np.ndarray,        # shape (D,)
    chunk_vecs: np.ndarray,       # shape (N, D)
    chunks: list[Chunk],
    top_k: int = 3,
) -> list[tuple[Chunk, float]]:
    """Return top-K chunks ranked by cosine similarity, with scores."""
    scores = chunk_vecs @ query_vec                        # (N,) dot products
    top_idx = np.argsort(-scores)[:top_k]                  # descending
    return [(chunks[i], float(scores[i])) for i in top_idx]


# ----------------------------------------------------------------------------
# Step 5: assemble the prompt
# ----------------------------------------------------------------------------
PROMPT_TEMPLATE = """You are a helpful assistant. Answer the user's question
using ONLY the context below. If the answer is not in the context, say so.
Cite the chunk_id you used in square brackets, e.g. [3].

--- CONTEXT ---
{context}
--- END CONTEXT ---

Question: {question}
"""


def build_prompt(question: str, retrieved: list[tuple[Chunk, float]]) -> str:
    context_blocks = []
    for chunk, score in retrieved:
        context_blocks.append(
            f"[chunk_id={chunk.chunk_id}] (source={chunk.source}, "
            f"section={chunk.header}, score={score:.3f})\n{chunk.text}"
        )
    return PROMPT_TEMPLATE.format(
        context="\n\n".join(context_blocks),
        question=question,
    )


# ----------------------------------------------------------------------------
# Step 6: generate
# ----------------------------------------------------------------------------
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
    question = " ".join(sys.argv[1:]) or "What is the e-HKD pilot?"
    here = os.path.dirname(os.path.abspath(__file__))
    docs_folder = os.path.join(here, "sample_docs")

    print(f"\n>>> Question: {question}\n")

    print("[1/6] Loading docs...")
    docs = load_docs(docs_folder)
    print(f"      {len(docs)} documents loaded")

    print("[2/6] Chunking...")
    chunks = chunk_markdown(docs)
    print(f"      {len(chunks)} chunks produced")

    print("[3/6] Loading embedding model + embedding chunks...")
    embed_model = SentenceTransformer(EMBED_MODEL_NAME)
    chunk_vecs = embed_texts(embed_model, [c.text for c in chunks])
    print(f"      chunk matrix shape: {chunk_vecs.shape}")

    print("[4/6] Embedding query + retrieving top-3...")
    query_vec = embed_texts(embed_model, [question])[0]
    retrieved = retrieve(query_vec, chunk_vecs, chunks, top_k=3)
    for chunk, score in retrieved:
        print(f"      score={score:.3f} chunk_id={chunk.chunk_id} "
              f"source={chunk.source} section={chunk.header!r}")

    print("[5/6] Building prompt...")
    prompt = build_prompt(question, retrieved)

    print("[6/6] Calling LLM...\n")
    client = Anthropic()  # reads ANTHROPIC_API_KEY from env
    answer = generate(client, prompt)

    print("=" * 60)
    print("ANSWER")
    print("=" * 60)
    print(answer)
    print()


if __name__ == "__main__":
    main()
