"""Generates a natural-language answer from hybrid retrieval results.

This is the final, previously-unbuilt step of the pipeline
(Hybrid Retrieval -> LLM -> Answer). The LLM's job is strictly limited
to phrasing - it is given only the facts hybrid_search() already
verified against the graph, and instructed not to add anything beyond
them. This preserves the project's core principle that the LLM never
invents graph structure (see README, Design Principles).
"""

import os

from groq import Groq

from retrieval.hybrid_search import EnrichedHit

MODEL = "openai/gpt-oss-20b"

_client: Groq | None = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY environment variable is not set.")
        _client = Groq(api_key=api_key)
    return _client


def _facts_to_text(hits: list[EnrichedHit]) -> str:
    """Flattens enriched hits into a plain fact list for the prompt."""
    lines = []
    seen = set()
    for hit in hits:
        for r in hit.all_relationships:
            key = (r["entity1"], r["relation"], r["entity2"], r["chunk_id"])
            if key in seen:
                continue
            seen.add(key)
            readable_relation = r["relation"].replace("_", " ")
            lines.append(f"- {r['entity1']} {readable_relation} {r['entity2']} (source: chunk {r['chunk_id']})")
    return "\n".join(lines) if lines else "(no relevant facts found)"


def generate_answer(question: str, hits: list[EnrichedHit]) -> str:
    """Turn retrieved graph facts into a grounded natural-language answer.

    Args:
        question: The user's original question.
        hits: Output of retrieval.hybrid_search.hybrid_search().

    Returns:
        A natural-language answer, or an honest "not found" message if
        no relevant facts were retrieved - the model is instructed not
        to guess beyond the provided facts.
    """
    facts = _facts_to_text(hits)

    prompt = (
    "You answer questions about a novel using ONLY the facts listed below. "
    "Each fact is a separate, isolated statement - facts are NOT connected "
    "to each other unless a single fact explicitly states the connection. "
    "Do not chain or combine two separate facts to infer something that "
    "isn't explicitly stated as one fact.\n\n"
    "Example of what NOT to do: if one fact says 'A is friend of B' and a "
    "separate fact says 'C is protector of D', do not conclude 'C is "
    "protector of A's friend' - B and D may not even be the same person "
    "unless a fact says so explicitly.\n\n"
    "If the exact fact (or chain) the question asks for is not explicitly "
    "present, say plainly that it cannot be determined from the retrieved "
    "facts, rather than guessing.\n\n"
    f"Facts:\n{facts}\n\n"
    f"Question: {question}\n\n"
    "Answer in 1-3 sentences:"
)

    client = _get_client()
    response = client.chat.completions.create(
    model=MODEL,
    messages=[{"role": "user", "content": prompt}],
    temperature=0.2,
    max_tokens=500,
    reasoning_effort="low",
)

    answer = response.choices[0].message.content
    if not answer or not answer.strip():
        # defensive: reasoning-style models can leave content empty under
        # token pressure - surface this clearly instead of silently
        # returning a blank string to the user
        raise RuntimeError(f"Model returned empty content. Full response: {response}")

    return answer.strip()
