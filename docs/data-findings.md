# Data Findings

What the project has measured about the ARF dataset and the graph built from
it. Every figure here comes from the real corpus, not from assumption. For how
these findings shaped the design, see [`architecture.md`](architecture.md).

Contents: [Dataset](#dataset) · [Loading and cleaning](#loading-and-cleaning) ·
[Entities](#entities) · [Relations](#relations) · [Graph build](#graph-build) ·
[Source-noise catalogue](#source-noise-catalogue) ·
[Temporal structure](#temporal-structure) · [Embedding records](#embedding-records)

---

## Dataset

**Source:** Hugging Face `Despina/project_gutenberg`, config
`synthetic_relations_in_fiction_books`, loaded with `datasets`. Cross-referenced
against the dataset paper (Christou & Tsoumakas, LaTeCH-CLfL 2025; see
[`research-notes.md`](research-notes.md)).

| Property | Value |
|---|---|
| Rows | 95,476, chunk-level |
| Chunk definition | One 5-sentence rolling window (1-sentence overlap) from a book |
| Books | 96 |
| Relation instances | 128,331 (GPT-4o-extracted, 0 or more per chunk) |
| Entity types | 11: PER, FAC, LOC, WTHR, VEH, ORG, EVNT, TIME, OBJ, SENT, CNCP |
| Relation types | 48 canonical (paper Appendix C) |
| Row schema | `book_id, title, author, author_gender, author_birth_year, author_death_year, release_date, pg_subjects, topics, chunk_id, chunk, relations` |

`relations` is a **Python-literal string**, so it needs `ast.literal_eval`, not
`json.loads` (single quotes, not valid JSON). It holds a list of dicts:
`{entity1, entity2, entity1Type, entity2Type, relation}`.

**PER dominates:** 231,313 of roughly 256,700 entity-slot occurrences (over 90%).
This is why entity work is scoped to PER entities.

---

## Loading and cleaning

- **1 malformed row.** The `book_id` field held a truncated fragment of another
  row's `relations` string, an upstream parsing artifact in ARF itself. It is
  filtered by `safe_parse_relations()`, which distinguishes "genuinely empty"
  (`[]`) from "unparseable" (`None`) instead of crashing or silently coercing.
- **`chunk_id` is contiguous within a book in 19 of 20 sampled books**, validated
  as a usable proxy for narrative position. The exception (book 5111) had
  explainable gaps rather than corruption. Book 106 was later confirmed
  contiguous in full (range 0–882, no gaps).
- **Book 74763 has 0 relations** across all 8 of its sampled chunks, a short
  work with nothing extractable, confirmed against the real chunk text. It
  produces a valid empty graph and is excluded from retrieval-ready book lists
  and from corpus-wide measurements (95 of 96 books are processed).
- **`chunk_id` loads as a string** from the cleaned parquet
  (`data/arf_chunks_parsed.parquet`), not an integer. Sorting, `.min()` and
  `.max()` on it are lexicographic (`"1" < "10" < "100" < "11"`) unless cast to
  `int`. This silently produced a nonsensical range and a scrambled passage in
  one exploration. The underlying data is fine once cast; the hazard is for any
  code that reads the parquet.

---

## Entities

**Canonicalization on book 106** (*Jungle Tales of Tarzan*, 279 unique raw
strings) found two distinct phenomena, not one:

1. **Appositive descriptors** are a mechanical, high-precision pattern:
   `"Bolgani, the gorilla"` is the same entity as `"Bolgani"`. A regex
   (`,\s*the\s+.+$` stripped, then lowercased) fixes it. Verified on book 106:
   exactly 5 matches and zero false-positive collisions (no two distinct raw
   names collapsed to one canonical form).
2. **Generic or collective entities** (`"apes"` vs `"the apes"` vs `"young
   apes"`) are a different kind of problem: collective references, not
   individual aliasing. Not resolved. See
   [`known-limitations.md`](known-limitations.md).

**Nickname and title resolution** (`Tarzan` vs `Lord Greystoke`) was not
attempted. A `difflib.SequenceMatcher` diagnostic produced mostly false
positives on short strings (`('Buto','Gunto')` flagged as similar despite being
different characters), so fuzzy string matching was ruled out as a foundation.

**Entity-name quality in the corpus is worse than first documented.** A
real-usage audit of retrieval found raw extraction noise stored as canonical
node names: bare pronouns (`('rufus lyon', 'you')`, `('mr. lyon', 'her')`) and
full descriptive clauses (`('jermyn', "jermyn's third daughter")`,
`('jermyn', 'his third affectionate and expensive daughter')`). Earlier
documented findings concerned *ambiguous* canonical strings; these are
uncleaned strings no user query could ever contain. Quantification and the
resolution work are in
[`v2-entity-resolution-findings.md`](v2-entity-resolution-findings.md).

---

## Relations

- **1,127 unique relation strings** against a closed 48-type ontology. The top
  48 types account for **97.5%** of instances (125,081 of 128,331). The
  remaining 850+ distinct strings are mostly singleton free-text phrases
  (`"screaming at"`, `"spared the life of"`, `"wept like"`): GPT-4o
  occasionally ignored the closed ontology and wrote descriptive verb phrases.
  This matches the ARF paper's reported 2.95% deviation rate.
- This is not typo or casing drift of the kind seen in entity names. There is
  no safe mechanical mapping for the long tail, so it is **not normalized**.
  `is_canonical_relation()` offers an opt-in filter, raw edges stay untouched,
  and the temporal and embedding pipelines default to `canonical_only=True`.
- **Event-shaped relations are rare.** The top 30 relation types are almost
  entirely relationship *states* (`companion_of`, `friend_of`, `sibling_of`).
  A sweep of all 48 types for event-shaped verbs found 33 instances corpus-wide:
  `kills` (2), `married_to` (2), `attacks` (12), `captured_by` (15),
  `captures` (2). See [`v2-events-findings.md`](v2-events-findings.md).
- **Template coverage.** Benchmark question generation is scoped to the 31 of
  48 relation types that have a verified natural-language template; the rest
  fall back to a generic form and are skipped rather than guessed at. At least
  one untemplated relation, `owns`, appeared in real usage. The original build
  recorded 32 hand-written `MANUAL_TEMPLATES`; the one-template difference from
  31 has not been reconciled.

---

## Graph build

| Property | Value |
|---|---|
| Nodes | 44,248 |
| Edges | 128,331 |

The edge total matches the dataset-wide relation count exactly, confirming no
data lost or duplicated across the 96-book build. The one outlier is book
74763 (0 edges, above).

**Parallel edges are real.** The pair `('Tarzan','Taug')` alone has **90
separate relation instances** in book 106, and 141 of 421 pairs in that book
repeat at least once. A simple `DiGraph` would collapse these and destroy
frequency signal, which is why the graph is a `MultiDiGraph`.

**`GML` cannot represent the graph.** `nx.write_gml()` cannot serialize the
`set`-typed `surface_forms` node attribute (GML and GraphML hold scalar
attributes only), confirmed by direct failure. The corpus is persisted with
`pickle`.

---

## Source-noise catalogue

Everything below is a property of ARF's GPT-4o-generated labels, not of the
project's code. The policy for all of it is the same: measure, document, scope
what is built and claimed to what the data supports, and never silently
"correct" ground truth. Several of these were first mistaken for code defects
(see the Mrs. Transome entry).

| Finding | Evidence | Handling |
|---|---|---|
| **`used_by` has inconsistent direction** | See [below](#used_by-direction-inconsistency). | Accepted; not specially handled. |
| **Symmetric relations stored in either direction** | `companion_of` appears both directions for the same pair. Seven relation types confirmed: `companion_of`, `friend_of`, `enemy_of`, `rival_of`, `sibling_of`, `spouse_of`, `relative_of`. | Direction-agnostic queries in the temporal layer; reverse traversal enabled for exactly these seven. |
| **Bidirectional parentage contradictions** | 92 unambiguous cases across 95 books: `parent_father_of` 41, `parent_mother_of` 39, `child_of` 12. Under 1 per book. | Documented; see [below](#bidirectional-parentage-contradictions). |
| **Duplicate relation extractions** | The identical relation dict repeated up to 35 times in one chunk (a passage about "his mother" with no textual repetition). | Deduplicated within a chunk for embedding only; graph stays faithful to raw ARF. |
| **Relation-semantics conflation** | `sir ector` appears as Arthur's foster father under the same relation slot as his biological father. | Accepted; same category as `used_by`. |
| **`married_to` linking a person to a location** | 2 of 2 instances (`Arthur Rushton married_to London`): "married at this venue" conflated with "married to this person". | Routed to manual review in the event design. |
| **`kills` with animals tagged `PER`** | `tiger (PER) kills sheep (PER)`. The `PER` tag cannot be trusted to mean "human character". | Noted; affects any PER-only assumption. |
| **`attacks` never PER to PER** | 12 of 12 target FAC, LOC or VEH (`Tyler's regiments → the wall`): a military force assaulting a place. | Treated as a distinct event subtype. |
| **`captured_by` / `captures` exceptions** | 13 of 16 clean; exceptions include a non-PER captor (`Regulus captured_by Carthaginians`, ORG) and odd captures (`rope captures tiger`, `commander captures frigate`). | Schema tolerates non-PER participants; odd cases not auto-promoted. |
| **Entity-type inconsistency** | `Tristan and Isolde` tagged both `EVNT` and `OBJ` in one book, in relations involving the same person. 1,119 distinct strings carry more than one entity type, counted **globally** rather than per book, so part of this is legitimate cross-book homonymy. | Per-book re-scoping not yet done. |
| **EVNT category mix** | 414 occurrences, 331 unique strings, 74 of 96 books: genuine events (`Battle of Bull Run`), artistic-work titles, structural artifacts (`'CHAPTER VI'`), generic concepts (`breakfast`, `arrest`), and `'This'`. | Tiered handling; see events findings. |
| **EVNT-to-EVNT relations** | 3 in the whole corpus. | No sequencing signal exists in current relations. |
| **Pronoun and clause node names** | `'her'`, `'his daughters'`, `'party'`, `'you'`, `"jermyn's third daughter"`. | Resolution layer (Stage 0). |
| **Surface-name variants** | `mr. harold transome` vs `harold`; `'mrs.holt'` vs `'mrs. holt'` (punctuation-variant split). | Resolution layer (Stage A). |
| **Hard aliases (zero string overlap)** | `wotan` / `wanderer`; `the king` / `tancrede`. | Not mechanically solvable; confirms the literature at corpus scale. |
| **Period and archaic vocabulary** | `sonne` (archaic spelling), `thy`, informal kinship terms (`mamma`, `papa`) in Victorian domestic fiction. | Vocabulary lists extended from real misses only. |
| **Short-form entity keys** | The graph's canonical node can be a bare first name (`harold`) while queries say `Harold Transome`. | Possessive matching tolerates 0–2 trailing words. |

### `used_by` direction inconsistency

The ARF ontology defines `used_by` **twice** with different type-pair
directions (id 36: FAC to ORG; id 47: OBJ to PER), and the paper's prose example
for id 47 appears inconsistent with its own stated type order. Checked against
real data, instances show entity1 as sometimes the user and sometimes the used
object: `{'entity1':'the blacks','entity2':'fire','relation':'used_by'}`
(PER to OBJ) alongside `{'entity1':'Excalibur','entity2':'King Arthur', ...}`
(OBJ to PER). This is source noise a smarter template cannot fix. It is accepted
as a small fraction of instances and documented, not engineered around.

### Bidirectional parentage contradictions

In book 40882 the graph stores both `mrs. transome -> harold` and
`harold -> mrs. transome`, each `parent_mother_of`: the same pair, both
directions, the same relation. The graph therefore asserts incompatible facts
about Harold's parentage, and no traversal or filtering logic can resolve a
contradiction that exists in the data.

Corpus-wide there are 92 such unambiguous cases: 41 `parent_father_of`, 39 `parent_mother_of` and 12 `child_of`. `spouse_of` (302) and
`sibling_of` (317) bidirectional pairs were checked separately and are
**expected**: both are symmetric relations whose mutual relationship legitimately
produces edges in both directions.The 12 `child_of` cases are mutual pairs of the same relation (each node recorded as the other's child), the same kind of contradiction as the parentage cases: the check may not distinguish a true contradiction from the expected co-occurrence of `child_of` and `parent_*_of` describing one relationship from both ends.

**Scope of the claim.** The 92 contradictions are real. Whether they explain the
Mrs. Transome retrieval failure specifically is **unverified**: an earlier
session reclassified that failure as pure source noise, but a separate and
independently identified defect in how a chain's terminal answer is computed
(see [`v2-retrieval-findings.md`](v2-retrieval-findings.md)) contributes to the
same behavior.

---

## Temporal structure

ARF has no calendar dates. `chunk_id` (per book) is the only ordering signal, so
"temporal" means **narrative position** (percent of book), not real-world time.

- **Activity distribution.** `weighted_mean_bin()` (normalized 0–1) over the 95
  books with relations: **89 of 95 (94%) fall in the 0.4–0.6 "roughly even"
  band, corpus mean 0.531.** Book 106, used throughout early development, is
  *not* representative: it shows unusually clustered early and late activity
  with a sparse middle. Narrative-position queries should therefore be
  meaningful across most of the corpus, not just the development book.
- **The adaptive bin count is mostly capped.** `N = clamp(total_relations / 15,
  6, 20)` hits the N=20 cap for 84 of 96 books (any book above 300 relations).
  Only 12 books adapt: 7 at N=6 and one each at 9–13. Book 44 (2,667 relations)
  and book 106 (1,280 relations) both get N=20. This was found incidentally
  while testing phrase parsing and is a property of the v1 formula, not a bug
  in anything built since. Not fixed; revisit only if temporal-query resolution
  proves too coarse on dense books.

---

## Embedding records

- Deduplicating exact `(entity1, entity2, relation)` repeats within a chunk
  leaves **128,190 records** from 128,331 raw canonical instances, matching an
  independently computed unique-key count exactly.
- Record IDs follow `book_id_chunk_id_entity1_entity2_relation`, verified
  collision-free by direct check. An `occurrence` suffix covers residual
  duplicates: 99 cases were found across the corpus, nearly all pronoun or
  generic-reference repeats such as `"my uncle"` appearing verbatim twice in one
  chunk.
