# The AI pipeline: files, features, and how to test it

Reference for the extraction pipeline on `feature/cv-ai-integration` — every
file involved in turning an uploaded CV into profile values, what each one is
for, how they fit together, and how to run the flow yourself.

Nothing here is aspirational: every file listed exists on this branch, and
every command in [How to test the flow](#how-to-test-the-flow) was run while
writing this. Where something does not work yet, it says so.

---

## Contents

- [The flow at a glance](#the-flow-at-a-glance)
- [Stage 1 — Text extraction](#stage-1--text-extraction)
- [Stage 2 — The LLM call](#stage-2--the-llm-call)
- [Stage 3 — Validating the answer](#stage-3--validating-the-answer)
- [Stage 4 — Field records and the deterministic rules](#stage-4--field-records-and-the-deterministic-rules)
- [Stage 5 — Merging sources and resolving conflicts](#stage-5--merging-sources-and-resolving-conflicts)
- [Stage 6 — The vetting path (no LLM)](#stage-6--the-vetting-path-no-llm)
- [Orchestration](#orchestration)
- [Where AI output is stored](#where-ai-output-is-stored)
- [The staging package](#the-staging-package)
- [AI features, and where each one lives](#ai-features-and-where-each-one-lives)
- [Integration map](#integration-map)
- [How to test the flow](#how-to-test-the-flow)
- [Known gaps](#known-gaps)

---

## The flow at a glance

One upload becomes profile values in six stages. The LLM is involved in
**exactly one** of them.

```
POST /cv/upload                      cv_router.py
  │   validate, store unchanged, hash, create job, reply at once (FR-013)
  ▼
RabbitMQ  "cv.processing"            rabbitmq_publisher.py
  │   {"file_id": 3, "trigger": "first_run"}
  ▼
CV worker                            workers/cv_worker.py → main.py
  │   asyncio.to_thread: OCR, the LLM call and the database all block
  ▼
ProcessCVUseCase.execute()           use_cases/process_cv.py
  │
  ├─ 1. TEXT      StoredDocumentReader ──► ExtractedDocument
  │                 pdf / docx / md extractor, OCR for scans
  │
  ├─ source_kind == "vetting"? ──► VettingParser  (no LLM at all)
  │
  ├─ 2. LLM       CVProcessingService._run_attempts
  │                 build_user_prompt → IAIClient → GeminiAIClient
  │                 up to 3 attempts, each one recorded (FR-058)
  │
  ├─ 3. VALIDATE  validate_llm_output ──► CVExtraction
  │                 drop unknown keys, then match the schema exactly
  │
  ├─ 4. RECORDS   FieldRecordBuilder ──► list[FieldRecord]
  │                 evidence check, then the N- rules: dates, skills,
  │                 countries, phone, email, name. Confidence adjusted,
  │                 then compared against the review limit.
  │
  ├─ 5. MERGE     ProfileBuilder + resolve_field ──► ProfileDocument
  │                 the C- rules across every source this candidate has;
  │                 what no rule decides becomes a review item
  │
  └─ 6. SAVE      one transaction: attempts, field records, review items,
                  rebuilt profile, file status  (NFR-026)
```

Two things are worth holding on to, because every file below follows from
them:

1. **The LLM extracts; it never decides.** It reads one document and fills a
   schema. Which value wins when two sources disagree, whether a date is
   plausible, whether a skill name is standard — all of that is fixed code.
   Same input, same output, no model involved (FR-034, NFR-023).
2. **Every stored value carries its source, its evidence, its confidence and
   the rule that produced it.** That is what makes a value explainable
   months later (FR-035, FR-051).

---

## Stage 1 — Text extraction

Not AI, but the AI is only ever as good as this. All of it is in
`app/infrastructure/file_processing/`.

| File | Lines | What it does |
|---|---|---|
| `base_extractor.py` | 35 | The shape every extractor returns: `text`, `pages`, `hyperlinks`, `method`, `ocr_confidence`, `page_count`. Each page also carries its own `ocr_confidence` and its `text_layer`, which the confidence model needs per page (stage 4b). |
| `extractor_factory.py` | 18 | `get_extractor(".pdf")` → the right class. The one place a format maps to an extractor. |
| `pdf_extractor.py` | 121 | PyMuPDF text layer, per page. A page with no readable text is handed to OCR (FR-017). Collects header/footer text (FR-016) and link targets behind clickable words. |
| `docx_extractor.py` | 66 | Word CVs via `python-docx`, keeping section structure (FR-054). |
| `markdown_extractor.py` | 13 | LinkedIn `.md` exports — the text is already text (FR-019). |
| `ocr_engine.py` | 194 | RapidOCR for scanned pages. Tries orientation fixes and contrast enhancement when confidence is low, and returns a mean confidence 0–1. Stored on the source (FR-018) **and per page**, where it becomes the `base` factor of every value read from that page (stage 4b). |
| `layout.py` | 90 | Turns positioned text boxes into reading order. Finds the vertical gutter in a two-column CV and reads each column top to bottom, so sidebar skills do not land inside work history (FR-015). |
| `document_reader.py` | 32 | `StoredDocumentReader`: reads the stored original through the storage, extracts, and returns `ExtractedDocument`. This is the seam the use case depends on, as `IDocumentReader`. |

**Output contract** — `app/application/dto/extracted_document.py` (17 lines):

```python
@dataclass(frozen=True)
class ExtractedDocument:
    source_name: str                  # file id, used to trace values back
    text: str
    page_texts: list[str] = ...       # empty for DOCX / Markdown
    hyperlinks: list[str] = ...
    extraction_method: str = "text"   # text | ocr | mixed
    ocr_confidence: float | None = None       # mean over the pages that needed OCR
    page_ocr_confidence: list[float | None]   # per page; None for a text page
    page_text_layers: list[str]               # the text-layer part of each page
```

It is a plain dataclass with no extractor imports on purpose: the
application layer never depends on infrastructure.

---

## Stage 2 — The LLM call

### `app/application/interfaces/ai_client.py` (30 lines) — the port

The contract the application depends on. No provider name appears above this
file, so swapping provider touches one module (NFR-035).

```python
@dataclass(frozen=True)
class LLMResponse:
    text: str | None       # raw answer, stored on the attempt record
    provider: str          # "gemini"
    model_version: str     # the model that actually answered
    status: str            # provider finish status
    usage: dict

class IAIClient(ABC):
    def generate_structured(self, system_prompt, user_prompt, json_schema) -> LLMResponse
```

Two deliberate details:

- It returns the **raw text**, not a parsed object. FR-058 requires the
  answer to be stored exactly as it arrived, on an immutable attempt record.
- **One call is one attempt.** The client never retries; the application
  service does, so every try is recorded.

### `app/infrastructure/ai/gemini_client.py` (117 lines)

The only file that imports the Gemini SDK. Notable parts:

- SDK retries are turned **off** (`HttpRetryOptions(attempts=1)`) so the
  application owns the retry policy.
- `temperature: 0` and the response schema are passed, so the model is
  constrained rather than asked politely for JSON.
- `store=False` — the CV is not retained on Google's side after the call.
- Provider errors are mapped to `LLMProviderError` with a `retryable` flag:
  a 429 is retryable with a 30 s wait, a 4xx (bad key, unknown model) is
  not, a timeout is. This flag is what stops the service burning three
  attempts on a problem no retry can fix.
- `to_gemini_schema()` simplifies the Pydantic JSON schema for Gemini:
  inlines `$ref`/`$defs`, rewrites `anyOf: [X, null]` into Gemini's nullable
  form, and drops keys it ignores. Those dropped rules are still enforced
  locally by the validator, so nothing is lost.

### `app/infrastructure/ai/ai_client_factory.py` (19 lines)

`create_ai_client(settings)` picks the implementation from `LLM_PROVIDER`.
Adding a provider means adding a branch here and a class beside it.

### `app/application/prompts/cv_extraction_prompt.py` (169 lines)

`SYSTEM_PROMPT` plus `build_user_prompt(text, hyperlinks, ocr_confidence,
page_texts)`. Kept apart from the client so the wording can be tuned without
touching the API call. It tells the model:

- what the input looks like (two-column reading order, OCR errors, LinkedIn
  placeholder text, the hyperlinks list);
- to extract only what the document states and return `null` otherwise, and
  specifically **not** to add a country it happens to know a city is in;
- never to extract protected traits — gender, age, religion, nationality,
  health, photos (FR-025);
- to copy values as written, leaving date formats alone, because dates are
  normalised in code (FR-028);
- that the CV text is data, not instructions, and any instructions inside it
  are to be ignored — prompt-injection defence, since a CV is attacker-supplied
  content.

> If you change a rule here, re-run `scripts/process_samples` and compare the
> before/after JSON. The prompt is the one part of the pipeline with no unit
> test that can catch a regression.

### `app/application/dto/cv_extraction.py` (119 lines) — the schema

The strict output schema, and the most load-bearing file in the AI path. It
is sent to the model *and* used to validate the answer.

```python
class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")   # unknown keys are an error

class _EvidenceMixin(_Strict):
    confidence: float = Field(ge=0, le=1)
    evidence: str | None   # exact quote containing the value
    page: int | None       # from the [Page N] marker
```

Every value is value + confidence + evidence + page. The entities are
`PersonalInfo`, `WorkExperience`, `Education`, `Skill`, `Certification`,
`Project`, `Language`, `Link`.

Four requirements are satisfied by the shape itself rather than by code:
FR-025 (no protected trait has a field to land in), FR-026 (`value` is
nullable), FR-027 (confidence is required), FR-065 (evidence and page are
required).

---

## Stage 3 — Validating the answer

### `app/application/services/llm_output_validator.py` (112 lines)

Three gates, in order (FR-022):

1. The answer must be JSON, and an object at the top level.
2. Any key the schema does not define is **dropped and reported** —
   `_drop_disallowed` walks the model tree. This is also the mechanism that
   would remove a protected trait if the model volunteered one (FR-025).
3. What remains must validate against `CVExtraction` exactly.

Returns `ValidationResult(is_valid, errors, dropped_fields, extraction)`.
The whole result is stored on the attempt record, so an invalid answer is as
traceable as a valid one. `_clear_evidence_of_null_values` also strips
evidence the model attached to a `null` value, since a value that is not
there cannot have a quote proving it.

---

## Stage 4 — Field records and the deterministic rules

This is where most of the logic lives. The LLM's answer becomes field
records, each checked and normalised.

### `app/domain/entities/field_record.py` (179 lines) — the output contract

```python
@dataclass
class FieldRecord:
    field_id: int
    source: str                   # the source file the value came from
    entity: str                   # "work_experience[2]"
    entity_type: str              # "work_experience"
    field_name: str               # "end_date"
    raw_value: Any                # exactly as the LLM returned it
    value: Any                    # after normalisation
    confidence: float
    evidence: str | None
    page: int | None
    evidence_status: str          # verified | verified_fuzzy | verified_weak | ...
    rule: str                     # "N-DATE-01", "C-02", "llm_extraction", ...
    review_reasons: list[str]
    note: str | None              # hint for the reviewer
    source_kind: str = "cv"       # cv | linkedin | vetting
    source_uploaded_at: datetime | None = None
    confidence_parts: ConfidenceParts | None = None   # why `confidence` is what it is
    model_confidence: float | None = None             # what the LLM said; read by nothing
```

`raw_value` and `value` are both kept, so a normalisation can always be
audited against what the source actually said. `source_kind` and
`source_uploaded_at` are what the conflict rules read in stage 5; they are
filled when records are loaded for a merge. `confidence_parts` is the
arithmetic behind `confidence` — see stage 4b.

The same file holds `ReviewReason` — the full list of reasons a field can
need a person — plus `ReviewItem`, `ReviewOption` and `RejectedValue`, the
record of a value an `R-` rule dropped.

### `app/application/services/evidence_checker.py` (167 lines) — hallucination control

The guard that makes a confident wrong answer survivable (NFR-028). For
every non-null value:

- the evidence snippet must exist in the extracted text — comparison ignores
  case, spacing, quote and dash style, and bullets;
- the value itself must be supported by that snippet;
- how much of the snippet is really there is measured, not just whether it
  is: `SequenceMatcher` against the best-aligned span of the text, on **every
  page**, not only on scans. A model drops a comma or straightens a dash on a
  text layer too, and rejecting those values lost correct data; the
  difference is priced instead.
- long values (over 120 chars — summaries, descriptions) only have the
  snippet checked, since they are joined text.

| Similarity | Status | `evidence` factor |
|---|---|---|
| the snippet is in the text | `verified` | 1.00 |
| ≥ 0.90 | `verified_fuzzy` | 0.85 |
| 0.75 – 0.90 | `verified_weak` | 0.60 |
| < 0.75, missing, or the snippet does not support the value | — | **rejected (R-03)** |

A window starts at `text_position - snippet_position`, which lines the two
copies of the common run up with each other; centring the window on the run
instead slides a snippet whose match sits at one end half out of the window
and scores a near-exact quote as a weak one.

Below 0.75 the snippet is not really in the document, which no score can
express, so the value is **dropped** rather than queued: see stage 4b.

### `app/application/services/field_record_builder.py` (489 lines) — the hub

Turns one `CVExtraction` into an `ExtractionOutcome`: the records to keep,
and the values that were dropped. Read this file first if you read only one.

For every field, in this order:

1. build the record with `raw_value`, evidence, page, and the model's own
   number parked in `model_confidence` where nothing reads it;
2. a `null` value (or `is_current=false`) returns early — no evidence needed
   and nothing to doubt, so it scores 1.00 (FR-026);
3. **evidence check**. If it fails, the value is **rejected** (`R-03`): no
   field record, no review item, an entry on `outcome.rejected`;
4. **normalise** — see the rule table below. This can change `value`, set
   `rule`, add a review reason, and record which confidence factors the
   repair cost;
4. **score** — `base x evidence x validation x mapping` (stage 4b);
5. **then** compare that score against the review limit.

> Step 6 comes last on purpose. If the limit were applied before
> normalisation, a value knocked below it by a repair would still count as
> accepted.

There are three outcomes, and the difference matters: **accepted**,
**flagged** (in the document, but something needs a person — an unreadable
date, an unknown skill, a score under the limit), and **rejected** (not in
the document, so there is nothing to decide).

It also runs three passes over the finished records:

- `_expand_combined_skills` — one entry naming two skills becomes two
  entities, before the loop (N-SKILL-02);
- `_check_current_jobs` — a job marked ongoing that also has an end date is
  contradictory and is flagged (FR-028);
- `_repair_reversed_dates` — a start after its end is swapped (N-DATE-05);
- `_add_inferred_country` — a country read from the city when none was
  stated (N-GEO-02).

---

## Stage 4b — The confidence model

### `app/domain/services/confidence.py` (270 lines)

    confidence = base x evidence x validation x mapping

rounded to two decimals, then compared with the review limit (0.65 by
default, changeable by an administrator: FR-046, FR-067).

A field's confidence used to be the number the model reported about its own
answer. That number is not evidence of anything: a model that invents a
company name reports the same 0.95 it reports for a name copied off the page.
Every score is now computed from checks that can be re-run, and the model's
number is kept only as `model_confidence`, for comparison — it is in no
formula and decides nothing.

| Factor | 1.00 when | Less when |
|---|---|---|
| `base` | the page had a text layer, or the value came from a vetting result | the page was read by OCR: the factor **is** that page's mean OCR confidence |
| `evidence` | the snippet is in the source text | 0.85 for a near quote, 0.60 for a worn one (table in stage 4) |
| `validation` | the value passed its format check as written | 0.80 after a listed repair: `N-DATE-03` ambiguous order, `N-DATE-05` swapped pair, `N-PHONE-01` where the dial code was borrowed from the profile country |
| `mapping` | an exact or alias table match, or the field has no table | 0.85 for a fuzzy match: `N-SKILL-03` corrected spelling, `N-GEO-02` country read from a city |

`base` is per **page**, not per file: one scanned page in a ten-page PDF must
not make the other nine look doubtful, and a 0.60 scan must not hide behind a
file-wide mean of 0.95. `ExtractedDocument` carries `page_ocr_confidence`
(`None` for a text page) and `page_text_layers`, so a value quoted from the
text layer of a page whose *logo* was read by OCR keeps `base` 1.00 — a page
can hold both. Where the page cannot be pinned down on a document that needed
OCR somewhere, the file's own mean applies rather than a text layer the value
may not have come from. The granularity is a page mean, not RapidOCR's
per-box scores.

**FR-018 is served through `base`.** There is no separate "low OCR
confidence" flag any more: a 0.62 page scores every value on it at or below
0.62, which is under the limit, so it reaches a person anyway — and
`confidence_parts` says *which* factor was responsible, which the flag never
did.

### The parts are the explanation

`confidence_parts` is stored on the record and in `extracted_field`, so a
stored 0.68 is not an opinion but "a 0.80 scan, quoted almost exactly", and
the arithmetic can be checked months later (FR-035, FR-048, NFR-023). Four
keys normally; a fifth, `agreement`, appears only when sources agreed, so
`product + agreement` is always the stored number.

### M-04 — agreement between sources

A second file stating the same value is evidence the first one did not have,
so in the merge the value is worth more than either reading of it alone: the
**highest** confidence among the agreeing records **plus 0.05**, capped at
1.00, added **once** however many sources agree. Two mentions inside one
source are not agreement — a CV repeating itself confirms nothing.

This runs in `ProfileBuilder` before anything decides which records are
usable, which is the whole reason it is there: two scans of one CV at 0.62
each reach 0.67 together and are accepted, where either alone would have gone
to a person. A record held back for any *other* reason keeps it — agreement
about what the page says is not agreement that the value is usable.

### R-03 — rejected, not queued

A value whose snippet is not in the document never becomes a field record and
never becomes a review item: there is nothing for a person to decide. It goes
on `processing_attempt.rejected` with its raw value, its snippet and the rule,
because "the model claimed this and we threw it away" is exactly what someone
investigating a bad profile needs to see (NFR-028). It is personal data, so it
is stored there and never in an application log.

---

### The rule modules — `app/domain/services/`

Pure functions and lookup tables. No I/O, no clock, no randomness, so they
are trivially testable and always give the same answer (FR-034).

| File | Lines | Rules | What it decides |
|---|---|---|---|
| `dates.py` | 204 | `N-DATE-01..06` | `PartialDate(year, month)` — **month or year precision only, a day is never stored or invented** (FR-028). "03/2022", "March 2022", "2022-03-15" all become `2022-03`. Recognises ongoing-role markers, so a current job differs from a missing end date. An ambiguous `04/05/2022` keeps the certain year at year precision with a 0.80 validation factor. A year beyond next year is a misread. `repair_date_order` swaps a reversed pair. |
| `skills.py` | 228 | `N-SKILL-01..03`, `R-09` | `skill_match_key()` reduces a name to the form two spellings must share: drops endorsement counts, trailing qualifiers, levels, version numbers and a trailing "skills"/"abilities", while keeping `+` and `#` so `C`, `C#` and `C++` stay distinct. `lookup()` is exact on that key. `resolve_fuzzy()` maps a misspelling — one edit for a 5–8 character key, two from 9 up, none under 5 — with a 0.85 mapping factor; two standard names tying choose nothing. `split_entry()` splits "React/Redux" but not "CI/CD". `suggest()` offers a reviewer the closest name and is never applied on its own. |
| `countries.py` | 262 | `N-GEO-01..02` | `CountryCatalog.match()` by name or ISO alpha-2, with aliases for how CVs really write countries ("UK", "KSA", "Palestinian Authority"). `CITY_COUNTRIES` (109 cities) and `infer_country_code_from_city()` for the common case of a CV giving only a city — a city with more than one plausible country is deliberately absent. `DIAL_CODES` (57) feeds the phone rule. |
| `contacts.py` | 125 | `N-PHONE-01`, `N-EMAIL-01`, `N-NAME-01` | Phone to E.164: `+962 7 9000 1234`, `0790001234` and `00962790001234` all become `+962790001234`. A local number borrows the profile's country; with no country it is rejected rather than given a guessed prefix, because a wrong dial code looks correct. Email lowercased. Names title-cased with no acronym exemption — CV headers shout names, and no person's name is an acronym. |
| `entity_matching.py` | 611 | `M-01`, `R-10` | Stage 5. Which entities from different sources are the same thing. See below. |
| `confidence.py` | 270 | `R-03`, `M-04` | Stage 4b. The four factors, the thresholds that grade an evidence match, and the cross-source agreement boost. |
| `conflict_rules.py` | 272 | `C-00..06` | Stage 5. See below. |
| `rules.py` | 103 | — | Every rule identifier with a sentence explaining it, so a stored `rule` string can be shown to a person (FR-051). `describe()` raises on an unknown id, and a test walks every rule class, so a rule added without a description fails CI rather than reaching a dashboard as a bare code. |

---

## Stage 5 — Merging sources and resolving conflicts

### `app/domain/services/entity_matching.py` (611 lines)

The ladder below can only compare two values of one field, so something has
to decide first that a CV's job and a LinkedIn job are *the same job*.
`match_entities(records)` groups the accepted records into entities per
source, then matches those across sources:

| Entity | Same when |
|---|---|
| `work_experience` | The **company keys** are equal or ≥ 0.90 similar (`difflib`), **and** the date ranges overlap or one side left a start or end unstated. `company_key()` lowercases, drops punctuation, a leading "the" and legal suffixes (`llc`, `inc`, `ltd`, `gmbh`, `pvt`, …), so "Google LLC", "google, inc." and "Google" are one company and "The Walt Disney Company" is `walt disney`. |
| `education` | Institution keys equal or ≥ 0.90 similar after common abbreviations are written out (`univ.`→university, `inst.`→institute, `tech.`→technology, `coll.`→college, `dept.`→department), so "Univ. of Jordan" and "University of Jordan" are one institution, **and** the same field of study where both name one, **and** the dates overlap or are unstated. Legal suffixes are *not* stripped here: "University" and "Institute" are what such names are made of. |
| `certifications` | The normalized name is **exactly** equal and the issuer agrees or is missing on one side. "AWS Developer" and "AWS Architect" are similar strings and different certificates. |
| `projects` | The normalized name is exactly equal. |

What is deliberately **not** part of a match:

- the **job title**, so "Engineer" against "Senior Engineer" at one company
  over one span is one job and the title is settled by `C-02`/`C-03`;
- the **degree level**, so a bachelor's and a master's of one study at one
  institution is one entry with a field conflict, not two silent degrees;
- anything from the **same source**. Two jobs at one company in one CV are
  two jobs, so a group holds at most one entity per source.

A year-only start counts as January and a year-only end as December, and
"present" is an open end — **today's date is never read** (FR-034). Two
fully dated spells at one employer that do not overlap are a promotion, so
they stay two rows.

Sources are processed in a fixed order (upload time, then source id) and
candidates are worked out for every entity before anything is merged, so the
groups never depend on the order records arrive in (NFR-023). An entity that
could equally be either of two entities from another source is merged with
**nothing**: it is kept on its own and a reviewer is asked which one it is
(`R-10`, review reason `entity_match_ambiguous`), because picking one of two
equally good candidates is exactly the guess these rules exist to avoid.

Each group's `entity_id` is taken from its **earliest** member in that fixed
order, so a newly uploaded source never renumbers the entities already in a
profile. A group that actually brought sources together cites `M-01` on the
profile record it produces.

### `app/domain/services/conflict_rules.py` (272 lines)

When a candidate has a CV *and* a LinkedIn export *and* a vetting result,
the same field arrives more than once. `resolve_field(candidates)` applies a
fixed ladder and returns which rule decided, or who to ask:

| Rule | Decides | Requirement |
|---|---|---|
| `C-00` | Every source agreed (case and spacing ignored) | — |
| `C-01` | A vetted value exists → it wins over anything self-reported | FR-032 |
| `C-04` | Same value at two precisions → the more precise one | FR-028 |
| `C-02` | The newer source wins — **only** where the field policy allows recency | FR-031 |
| `C-03` | Still tied → the more trusted source kind, **only** where the field policy allows priority | — |
| `C-05` | Nothing decided, personal detail → ask the candidate | FR-033 |
| `C-06` | Nothing decided, a claim → ask a reviewer | FR-033 |

`FIELD_POLICIES` is the "list kept in code configuration" FR-031 asks for.
Each row says whether recency may decide, whether source priority may decide,
who the fallback is, and the source priority order. `recency` and `priority`
are each a licence for one rung: switching one off does not pick a different
value, it makes that rung decline, so the field falls through to the person
named by `fallback`. That is the only safe way to say "no rule we have can
settle this". The reasoning is in the file; the shape of it:

- a **name** does not get truer with a newer file, so recency is off and the
  CV outranks a stale LinkedIn headline;
- a **headline** is the one thing people keep current on LinkedIn, so
  recency is on and LinkedIn outranks the CV;
- **city, country, email, phone** fall back to the *candidate*, not a
  reviewer — only they can settle where they live;
- a **degree** is a claim about the past: recency off, **and priority off** — a
  bachelor's in the CV against a master's on LinkedIn is not settled by
  preferring LinkedIn, because one of the two is simply wrong and only a
  person can say which, so it reaches `C-06` with both values;
- a field with **no row** gets the safe default — recency, then priority,
  then a reviewer. It never silently picks a value no rule supports.

### `app/application/services/profile_builder.py` (368 lines)

Builds the live profile from accepted field records (FR-036, FR-063).

- Calls `resolve_field` per personal field and uses the winner, recording
  the deciding rule on the record.
- Groups work experience, education, certifications and projects with
  `match_entities` (`M-01`) and then runs the **same** ladder on every field
  of each group, so the `C-` rules apply inside an entity and not only to
  personal details. A matched entity keeps every `field_id` that fed it, from
  every source (FR-063).
- A reviewer's decision (`rule == "review_decision"`) settles a field across
  all sources; the latest one wins and a rejection leaves it empty (FR-043).
- Flagged records stay **out** of the live profile until a person decides
  (FR-040), but are still stored — nothing is lost.
- Skills are unioned across sources without repeats (FR-030).
- Every profile record lists the `field_ids` that produced it (FR-063), so a
  profile value always traces back to evidence.
- The result must validate as `ProfileDocument`; if it does not, no profile
  is produced and the job goes to review (FR-038).

### `app/application/dto/profile_document.py` (129 lines)

The Simera profile format, as Pydantic. The validation gate for FR-038, and
what gets stored as the generated profile JSON.

### `app/application/services/profile_rebuild_service.py` (28 lines)

Short but important. After any file is processed, or any reviewer decision,
the profile is rebuilt from the field records of **all** of the candidate's
sources, and cross-source conflicts are recomputed. The profile is therefore
never edited in place — it is always a function of the stored field records
(FR-063, FR-064). An open conflict that has not changed keeps its review
item and id, so a reviewer looking at it is not interrupted.

---

## Stage 6 — The vetting path (no LLM)

### `app/application/services/vetting_parser.py` (219 lines)

A vetting result is structured data the platform produced itself, so there
is nothing to extract and nothing to doubt: no model is called, confidence
is 1.0, and the evidence is the payload entry.

```json
{"skills":    [{"name": "React", "level": 4}],
 "languages": [{"name": "English", "proficiency": "fluent"}]}
```

- Skill names go through the same catalog as CV skills, so a vetted
  "postgres" becomes "PostgreSQL".
- A level outside 1–5 is rejected, but the **skill itself is still
  recorded** — the candidate does have the skill, only its level is unusable
  (FR-056).
- An unknown skill is queued, never silently stored or dropped (FR-062).
- Records carry `source_kind="vetting"`, which is exactly what `C-01` looks
  for. **Without this file, no vetted record exists and `C-01` can never
  fire.**

`ProcessCVUseCase._process_vetting` runs it and still writes an attempt
record, so a vetting source is as traceable as any other (FR-058).

---

## Orchestration

### `app/application/services/cv_processing_service.py` (189 lines) — the LLM loop

Owns the retry policy (FR-023) and the attempt log (FR-058).

- No readable text → no LLM call at all; the job goes to review with the
  reason (FR-020).
- Up to `max_attempts` (3) tries with doubling waits: 2 s, then 4 s. A
  non-retryable provider error breaks out immediately instead of wasting
  the remaining attempts.
- **Every** try produces an immutable `ProcessingAttempt`: number, trigger,
  provider, model version, start and end time, outcome
  (`valid`/`invalid`/`error`), the raw answer, the validation result, the
  error. These are what FR-059's dashboard numbers are computed from.
- After three failures: review queue with the reason, and **no profile
  data** is saved.

Returns `ProcessingResult(status, reason, attempts, field_records,
review_items, profile, confidence_threshold)`. `status` is one of
`done` / `needs_review` / `failed`, and `confidence_threshold` records the
limit this job ran under (FR-067).

`app/domain/entities/processing_attempt.py` (58 lines) holds
`ProcessingAttempt`, `AttemptLog`, `AttemptOutcome` and `AttemptTrigger`
(`first_run` / `auto_retry` / `admin_rerun` — an admin re-run is recorded
but does not count toward the automatic limit, FR-059).

### `app/application/use_cases/process_cv.py` (195 lines) — the top level

The sequence for one file:

1. mark the file `processing` and **commit**, so the candidate sees it
   straight away (FR-014);
2. read the stored original and extract text — a failure here is FR-020,
   saved as failed with a review item;
3. vetting source → `VettingParser`; otherwise → `CVProcessingService`;
4. in **one** transaction (NFR-026): attempts, the valid attempt's field
   records, this file's review items, the rebuilt profile, the file status.
   If the save fails, nothing from step 4 is kept and the file is marked
   failed.

### `app/core/processing_dependencies.py` — the wiring

`build_process_cv_use_case(db, settings)` assembles the real
implementations. It also reads the **review limit in force from the
database**, not from the environment, so an administrator's change applies
without a redeploy (FR-046, FR-067).

### `app/workers/cv_worker.py` and `main.py` — the entry point

`main.py` consumes the durable `cv.processing` queue with
`prefetch_count=1`. `cv_worker.handle_message` parses
`{"file_id", "trigger"}` and runs the use case through
`asyncio.to_thread`, because OCR, the LLM call and the database all block.
A failure is logged and **not requeued** — the use case has already marked
the file failed, so it is visible to an administrator (FR-042) rather than
looping. Logs carry ids and outcomes only, never CV content (NFR-022).

---

## Where AI output is stored

| Table | Model file | Holds |
|---|---|---|
| `processing_attempt` | `persistence/models/processing_models.py` | One row per try: trigger, provider, model version, outcome, raw answer, validation result, timings, the limit used. Never overwritten (FR-058). |
| `extracted_field` | same file | One row per field record: value, raw value, confidence and its four parts, the model's own number, evidence, page, evidence status, rule, review reasons (FR-035). |
| `review_item` / `review_option` | `persistence/models/review_models.py` | The needs-review queue with every competing value and its source (FR-041, FR-033). |
| `profile_change_log` | same file | Field history: before, after, who, why (FR-037). |
| `vetting_record` | `persistence/models/vetting_model.py` | Vetted skill levels (FR-056). **Nothing writes to it yet** — see the gaps. |
| `system_setting` | `persistence/models/system_setting_model.py` | The review limit, with who changed it and when (FR-046, FR-067). |
| profile tables | `persistence/models/profile_records_model.py` | The generated profile; each record references the field records that produced it (FR-063). |

`persistence/repositories/processing_repository.py` writes all of it in one
transaction. Its `load_profile_field_records` joins `source_file` to carry
`source_kind` and `uploaded_at` onto each record — that join is what makes
`C-01` and `C-02` possible.

**Reading it back:** `GET /profile/me` and `/profile/{id}/history`,
`GET /review/items` and `/review/items/{id}`,
`POST /review/items/{id}/resolve` and `/request-candidate`,
`GET /admin/dashboard` and `/admin/files/{id}`.

---

## The staging package

`app/application/ai/` is **not** the live path. Nothing outside that folder
imports it. It came from the `feature/ai-architecture` branch and is kept
because four of its stages have no equivalent in the live path yet. Its
[README](app/application/ai/README.md) is the authority: a table of which
modules are superseded by which live module, which differences are
deliberate, and what is still pending.

**Editing a file there changes nothing.** If a behaviour needs changing, the
live module is in `app/domain/services/` or
`app/application/services/`.

---

## AI features, and where each one lives

| Feature | Requirement | Where |
|---|---|---|
| OCR for scanned pages, with a confidence score | FR-017, FR-018 | `ocr_engine.py` |
| Two-column reading order; header/footer text kept | FR-015, FR-016 | `layout.py`, `pdf_extractor.py` |
| Strict schema sent to the model | FR-021 | `cv_extraction.py` |
| Protected traits never extracted | FR-025 | schema shape + prompt + validator |
| Prompt-injection defence (CV text is data) | NFR | `cv_extraction_prompt.py` |
| Schema validation before anything is used | FR-022 | `llm_output_validator.py` |
| Retries with increasing wait, then review | FR-023 | `cv_processing_service.py` |
| One immutable record per attempt | FR-058, FR-059 | `processing_attempt.py` |
| Confidence on every field | FR-027 | `confidence.py` + `field_record_builder.py` |
| Confidence computed from verifiable factors, not the model's claim | FR-048 | `confidence.py` |
| Evidence: snippet and page, verified in the text | FR-065, NFR-028 | `evidence_checker.py` |
| Null when absent; no invented values | FR-026 | schema + builder early return |
| Date normalisation, precision kept | FR-028 | `dates.py` |
| Skill standardisation, aliases, fuzzy spelling | FR-029, FR-062 | `skills.py` |
| Skills unioned across sources | FR-030 | `profile_builder.py` |
| Country matching, and inference from a city | FR-070 | `countries.py` |
| Phone / email / name normalisation | — | `contacts.py` |
| Vetted beats self-reported | FR-032 | `conflict_rules.py` + `vetting_parser.py` |
| Newer source wins, where the policy allows | FR-031 | `conflict_rules.py` |
| Unresolved conflicts keep every value and go to a person | FR-033 | `conflict_rules.py`, `profile_builder.py` |
| Conflicts resolved by fixed rules, no LLM | FR-034 | `conflict_rules.py` |
| Every value cites its rule | FR-035, FR-051 | `field_record.py`, `rules.py` |
| Profile always rebuilt from field records | FR-036, FR-063 | `profile_rebuild_service.py` |
| Flagged values stay out of the live profile | FR-040 | `profile_builder.py` |
| Vetting JSON parsed without an LLM | FR-056, FR-057 | `vetting_parser.py` |
| Admin-settable review limit, recorded per job | FR-046, FR-067 | `settings_repository.py`, `system_setting_model.py` |
| Provider swappable | NFR-035 | `ai_client.py`, `ai_client_factory.py` |

---

## Integration map

Who depends on whom. Arrows point from caller to callee; everything crossing
a layer boundary goes through a port (an `I*` interface).

```
cv_router ─► FileService ─► IMessagePublisher ──► RabbitMQ
                                                    │
                                              cv_worker
                                                    │
                                        ProcessCVUseCase
                                      ╱       │       ╲
                        IDocumentReader   IAIClient   IProcessingRepository
                               │              │              │
                   StoredDocumentReader  GeminiAIClient  SqlProcessingRepository
                               │
                        get_extractor ─► Pdf / Docx / Markdown ─► ocr_engine, layout

ProcessCVUseCase
  ├─► CVProcessingService ─► prompts, IAIClient, llm_output_validator
  │        └─► FieldRecordBuilder ─► evidence_checker
  │                 └─► dates, skills, countries, contacts   (domain/services)
  │        └─► ProfileBuilder ─► entity_matching ─► conflict_rules ─► ProfileDocument
  ├─► VettingParser ─► skills                                (vetting only)
  └─► ProfileRebuildService ─► ProfileBuilder
```

The four ports are the whole reason this is testable without a network, a
database or an API key:

| Port | Defined in | Real | Fake used in tests |
|---|---|---|---|
| `IAIClient` | `interfaces/ai_client.py` | `GeminiAIClient` | `FakeAI` in `tests/test_processing_service.py` |
| `IDocumentReader` | `interfaces/processing_repository.py` | `StoredDocumentReader` | a stub returning `ExtractedDocument` |
| `IProcessingRepository` | same | `SqlProcessingRepository` | in-memory fake |
| `ICatalogRepository` | same | `SqlCatalogRepository` | `seed_skill_catalog()`, `seed_country_catalog()` |

`app/infrastructure/reference_data.py` (176 lines) holds the seed country and
skill lists used by the catalogs and by tests, and is the frozen source the
standard-skill migrations were generated from.

---

## How to test the flow

Four levels, cheapest first. Level 1 needs nothing; level 4 needs everything.

### Level 0 — setup

The extraction and LLM dependencies are **not currently installed** in
`backend/.venv`. Checked while writing this: `pymupdf`, `python-docx`,
`rapidocr`, `onnxruntime`, `opencv` and `google-genai` are all missing.
Levels 2–4 need them; level 1 does not.

```bash
cd backend
pip install -r requirements.txt       # runtime, incl. extraction + Gemini
pip install -r requirements-dev.txt   # pytest
cp .env.example .env                  # then fill in GEMINI_API_KEY
```

`requirements-dev.txt` lists `httpx2`, which looks like a typo for `httpx`
(what FastAPI's `TestClient` needs). If the API tests fail to import, install
`httpx` instead.

### Level 1 — the logic, with no key, no database and no network

This is the fast loop. It covers every rule and the whole pipeline with a
fake LLM.

```bash
cd backend
python -m pytest tests/ -q --ignore=tests/test_ocr.py
# 285 passed, 15 skipped
```

`test_ocr.py` is excluded only because it needs the OCR stack; the 15 skips
are the database integration tests. Pick the file that matches what you are
changing:

| Test file | Tests | Covers |
|---|---|---|
| `test_normalisation.py` | 154 | Dates, skills (incl. fuzzy and the 5-character floor), countries, cities, phone, email, names, and that every rule id has a description. |
| `test_conflict_rules.py` | 28 | Every rung of the `C-` ladder, the policy table, and that the same records always give the same answer. |
| `test_entity_matching.py` | 28 | What counts as the same job, degree, certificate or project across sources and what deliberately does not: the company key, a promotion, one company twice in one CV, two equally good candidates, and that shuffled records and a newly added source leave the result and the entity ids unchanged. |
| `test_confidence_model.py` | 34 | The whole formula, factor by factor, with the arithmetic named in each test: a text page quoted exactly, a near quote, a fuzzy skill match, a repaired date pair, a poor scan, a page-by-page base on a two-page file, a weak quote, a rejection, the model's own number being ignored, the agreement boost (and what is not agreement), a vetted value, and that the shipped 0.65 limit is the documented one. |
| `test_confidence_factors.py` | 9 | The two normalisation rules that lower a score, measured on **built records** rather than on the functions alone. |
| `test_vetting_parser.py` | 23 | FR-056/057, levels outside 1–5, unknown skills, broken payloads. |
| `test_processing_service.py` | 12 | The retry loop and attempt records, via `FakeAI`. Start here for pipeline behaviour. |
| `test_validation_and_evidence.py` | 14 | Schema validation, dropped keys, evidence verification and the three grades of match. |
| `test_settings_repository.py` | 15 | The admin-settable review limit. |
| `test_review_api.py` | — | The review queue endpoints end to end. |
| `test_persistence_integration.py` | — | Real database writes. Skipped unless a database is reachable. |
| `test_no_secrets.py` | — | No key or CV content in logs or fixtures. |

**To test a change to the LLM behaviour without spending a call**, copy the
`FakeAI` pattern — it is 12 lines and scripts replies in order, including
exceptions:

```python
class FakeAI(IAIClient):
    provider, model = "fake", "fake-model-1"
    def __init__(self, *replies): self.replies = list(replies)
    def generate_structured(self, system_prompt, user_prompt, json_schema):
        reply = self.replies.pop(0)
        if isinstance(reply, Exception): raise reply
        return LLMResponse(text=reply, provider="fake",
                           model_version="fake-model-1-0612", status="completed")
```

`tests/helpers.py` builds a valid answer for you: `answer()` returns the full
structure, `f(value, evidence)` one field, and `answer(skills=[...])`
overrides one part. `CV_TEXT` is the matching document text, so the evidence
check passes.

### Level 2 — real CVs, text extraction only (no LLM, no database)

Checks what the model will actually be given. This is the first thing to run
when extraction looks wrong — often the problem is here, not in the prompt.

```bash
cd backend
python -m scripts.extract_samples                      # all of Cv_Samples/
python -m scripts.extract_samples --input Cv_Samples --output extraction_output
```

One JSON per CV in `extraction_output/`, with `extraction_method`,
`ocr_confidence`, `page_count`, `char_count`, seconds, hyperlinks and the
text. `Cv_Samples/` holds seven real CVs on purpose: text PDFs, a
**scanned** PDF (`pilot_cv_sam_carter_scan.pdf` — the OCR path, and the same
CV as the text version so you can compare), two DOCX, and a LinkedIn
Markdown export.

### Level 3 — the full pipeline on real CVs, with a key but no database

The one to run after changing a prompt or a rule. Text extraction → Gemini
with retries → validation → field records with evidence checks → review
items → profile. **Nothing is saved**, so it is safe to run repeatedly.

```bash
cd backend
python -m scripts.process_samples
python -m scripts.process_samples --only pilot_cv_sam_carter.pdf
```

Needs `GEMINI_API_KEY`. Each file is one or more real LLM calls, so it costs
tokens. Prints a line per file and writes full JSON to
`processing_output/`:

```
done         waiter_cv_matthew_walters.pdf   attempts=1 fields=38 accepted=35 review=3
```

The JSON has `status`, `reason`, `confidence_threshold`, every `attempt`
(including the raw answer), every `field_record` with its rule and evidence,
the `review_items`, and the built `profile`. Diffing these files before and
after a change is the regression test for the prompt.

### Level 4 — end to end, with the database and the queue

```bash
cd backend
alembic upgrade head                 # includes source_kind and system_setting
docker compose up -d                 # postgres + rabbitmq
uvicorn app.main:app --reload        # the API
python -m app.workers.main           # the worker, in another terminal
```

Then either go through the API:

```bash
curl -X POST localhost:8000/cv/upload \
     -H "Authorization: Bearer <token>" \
     -F file=@Cv_Samples/pilot_cv_sam_carter.pdf
# 202 Accepted with a file id; the worker picks it up
curl localhost:8000/cv/files/<file_id> -H "Authorization: Bearer <token>"
```

or process a stored file directly, which skips the queue and is easier to
debug:

```bash
python -m scripts.process_file --file-id 3
python -m scripts.process_file --file-id 3 --rerun     # admin re-run (FR-045)
```

`scripts/create_staff_user.py` makes a reviewer or admin account so you can
exercise the review queue and the settings endpoints.

### What to look at when a result is wrong

| Symptom | Look at |
|---|---|
| Text is garbled or in the wrong order | Level 2 output; `layout.py`, `pdf_extractor.py` |
| A scan produced nothing | `ocr_confidence` in level 2; `ocr_engine.py` |
| The model invented a value | `evidence_status` on the record — it should already be flagged; `evidence_checker.py` |
| The model missed a field that is in the text | the prompt, and the level 2 text — is the field actually in it? |
| A date, skill or country came out wrong | the record's `rule`, then that rule's module |
| The wrong value won between two sources | the record's `rule` (a `C-` id), then `FIELD_POLICIES` |
| Too much, or too little, in the review queue | the job's `confidence_threshold`, then `GET /admin/settings` |
| The job failed | the `attempts` — each has its own error and validation result |

---

## Known gaps

Honest list, worst first.

1. **Nothing writes `vetting_record`.** The parser returns `VettedSkill`
   objects and the table exists, but no repository persists them, so FR-057's
   "verified" marking is not visible anywhere yet.
2. **No admin vetting upload route** (FR-007). The `vetting:upload`
   permission exists and the parser works; a `.json` uploaded through the
   CV route is processed correctly, but there is no dedicated endpoint.
3. **`file_hash` is not unique per candidate** (FR-011, FR-055). The
   migration has no constraint and the reference SQL says system-wide
   unique. This is `feature/cv-duplicate-detection`'s work.
4. **The prompt has no automated regression test.** Level 3 output diffing
   is the only safety net.
