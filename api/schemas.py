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
    query_direction_match: bool | None = None
    """Whether the query's detected direction matches this fact's
    stored direction - see retrieval.direction_detection. None means
    direction couldn't be determined; optional/defaulted for backward
    compatibility with any existing caller constructing SourceFact
    directly with only the original four fields."""


class ChainFact(BaseModel):
    """A graph-verified multi-hop path, given as citation provenance
    for answers that needed more than a single direct fact."""

    path: list[str]
    relations: list[str]
    directions: list[str]


class QueryResponse(BaseModel):
    answer: str
    book_id: str
    sources: list[SourceFact]
    chains: list[ChainFact] = Field(default_factory=list)


class BookInfo(BaseModel):
    book_id: str
    title: str
    num_nodes: int
    num_edges: int


class HealthResponse(BaseModel):
    status: str
    books_loaded: int
    vectors_indexed: int
