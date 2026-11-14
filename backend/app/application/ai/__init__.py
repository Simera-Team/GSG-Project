"""The AI module: document text in, validated field records out.

The module turns the text the backend extracted from one source into field
records, each with its evidence, its confidence and the rule that produced it,
and then merges a candidate's sources into one set of values. Three principles
shape the layout:

1. The LLM extracts; it never decides between sources. Only
   :mod:`~app.application.ai.extraction` talks to a model, and it is given the
   contract in :mod:`app.application.interfaces.structured_output_generator`,
   so no framework or provider is visible from here.
2. Every stored value carries its source, evidence, confidence and rule.
3. Every field ends in exactly one of three outcomes: accept, reject or review.

Packages, in the order a value passes through them:

``schemas``
    The input contract (:mod:`~app.application.ai.schemas.document_text`), the
    schema the model answers with
    (:mod:`~app.application.ai.schemas.extracted_profile`) and the output
    contract (:mod:`~app.application.ai.schemas.field_record`).
``extraction``
    The single LLM-backed step, its prompt, and the no-LLM vetting parser.
``normalization``
    Deterministic N-rules: dates, contacts, places, free text and closed
    vocabularies, plus the table saying which apply to which field.
``skills``
    The shared skill vocabulary and the canonicalization rules over it.
``confidence``
    The evidence check that rejects values the source does not support, and the
    score computed from the four verifiable factors.
``matching``
    Which records from different sources describe the same entity.
``conflict_resolution``
    The field policy table and the rules that apply it, preserving any conflict
    no rule decides.
``pipeline``
    Orchestration only: the stage order for one source, and for a merge.

:mod:`~app.application.ai.rules` holds every rule ID the module cites and
:mod:`~app.application.ai.settings` the thresholds each job records.
"""
