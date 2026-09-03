"""Request/response schemas for the NIE API."""

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    book_id: str = Field(..., description="Which book to query, e.g. '106'")
    question: str = Field(..., min_length=1, max_length=500)


class SourceFact(BaseModel):
    """One graph-verified fact backing the answer, with full provenance."""

    entity1: str
    entity2: str
    relation: str
    chunk_id: int


class QueryResponse(BaseModel):
    answer: str
    book_id: str
    sources: list[SourceFact]


class BookInfo(BaseModel):
    book_id: str
    title: str
    num_nodes: int
    num_edges: int


class HealthResponse(BaseModel):
    status: str
    books_loaded: int
    vectors_indexed: int
