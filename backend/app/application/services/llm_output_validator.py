"""Validate an LLM answer against the extraction schema (FR-022, FR-025).

1. The answer must be JSON.
2. Any key that is not an allowed field name is dropped and reported
   (this is also how a protected trait such as "gender" would be removed).
3. What remains must match the schema exactly: required fields, types,
   allowed enum values, confidence between 0 and 1.

Only an answer that passes all three is used; otherwise the attempt is
recorded as invalid and retried (FR-023).
"""

import json
import types
import typing
from dataclasses import dataclass, field

from pydantic import BaseModel, ValidationError

from app.application.dto.cv_extraction import CVExtraction


@dataclass
class ValidationResult:
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    dropped_fields: list[str] = field(default_factory=list)
    extraction: CVExtraction | None = None

    def to_dict(self) -> dict:
        return {
            "is_valid": self.is_valid,
            "errors": self.errors,
            "dropped_fields": self.dropped_fields,
        }


def validate_llm_output(raw_text: str | None) -> ValidationResult:
    if not raw_text or not raw_text.strip():
        return ValidationResult(False, ["empty answer"])

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        return ValidationResult(False, [f"not valid JSON: {exc.msg} at position {exc.pos}"])

    if not isinstance(data, dict):
        return ValidationResult(False, ["top level must be a JSON object"])

    dropped: list[str] = []
    cleaned = _drop_disallowed(data, CVExtraction, "", dropped)

    try:
        extraction = CVExtraction.model_validate(cleaned)
    except ValidationError as exc:
        errors = [
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}"
            for err in exc.errors()
        ]
        return ValidationResult(False, errors, dropped)

    _clear_evidence_of_null_values(extraction)
    return ValidationResult(True, [], dropped, extraction)


def _drop_disallowed(data, model: type[BaseModel], path: str, dropped: list[str]):
    """Keep only keys the model defines; recurse into nested models and lists."""
    if not isinstance(data, dict):
        return data

    kept = {}
    for key, value in data.items():
        if key not in model.model_fields:
            dropped.append(f"{path}{key}")
            continue
        nested = _nested_model(model.model_fields[key].annotation)
        if nested is None:
            kept[key] = value
        elif isinstance(value, list):
            kept[key] = [
                _drop_disallowed(item, nested, f"{path}{key}[{i}].", dropped)
                for i, item in enumerate(value)
            ]
        else:
            kept[key] = _drop_disallowed(value, nested, f"{path}{key}.", dropped)
    return kept


def _nested_model(annotation) -> type[BaseModel] | None:
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    origin = typing.get_origin(annotation)
    if origin in (list, typing.Union, types.UnionType):
        for arg in typing.get_args(annotation):
            found = _nested_model(arg)
            if found:
                return found
    return None


def _clear_evidence_of_null_values(model: BaseModel) -> None:
    """A null value cannot have evidence; ignore any the LLM gave."""
    for name in type(model).model_fields:
        value = getattr(model, name)
        items = value if isinstance(value, list) else [value]
        for item in items:
            if isinstance(item, BaseModel):
                if "evidence" in type(item).model_fields and getattr(item, "value", 0) is None:
                    item.evidence = None
                    item.page = None
                else:
                    _clear_evidence_of_null_values(item)
