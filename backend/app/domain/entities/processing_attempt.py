from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class AttemptTrigger(str, Enum):
    FIRST_RUN = "first_run"
    AUTO_RETRY = "auto_retry"
    ADMIN_RERUN = "admin_rerun"   # recorded, but not counted toward the 3-try limit (FR-059)


class AttemptOutcome(str, Enum):
    VALID = "valid"               # LLM answered and the answer passed the schema
    INVALID = "invalid"           # LLM answered but the answer failed validation
    ERROR = "error"               # no usable answer (network, rate limit, bad key...)


@dataclass(frozen=True)
class ProcessingAttempt:
    """One processing try of a job (FR-058). Frozen: never changed after creation."""

    attempt_number: int
    trigger: AttemptTrigger
    provider: str
    model_version: str            # model that actually answered (NFR-035)
    started_at: datetime
    finished_at: datetime
    outcome: AttemptOutcome
    llm_response: str | None
    validation_result: dict[str, Any] | None
    error: str | None

    def to_dict(self) -> dict:
        data = asdict(self)
        data["trigger"] = self.trigger.value
        data["outcome"] = self.outcome.value
        data["started_at"] = self.started_at.isoformat()
        data["finished_at"] = self.finished_at.isoformat()
        return data


class AttemptLog:
    """Append-only list of attempts (FR-058, NFR-024): no update or delete."""

    def __init__(self) -> None:
        self._attempts: list[ProcessingAttempt] = []

    def append(self, attempt: ProcessingAttempt) -> None:
        self._attempts.append(attempt)

    @property
    def attempts(self) -> tuple[ProcessingAttempt, ...]:
        return tuple(self._attempts)

    @property
    def automatic_count(self) -> int:
        return sum(a.trigger != AttemptTrigger.ADMIN_RERUN for a in self._attempts)
