"""Orchestrates the AI stages for one source file.

The stages run in a fixed order — LLM call, schema validation, normalization,
evidence check, confidence score — and the first check that decides a value
ends its chain, so the same input always gives the same result (NFR-023). The
pipeline itself holds no rules: each stage is a collaborator it is given.
"""

import logging

from app.application.ai.confidence.evidence_verifier import EvidenceVerifier
from app.application.ai.confidence.scorer import ConfidenceScorer
from app.application.ai.errors import NoUsableTextError
from app.application.ai.extraction.profile_extractor import ProfileExtractor
from app.application.ai.normalization.dates import repair_date_order
from app.application.ai.normalization.field_normalizers import FieldNormalizerRegistry
from app.application.ai.normalization.places import infer_country_from_city
from app.application.ai.pipeline.candidate_builder import build_candidates
from app.application.ai.rules import RuleId
from app.application.ai.schemas.document_text import DocumentText, SourceMeta
from app.application.ai.schemas.extracted_profile import ExtractedProfile
from app.application.ai.schemas.field_record import (
    PROFILE_ENTITY_KEY,
    CandidateValue,
    EntityType,
    ExtractionResult,
    FieldName,
    FieldRecord,
    RejectedValue,
)
from app.application.ai.schemas.normalization import (
    NormalizationContext,
    NormalizationOutcome,
)
from app.application.ai.schemas.normalized_value import PartialDate, PresentDate
from app.application.ai.settings import AISettings

logger = logging.getLogger(__name__)

#: Entities whose start and end dates are checked for being the wrong way round.
_DATE_ORDERED_ENTITIES = frozenset({EntityType.WORK_EXPERIENCE, EntityType.EDUCATION})


