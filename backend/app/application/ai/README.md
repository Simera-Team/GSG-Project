# `app/application/ai` — staging area, not the live path

This package came from the `feature/ai-architecture` branch. The pipeline that
actually runs lives elsewhere; nothing outside this folder imports anything in
it. **Do not edit a module here expecting a behaviour change.**

It is kept because four of its stages have no equivalent in the live path yet
(see *Pending* below), and because the rule identifiers it defines are the
ones the live path now cites.

## Superseded — the live version is elsewhere

The logic below was merged into the running pipeline. The copy here is history;
change the live module instead.

| Module here | Live module |
|---|---|
| `normalization/dates.py` | `app/domain/services/dates.py` |
| `normalization/places.py` | `app/domain/services/countries.py` |
| `normalization/contacts.py` | `app/domain/services/contacts.py` |
| `skills/canonicalizer.py`, `skills/alias_table.py` | `app/domain/services/skills.py` + the standard-skill migrations |
| `conflict_resolution/` | `app/domain/services/conflict_rules.py` |
| `extraction/vetting_parser.py` | `app/application/services/vetting_parser.py` |
| `rules.py` | `app/domain/services/rules.py` |
| `schemas/extracted_profile.py` | `app/application/dto/cv_extraction.py` |
| `schemas/field_record.py` | `app/domain/entities/field_record.py` |

Differences that remain deliberate, where the live version is the one that
holds:

- **Dates** keep month or year precision only, never a day (FR-028). The
  version here kept days.
- **Soft skills** are standard skills with their own aliases, not a stop list.
  Nothing is dropped for being a soft skill (FR-062).

Three behaviours were later changed back to match the AI rules document, so
the live path now agrees with this package on them: fuzzy skill matching maps
automatically with a 0.85 mapping factor, an ambiguous date keeps the year
with a 0.80 validation factor and no review item, and the default review
limit is 0.65 — stored as a setting an administrator can change (FR-046,
FR-067) rather than a constant.

## Pending — real gaps in the live path

1. `matching/entity_matcher.py` (M-01). The live `ProfileBuilder` de-duplicates
   entities on exact tuples, so "Google" and "Google LLC" stay two jobs and
   their fields never meet to be compared. Porting this is what makes the
   conflict rules apply inside work experience and education, not only to
   personal details.
2. `confidence/scorer.py` and `confidence/evidence_verifier.py`. The live path
   uses the model's own confidence and a yes/no evidence check; these compute a
   score from four separately verifiable factors, which is what FR-048's
   quality numbers would be built on.
3. `extraction/prompts.py` and `extraction/profile_extractor.py` — an
   alternative prompt and extraction loop. The live retry loop in
   `CVProcessingService` is the one that records attempts (FR-058) and should
   stay in charge of retries; only the prompt is worth comparing.
4. `app/infrastructure/ai/langchain_structured_output_generator.py` with
   `app/application/interfaces/structured_output_generator.py` — a second
   provider path, kept so NFR-035 is demonstrable rather than asserted. The
   live port is `IAIClient`, which also returns the raw answer and the model
   version that FR-058 stores.

## Before deleting this folder

Everything here is on the `feature/ai-architecture` branch too, so deleting it
loses nothing permanently. Do it once the four items above are either ported or
written off, so the decision is recorded rather than implied.
