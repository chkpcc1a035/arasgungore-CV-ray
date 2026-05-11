"""
05_rag_pgvector.py
==================
The same RAG pipeline as 01, but using Postgres + pgvector instead of
an in-memory numpy matrix. This is what a "real" RAG store looks like
when you don't want to run a separate vector DB.

What you'll see:
  - HNSW index for fast approximate nearest neighbour
  - Metadata stored alongside vectors (source, header) — filterable in SQL
  - Cosine distance via the <=> operator
  - Persistence — re-runs don't re-embed

Prereqs (one-time):

    # Start a local Postgres with pgvector pre-installed
    docker run -d --name pgvector \
        -e POSTGRES_PASSWORD=ragdemo \
        -p 5432:5432 \
        pgvector/pgvector:pg16

    pip install psycopg[binary] pgvector

Run:
    $env:ANTHROPIC_API_KEY="sk-ant-..."
    $env:PG_DSN="postgresql://postgres:ragdemo@localhost:5432/postgres"
    python 05_rag_pgvector.py "Which database powers the eMPF platform?"
"""
from __future__ import annotations

import os
import sys

import numpy as np
import psycopg
from pgvector.psycopg import register_vector
from sentence_transformers import SentenceTransformer
from anthropic import Anthropic

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from importlib import import_module
hybrid = import_module("02_rag_hybrid")  # reuse chunking, prompt, generate

EMBED_DIM = 384  # all-MiniLM-L6-v2


# ----------------------------------------------------------------------------
# Schema: one table, vector column + JSONB metadata. HNSW index for ANN.
# ----------------------------------------------------------------------------
SCHEMA_SQL = f"""
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS rag_chunks (
    id           BIGSERIAL PRIMARY KEY,
    source       TEXT      NOT NULL,
    header       TEXT      NOT NULL,
    text         TEXT      NOT NULL,
    embedding    vector({EMBED_DIM}) NOT NULL,
    model        TEXT      NOT NULL,           -- track embedding model version
    created_at   TIMESTAMPTZ DEFAULT now()
);

-- HNSW index for cosine distance. Build once after bulk insert for speed.
CREATE INDEX IF NOT EXISTS rag_chunks_embedding_hnsw
    ON rag_chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Useful for source-filtered queries (per-tenant, per-doc).
CREATE INDEX IF NOT EXISTS rag_chunks_source_idx ON rag_chunks (source);
"""


def connect() -> psycopg.Connection:
    dsn = os.environ.get("PG_DSN", "postgresql://postgres:ragdemo@localhost:5432/postgres")
    conn = psycopg.connect(dsn, autocommit=True)
    register_vector(conn)
    return conn


def ensure_schema(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL)


# ----------------------------------------------------------------------------
# Ingest — only embed chunks we haven't seen before. Persistence wins.
# ----------------------------------------------------------------------------
def ingest_if_empty(conn: psycopg.Connection, embed_model: SentenceTransformer) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM rag_chunks")
        existing = cur.fetchone()[0]
    if existing > 0:
        print(f"      {existing} chunks already in DB, skipping ingest")
        return existing

    chunks = hybrid.load_and_chunk(os.path.join(HERE, "sample_docs"))
    vecs = hybrid.embed_normalized(embed_model, [c.text for c in chunks])

    model_id = "all-MiniLM-L6-v2@v1"  # version your embedding model!
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO rag_chunks (source, header, text, embedding, model) "
            "VALUES (%s, %s, %s, %s, %s)",
            [
                (c.source, c.header, c.text, vecs[i], model_id)
                for i, c in enumerate(chunks)
            ],
        )
    print(f"      ingested {len(chunks)} chunks")
    return len(chunks)


# ----------------------------------------------------------------------------
# Retrieve — cosine distance is the <=> operator in pgvector.
# Smaller = closer. We also demonstrate a metadata filter (source IN ...).
# ----------------------------------------------------------------------------
RETRIEVE_SQL = """
SELECT id, source, header, text, 1 - (embedding <=> %s::vector) AS cosine_sim
FROM rag_chunks
WHERE (%s::text[] IS NULL OR source = ANY(%s::text[]))
ORDER BY embedding <=> %s::vector
LIMIT %s
"""


def retrieve(
    conn: psycopg.Connection,
    query_vec: np.ndarray,
    top_k: int = 3,
    source_filter: list[str] | None = None,
) -> list[tuple[hybrid.Chunk, float]]:
    with conn.cursor() as cur:
        cur.execute(RETRIEVE_SQL, (query_vec, source_filter, source_filter, query_vec, top_k))
        rows = cur.fetchall()
    return [
        (
            hybrid.Chunk(text=r[3], source=r[1], header=r[2], chunk_id=r[0]),
            float(r[4]),
        )
        for r in rows
    ]


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
def main():
    question = " ".join(sys.argv[1:]) or "Which database powers the eMPF platform?"
    print(f"\n>>> Question: {question}\n")

    print("[1] Connect + ensure schema")
    conn = connect()
    ensure_schema(conn)

    print("[2] Embed model + ingest-if-empty")
    embed_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    ingest_if_empty(conn, embed_model)

    print("[3] Embed query + retrieve via pgvector")
    q_vec = hybrid.embed_normalized(embed_model, [question])[0]
    retrieved = retrieve(conn, q_vec, top_k=3)
    for c, sim in retrieved:
        print(f"    sim={sim:.3f} id={c.chunk_id} source={c.source} section={c.header!r}")

    print("[4] Generate")
    client = Anthropic()
    answer = hybrid.generate(client, hybrid.build_prompt(question, retrieved))

    print("\n" + "=" * 60)
    print("ANSWER")
    print("=" * 60)
    print(answer)
    print()


if __name__ == "__main__":
    main()