class ExtractionPipeline:
    """Turns one source's text into field records with evidence and confidence."""

    def __init__(
        self,
        extractor: ProfileExtractor,
        normalizers: FieldNormalizerRegistry,
        evidence_verifier: EvidenceVerifier,
        scorer: ConfidenceScorer,
        settings: AISettings | None = None,
    ) -> None:
        self._extractor = extractor
        self._normalizers = normalizers
        self._evidence_verifier = evidence_verifier
        self._scorer = scorer
        self._settings = settings or AISettings()

    async def extract_fields(
        self,
        document: DocumentText,
        meta: SourceMeta | None = None,
    ) -> ExtractionResult:
        """Run every AI stage over ``document`` and return its result.

        Raises :class:`NoUsableTextError`,
        :class:`~app.application.ai.errors.LLMUnavailableError` or
        :class:`~app.application.ai.errors.LLMInvalidOutputError` so the caller
        knows whether to retry; a failure leaves no partial result behind.
        """
        if not document.has_usable_text():
            raise NoUsableTextError(
                f"Source {document.source_id} has no text on any page"
            )

        profile = await self._extractor.extract(document)
        return self.build_result(document, profile, meta)

    def build_result(
        self,
        document: DocumentText,
        profile: ExtractedProfile,
        meta: SourceMeta | None = None,
    ) -> ExtractionResult:
        """Run the deterministic stages over an answer the model already gave.

        Separated from :meth:`extract_fields` so the checks can be run against a
        saved answer, which is what makes the labelled test set cheap to
        re-score after a rule change.
        """
        candidates = build_candidates(profile)
        context = self._build_context(candidates)

        records: list[FieldRecord] = []
        rejected: list[RejectedValue] = []

        for candidate in candidates:
            self._process_candidate(document, candidate, context, records, rejected)

        self._add_inferred_country(document, candidates, records, rejected)
        self._repair_date_order(records)

        return ExtractionResult(
            source_id=meta.source_id if meta else document.source_id,
            fields=records,
            rejected=rejected,
        )

    # --- stages ----------------------------------------------------------

    def _process_candidate(
        self,
        document: DocumentText,
        candidate: CandidateValue,
        context: NormalizationContext,
        records: list[FieldRecord],
        rejected: list[RejectedValue],
    ) -> None:
        """Normalize, check the evidence for and score one candidate value."""
        for outcome in self._normalizers.normalize(candidate, context):
            if not outcome.accepted:
                rejected.append(self._rejection(candidate, outcome))
                continue

            assessment = self._evidence_verifier.verify(
                document,
                snippet=candidate.evidence_snippet,
                raw_value=candidate.raw_value,
                block_id=candidate.block_id,
            )

            if not assessment.found or assessment.evidence is None:
                # R-03: without evidence in the source the value is not kept,
                # however confident the model was.
                rejected.append(
                    RejectedValue(
                        entity=candidate.entity,
                        field=candidate.field,
                        raw_value=candidate.raw_value,
                        reason=RuleId.R_03,
                        detail="Evidence snippet not found in the source text",
                    )
                )
                continue

            confidence = self._scorer.score(
                base=assessment.base,
                evidence=assessment.evidence_factor,
                validation=outcome.validation,
                mapping=outcome.mapping,
            )

            if confidence.below_threshold:
                # The single R-06 retry is the caller's to run, because it needs
                # the OCR engine or another LLM call; the status says so.
                logger.debug(
                    "Field %s.%s is below the confidence threshold",
                    candidate.entity.value,
                    candidate.field.value,
                )

            records.append(
                FieldRecord(
                    entity=candidate.entity,
                    entity_key=candidate.entity_key,
                    field=candidate.field,
                    raw_value=candidate.raw_value,
                    value=outcome.value,  # type: ignore[arg-type]
                    confidence=confidence.confidence,
                    confidence_parts=confidence.parts,
                    evidence=assessment.evidence,
                    normalization=outcome.rule,
                    extraction_status=confidence.status,
                )
            )

    def _build_context(
        self, candidates: list[CandidateValue]
    ) -> NormalizationContext:
        """Resolve the facts a normalizer needs from outside its own value.

        A local phone number has to borrow a country code, so the country is
        resolved first — from the stated country, or from a city that
        identifies exactly one country.
        """
        stated_country = self._first_raw(candidates, FieldName.COUNTRY)
        if stated_country:
            outcome = self._normalizers.normalize(
                CandidateValue(
                    entity=EntityType.PROFILE,
                    entity_key=PROFILE_ENTITY_KEY,
                    field=FieldName.COUNTRY,
                    raw_value=stated_country,
                ),
                NormalizationContext(),
            )[0]
            if outcome.accepted:
                return NormalizationContext(profile_country=str(outcome.value))

        city = self._first_raw(candidates, FieldName.CITY)
        if city and (inferred := infer_country_from_city(city)):
            return NormalizationContext(profile_country=str(inferred.value))

        return NormalizationContext()

    def _add_inferred_country(
        self,
        document: DocumentText,
        candidates: list[CandidateValue],
        records: list[FieldRecord],
        rejected: list[RejectedValue],
    ) -> None:
        """Record a country inferred from the city, when none was stated (N-GEO-02).

        The record cites the city's own evidence, because that is the text the
        country was read from. Nothing is inferred when the document states a
        country, even one that was rejected: a guess must not override it.
        """
        if any(
            record.entity is EntityType.PROFILE and record.field is FieldName.COUNTRY
            for record in records
        ):
            return
        if any(
            entry.entity is EntityType.PROFILE and entry.field is FieldName.COUNTRY
            for entry in rejected
        ):
            return

        city_candidate = next(
            (
                candidate
                for candidate in candidates
                if candidate.entity is EntityType.PROFILE
                and candidate.field is FieldName.CITY
            ),
            None,
        )
        if city_candidate is None:
            return

        inferred = infer_country_from_city(
            city_candidate.raw_value,
            fuzzy_mapping_factor=self._settings.fuzzy_mapping_factor,
        )
        if inferred is None or not inferred.accepted:
            return

        assessment = self._evidence_verifier.verify(
            document,
            snippet=city_candidate.evidence_snippet,
            raw_value=city_candidate.raw_value,
            block_id=city_candidate.block_id,
        )
        if not assessment.found or assessment.evidence is None:
            return

        confidence = self._scorer.score(
            base=assessment.base,
            evidence=assessment.evidence_factor,
            validation=inferred.validation,
            mapping=inferred.mapping,
        )

        records.append(
            FieldRecord(
                entity=EntityType.PROFILE,
                entity_key=PROFILE_ENTITY_KEY,
                field=FieldName.COUNTRY,
                raw_value=city_candidate.raw_value,
                value=inferred.value,  # type: ignore[arg-type]
                confidence=confidence.confidence,
                confidence_parts=confidence.parts,
                evidence=assessment.evidence,
                normalization=inferred.rule,
                extraction_status=confidence.status,
            )
        )

    def _repair_date_order(self, records: list[FieldRecord]) -> None:
        """Swap a start and end date that are the wrong way round (N-DATE-05).

        Both records keep their evidence and are rescored with the repaired
        validation factor, since the repair is deterministic but the source was
        wrong about something.
        """
        by_entity: dict[str, dict[FieldName, int]] = {}

        for index, record in enumerate(records):
            if record.entity not in _DATE_ORDERED_ENTITIES:
                continue
            if record.field not in {FieldName.START_DATE, FieldName.END_DATE}:
                continue
            by_entity.setdefault(record.entity_key, {})[record.field] = index

        for positions in by_entity.values():
            start_index = positions.get(FieldName.START_DATE)
            end_index = positions.get(FieldName.END_DATE)
            if start_index is None or end_index is None:
                continue

            start, end = records[start_index], records[end_index]
            new_start, new_end, swapped = repair_date_order(
                _as_date(start.value), _as_date(end.value)
            )
            if not swapped:
                continue

            records[start_index] = self._rescore_swapped(start, new_start)
            records[end_index] = self._rescore_swapped(end, new_end)

    def _rescore_swapped(
        self,
        record: FieldRecord,
        value: PartialDate | PresentDate | None,
    ) -> FieldRecord:
        """Return ``record`` holding ``value`` with the repaired validation factor."""
        if value is None:
            return record

        confidence = self._scorer.score(
            base=record.confidence_parts.base,
            evidence=record.confidence_parts.evidence,
            validation=self._settings.repaired_validation_factor,
            mapping=record.confidence_parts.mapping,
        )

        return record.model_copy(
            update={
                "value": value,
                "confidence": confidence.confidence,
                "confidence_parts": confidence.parts,
                "normalization": RuleId.N_DATE_05,
                "extraction_status": confidence.status,
            }
        )

    # --- helpers ---------------------------------------------------------

    @staticmethod
    def _first_raw(
        candidates: list[CandidateValue], field: FieldName
    ) -> str | None:
        return next(
            (
                candidate.raw_value
                for candidate in candidates
                if candidate.entity is EntityType.PROFILE and candidate.field is field
            ),
            None,
        )

    @staticmethod
    def _rejection(
        candidate: CandidateValue, outcome: NormalizationOutcome
    ) -> RejectedValue:
        return RejectedValue(
            entity=candidate.entity,
            field=candidate.field,
            raw_value=candidate.raw_value,
            reason=outcome.rejected_by or RuleId.R_02,
            detail=outcome.detail,
        )


def _as_date(value: object) -> PartialDate | PresentDate | None:
    return value if isinstance(value, (PartialDate, PresentDate)) else None
