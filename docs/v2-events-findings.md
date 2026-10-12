# v2 Findings — Events as Graph Objects

Findings from auditing whether ARF supports first-class event nodes, which the
counterfactual-simulation goal requires. Literature context (Vauth & Gius) is in
[`research-notes.md`](research-notes.md#event-annotations-of-prose--vauth--gius-2022);
the resulting design is summarized in
[`architecture.md`](architecture.md#event-model-planned).

**Motivating case.** "What if the hero died in the second battle" has no node to
remove: "the second battle" is not represented anywhere in the graph, only
implicit in scattered edges. Whether and how events become nodes is therefore a
schema prerequisite for simulation, not parallel work.

**Method.** Before assuming new extraction was needed, the existing 414
`EVNT`-typed entity occurrences were audited on real data
(`notebooks/explore_events.ipynb`).

---

## Audit findings

- **Scale.** 414 EVNT occurrences, 331 unique raw strings, across 74 of 96 books.
- **Mixed content.** Manual sampling found real historical events (`Battle of Bull
  Run`), artistic-work titles (`Tristan and Isolde`), structural extraction
  artifacts (`'CHAPTER VI'` tagged as an event), a bare demonstrative (`'This'`),
  and generic recurring concepts (`breakfast`, `arrest`). It is not mostly
  removable, specific occurrences.
- **Confirmed mistagging, not just ambiguity.** `Tristan and Isolde` is tagged
  both `EVNT` and `OBJ` in the same book, in relations involving the same person
  (`author_of` for the EVNT cases, `owns` for the OBJ case). Corpus-wide, 1,119
  distinct strings carry more than one entity type. This count is global rather
  than per book, so some of it is legitimate cross-book homonymy; re-scoping it
  per book is an open follow-up.
- **EVNT-to-EVNT relations: 3 in the entire corpus**
  (`'Second Manassas' associated_with 'big battle'`, `'dance and general feast'
  associated_with 'slaying an elephant'`, `'Mons retreat' occurs_in 'Battle of the
  Marne'`). No sequencing or causality signal exists to build simulation ordering
  on. This is decisive on its own, independent of the type-quality question.
- **Entity types on the other side of EVNT relations:** PER 278, LOC 39, WTHR 27,
  ORG 26, FAC 12, TIME 11, CNCP 11, EVNT 6, OBJ 2, SENT 1, VEH 1. PER is a
  majority (about 67%) with a noisy tail, a softer signal than a clean pass.
- **Hidden-event check.** Event signal might live in relation *type* rather than
  the unreliable EVNT tag. The top 30 relation types are almost entirely
  relationship states. A full 48-type sweep for event-shaped verbs found 33
  instances: `kills` (2), `married_to` (2), `attacks` (12), `captured_by` (15),
  `captures` (2). Thin, and decisive.
- **Why so few events.** The stative versus change-of-state taxonomy
  (Vauth & Gius) explains the numbers: ARF's 48-type ontology was built for
  character relationships, which are stative, so event-shaped relations were never
  what it was designed to hold. This is a structural blind spot in the ontology,
  not a GPT-4o extraction miss.
- **No exact chunk-boundary duplicates** were found in the sample. The specific
  worry raised beforehand was disconfirmed by the check.

## Per-relation checks of "event-shaped relations are always PER to PER"

An initial claim that Tier 1 relations are always between persons was checked
against all 33 real rows and falsified, not uniformly but by relation type:

| Relation | Result |
|---|---|
| `attacks` (12 of 12) | Never PER to PER; always targets FAC, LOC or VEH (`Tyler's regiments → the wall`, `McDowell → Henry Hill`). A consistent pattern meaning "a military force assaults a place": real events, but a structurally different shape (actor plus target location) than a victim/perpetrator schema. |
| `captured_by` / `captures` (13 of 16 clean) | Mostly holds. Three exceptions: `Regulus captured_by Carthaginians` (an ORG, still a sensible event) and two odd non-person captures (`rope captures tiger`, `commander captures frigate`) that must not auto-promote. |
| `kills` (n = 2) | Exposed a deeper problem than relation reliability: `tiger (PER) kills sheep (PER)`, both animals mistagged `PER`. The `PER` tag cannot be trusted to mean "a human character", which matters well beyond this relation. |
| `married_to` (2 of 2) | A clean, unambiguous failure: both link a person to a location (`Arthur Rushton married_to London`), reading as "married at this venue" conflated with "married to this person". |

## Design and corrected recommendation

Mechanical-first, dataset-first and non-destructive (same shape as the
resolution layer): a map alongside the raw graph, never mutating it.

1. **Tier 1, event-shaped relations:** direct edge reification, with no blanket
   auto-promotion. `captured_by`/`captures` stay with a participant-type-tolerant
   schema and the three exceptions routed to `needs_review`. `attacks` stays as a
   distinct event subtype, not forced into a person-harm role schema. `kills` and
   `married_to` move to `needs_review` given their failure rates.
2. **Tier 2, EVNT-typed entities, a tiered `event_candidate` map:** mechanical
   exclude (structural artifacts, bare pronouns), then flagged but not excluded
   (the creative-work-verb pattern, generalized to "this raw string is also tagged
   with a different type elsewhere in the same book"), then `needs_review`
   (tractable at single-book scope: low dozens, not 331).

**Not pursued:** LLM-prompt event extraction (Vrittanta-EN). It would create graph
structure ARF never provided, which needs its own explicit exception to the
dataset-first constraint rather than an extension of the identity-verifier
carve-out.

## Open

- **Edge semantics:** generic `involved_in` for both participants, or
  role-differentiated edges (`victim_of`/`perpetrator_of`; `actor_of`/`target_of`
  for the `attacks` subtype)?
- **Does the original binary relation edge stay** alongside an event node
  (matching the non-destructive pattern used elsewhere) or get removed?
- **One event or two:** `Cassandra captured_by Greeks` and `Andromache
  captured_by Greeks` in the same chunk with the same captor. A modeling choice,
  not urgent, not yet made.
- **Per-book re-scoping** of the 1,119 multi-typed-string count before it is used
  to argue anything beyond the one confirmed `Tristan and Isolde` example.
