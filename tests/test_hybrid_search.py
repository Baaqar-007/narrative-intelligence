# tests/test_hybrid_integration.py
"""Integration tests across graph + embedding modules - specifically
targets the kind of bug that unit tests of either module alone can't
catch (see Week 3 Day 4 findings).
"""

import networkx as nx
import pandas as pd

from embedding.embed_relations import build_embedding_records
from graph.build_graph import build_book_graph
from temporal.trajectory import get_relationships_between


def test_embedded_entity_names_resolve_in_graph() -> None:
    """The core invariant: any entity name stored in embedding metadata
    must be a real node in the corresponding graph, so hybrid retrieval
    can actually look it up.
    """
    rows = pd.DataFrame([
        {
            "book_id": "106",
            "chunk_id": "10",
            "relations_parsed": [
                {"entity1": "Taug", "entity2": "Bolgani, the gorilla",
                 "entity1Type": "PER", "entity2Type": "PER", "relation": "enemy_of"}
            ],
        }
    ])

    graph, _ = build_book_graph(rows, book_id="106")
    records = build_embedding_records(rows)

    for record in records:
        assert record.entity1 in graph.nodes, (
            f"{record.entity1!r} from embedding metadata not found in graph nodes"
        )
        assert record.entity2 in graph.nodes, (
            f"{record.entity2!r} from embedding metadata not found in graph nodes"
        )

    # and confirm the actual downstream lookup works end-to-end
    relationships = get_relationships_between(graph, records[0].entity1, records[0].entity2)
    assert len(relationships) == 1
    assert relationships[0]["relation"] == "enemy_of"