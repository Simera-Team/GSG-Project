"""Tunable settings for the AI module.

These are the knobs the contract calls ``AISettings``. They are plain data with
contract defaults rather than environment-bound settings, so the module stays
independent of process configuration and every job can record the exact values
it ran under (FR-067, NFR-023).
"""

from pydantic import BaseModel, ConfigDict, Field

from app.application.ai.rules import RULE_VERSION


class AISettings(BaseModel):
    """Thresholds, factor values and attempt limits for one extraction job."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    # --- Confidence model ------------------------------------------------
    confidence_threshold: float = Field(
        default=0.65,
        ge=0,
        le=1,
        description="Below this a field is marked low_confidence and goes to review (R-06).",
    )

    evidence_fuzzy_high_similarity: float = Field(
        default=0.90,
        ge=0,
        le=1,
        description="Similarity at or above this counts as a fuzzy_high evidence match.",
    )
    evidence_fuzzy_low_similarity: float = Field(
        default=0.75,
        ge=0,
        le=1,
        description="Similarity below this rejects the value (R-03).",
    )
    evidence_fuzzy_high_factor: float = Field(default=0.85, ge=0, le=1)
    evidence_fuzzy_low_factor: float = Field(default=0.60, ge=0, le=1)

    repaired_validation_factor: float = Field(
        default=0.80,
        ge=0,
        le=1,
        description="Validation factor for a value that passed after a deterministic repair.",
    )
    fuzzy_mapping_factor: float = Field(
        default=0.85,
        ge=0,
        le=1,
        description="Mapping factor for a fuzzy alias or city match.",
    )
    agreement_boost: float = Field(
        default=0.05,
        ge=0,
        le=1,
        description="Added once when two or more sources agree on a value (M-04).",
    )

    # --- Entity matching -------------------------------------------------
    entity_name_similarity: float = Field(
        default=0.90,
        ge=0,
        le=1,
        description="Name similarity at or above this makes two entities one (M-01).",
    )

    # --- LLM call policy -------------------------------------------------
    max_provider_attempts: int = Field(
        default=3,
        ge=1,
        description="Attempts on a provider timeout or rate limit; those spend few tokens.",
    )
    max_invalid_output_attempts: int = Field(
        default=2,
        ge=1,
        description=(
            "Attempts when the answer fails schema validation (R-01); each one "
            "costs a full call."
        ),
    )
    reuse_llm_results: bool = Field(
        default=False,
        description=(
            "Reuse a saved result for the same file hash (FR-024). Off while "
            "the prompt is still changing."
        ),
    )

    # --- Free-text limits from the field catalogue -----------------------
    max_headline_length: int = Field(default=120, ge=1)
    max_summary_length: int = Field(default=1_000, ge=1)

    # --- Provenance ------------------------------------------------------
    rule_version: str = Field(
        default=RULE_VERSION,
        description="Rule-set version recorded on the job for reproducibility.",
    )
