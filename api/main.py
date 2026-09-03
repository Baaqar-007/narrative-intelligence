"""NIE API - FastAPI application.

Loads the pre-built pipeline (graphs, vector store, embedding model)
once at startup, not per-request. Run locally with:
    uvicorn api.main:app --reload
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from api.schemas import BookInfo, HealthResponse, QueryRequest, QueryResponse, SourceFact
from embedding.embed_relations import load_embedding_model
from embedding.vector_store import get_collection
from graph.corpus import load_corpus
from retrieval.answer_generation import generate_answer
from retrieval.hybrid_search import hybrid_search

DATA_DIR = Path("data")

state: dict = {}


import pandas as pd

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Loading pipeline...")
    state["corpus"] = load_corpus(DATA_DIR / "graphs" / "corpus.pkl")
    state["collection"] = get_collection(path=str(DATA_DIR / "chroma"))
    state["model"] = load_embedding_model()

    meta = pd.read_parquet(DATA_DIR / "arf_chunks_parsed.parquet", columns=["book_id", "title"])
    state["titles"] = meta.drop_duplicates("book_id").set_index("book_id")["title"].to_dict()

    print(f"Ready: {len(state['corpus'])} books, {state['collection'].count():,} vectors.")
    yield
    state.clear()


app = FastAPI(title="Narrative Intelligence Engine", lifespan=lifespan)


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(
        status="ok",
        books_loaded=len(state["corpus"]),
        vectors_indexed=state["collection"].count(),
    )


@app.get("/books", response_model=list[BookInfo])
def list_books():
    books = [
        BookInfo(
            book_id=book_id,
            title=state["titles"].get(book_id, book_id),
            num_nodes=graph.number_of_nodes(),
            num_edges=graph.number_of_edges(),
        )
        for book_id, graph in state["corpus"].items()
        if graph.number_of_edges() > 0
    ]
    return sorted(books, key=lambda b: b.title)


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest):
    if req.book_id not in state["corpus"]:
        raise HTTPException(status_code=404, detail=f"Unknown book_id: {req.book_id}")

    hits = hybrid_search(
        state["collection"], req.question, state["model"], state["corpus"],
        n_results=5, book_id=req.book_id,
    )

    sources = [
        SourceFact(entity1=r["entity1"], entity2=r["entity2"], relation=r["relation"], chunk_id=r["chunk_id"])
        for hit in hits for r in hit.all_relationships
    ]
    # de-duplicate while preserving order
    seen = set()
    unique_sources = []
    for s in sources:
        key = (s.entity1, s.entity2, s.relation, s.chunk_id)
        if key not in seen:
            seen.add(key)
            unique_sources.append(s)

    answer = generate_answer(req.question, hits)

    return QueryResponse(answer=answer, book_id=req.book_id, sources=unique_sources)


app.mount("/static", StaticFiles(directory="api/static"), name="static")


@app.get("/")
def root():
    return FileResponse("api/static/index.html")
