"""Generates a natural-language answer from hybrid retrieval results.

This is the final step of the pipeline (Hybrid Retrieval -> LLM ->
Answer). The LLM's job is strictly limited to phrasing - it is given
only facts already graph-verified upstream, and instructed not to add
anything beyond them.

WEEK 7 UPDATE: this previously rendered only hit.all_relationships,
silently ignoring hit.chains and the query_direction_match annotation
entirely - meaning neither of Week 7's actual features (multi-hop
chains, direction-mismatch flagging) reached the LLM at all, despite
being correctly computed upstream. Fixed here. Also required updating
the prompt's "never chain facts" instruction, which was correct for
the original single-hop-only pipeline but would have caused the model
to either ignore chains entirely or misapply the instruction to them -
chains are graph-verified paths, not something the model is combining
on its own, and the prompt now says so explicitly.
"""

import os

from groq import Groq

from embedding.relation_text import relation_to_sentence
from retrieval.hybrid_search import EnrichedHit

MODEL = "openai/gpt-oss-20b"

TEMPERATURE = 0
"""Was 0.2 - changed after a real-usage audit confirmed it as the
cause of observed non-reproducibility (retrieval was independently
verified deterministic across identical calls; the LLM layer was not
- 10/11 test questions produced differently-worded "cannot be
determined" answers on identical retrieved facts, and one question
produced an unhedged, over-inferred wrong answer on one of two
identical trials - see docs/, "Week 7, real-usage reality check").

Honest limit, not a full guarantee: temperature=0 makes the SAME
input produce the SAME output reliably - it does not make that output
CORRECT. The Jermyn over-inference case wasn't the model choosing
between right and wrong at random; it was over-inferring "owns implies
manages" on one of two trials. At temperature=0 that same over-
inference would very plausibly happen every time, not half the time -
consistently wrong, not fixed. If that turns out to still happen,
it's a separate, prompt-instruction-following problem, not a sampling
problem, and needs its own fix rather than being expected to disappear
here."""

_client: Groq | None = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY environment variable is not set.")
        _client = Groq(api_key=api_key)
    return _client


def _fact_line(r: dict) -> str:
    """Render one single-hop fact, with an explicit note when the
    query's detected direction doesn't match this fact's stored
    direction - the LLM is told this directly rather than left to
    infer it, consistent with computing signals rather than having
    the model guess."""
    readable_relation = r["relation"].replace("_", " ")
    line = f"- {r['entity1']} {readable_relation} {r['entity2']} (source: chunk {r['chunk_id']})"
    if r.get("query_direction_match") is False:
        line += (" [Note: this fact may describe the relationship in the "
                  "OPPOSITE direction from how the question is phrased - "
                  "check carefully before treating it as the answer.]")
    return line


def _chain_line(chain: dict) -> str:
    """Render a multi-hop chain as a sequence of natural-language
    sentences, one per hop - reusing relation_to_sentence() rather
    than inventing new phrasing a third time this week (single source
    of truth for direction-correct sentence generation)."""
    sentences = []
    path = chain["path"]
    for i, (relation, direction) in enumerate(zip(chain["relations"], chain["directions"])):
        a, b = path[i], path[i + 1]
        entity1, entity2 = (a, b) if direction == "forward" else (b, a)
        sentences.append(relation_to_sentence(entity1, entity2, relation))
    return "- " + ". ".join(sentences) + "."


def _facts_to_text(hits: list[EnrichedHit]) -> tuple[str, str]:
    """Flattens enriched hits into separate single-hop and chain fact
    lists for the prompt - kept separate because the model needs
    different instructions for each (see generate_answer's prompt).

    Returns:
        (single_hop_facts_text, chain_facts_text) - either may be the
        placeholder "(none)" if that category is empty.
    """
    fact_lines = []
    seen_facts = set()
    chain_lines = []
    seen_chains = set()

    for hit in hits:
        for r in hit.all_relationships:
            key = (r["entity1"], r["relation"], r["entity2"], r["chunk_id"])
            if key in seen_facts:
                continue
            seen_facts.add(key)
            fact_lines.append(_fact_line(r))

        for chain in hit.chains:
            key = (tuple(chain["path"]), tuple(chain["relations"]))
            if key in seen_chains:
                continue
            seen_chains.add(key)
            chain_lines.append(_chain_line(chain))

    facts_text = "\n".join(fact_lines) if fact_lines else "(none)"
    chains_text = "\n".join(chain_lines) if chain_lines else "(none)"
    return facts_text, chains_text


def generate_answer(question: str, hits: list[EnrichedHit]) -> str:
    """Turn retrieved graph facts into a grounded natural-language answer.

    Args:
        question: The user's original question.
        hits: Output of retrieval.hybrid_search.hybrid_search().

    Returns:
        A natural-language answer, or an honest "not found" message if
        no relevant facts were retrieved.
    """
    facts_text, chains_text = _facts_to_text(hits)

    prompt = (
        "You answer questions about a novel using ONLY the facts and "
        "chains listed below.\n\n"
        "SINGLE-HOP FACTS are separate, isolated statements - they are "
        "NOT connected to each other unless a single fact explicitly "
        "states the connection. Do not chain or combine two separate "
        "single-hop facts to infer something not explicitly stated as "
        "one fact. Example of what NOT to do: if one fact says 'A is "
        "friend of B' and a separate fact says 'C is protector of D', "
        "do not conclude 'C is protector of A's friend' - B and D may "
        "not even be the same person unless a fact says so explicitly.\n\n"
        "CHAINS are different: each chain below is a single, pre-verified "
        "multi-hop path already confirmed against the story's graph, "
        "given to you as one connected unit - not something you are "
        "combining yourself. You may use a chain as complete evidence "
        "for a multi-step question, but do not extend a chain further "
        "or combine it with anything beyond what it explicitly states.\n\n"
        "Facts flagged with a direction note may describe the relationship "
        "in the opposite direction from how the question is phrased - "
        "read the note and the question carefully before using such a "
        "fact as the answer.\n\n"
        "If the exact fact or chain the question asks for is not "
        "explicitly present, say plainly that it cannot be determined "
        "from the retrieved facts, rather than guessing.\n\n"
        f"Single-hop facts:\n{facts_text}\n\n"
        f"Chains:\n{chains_text}\n\n"
        f"Question: {question}\n\n"
        "Answer in 1-3 sentences:"
    )

    client = _get_client()
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=TEMPERATURE,
        max_tokens=500,
        reasoning_effort="low",
    )

    answer = response.choices[0].message.content
    if not answer or not answer.strip():
        raise RuntimeError(f"Model returned empty content. Full response: {response}")

    return answer.strip()
