"""Reads and writes the settings an administrator controls (FR-046, FR-067)."""

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.persistence.models.system_setting_model import SystemSettingModel

#: Key of the limit below which a field goes to review.
CONFIDENCE_THRESHOLD_KEY = "review_confidence_threshold"

#: Used when the table has no row yet, so a fresh database behaves the same as
#: a migrated one.
DEFAULT_CONFIDENCE_THRESHOLD = 0.65


@dataclass(frozen=True)
class SettingView:
    key: str
    value: str
    description: str | None
    updated_by: int | None
    updated_at: datetime | None


class SqlSettingsRepository:

    def __init__(self, db: Session):
        self.db = db

    def confidence_threshold(self) -> float:
        """The review limit in force now, or the default when none is stored.

        A stored value that is not a number between 0 and 1 is ignored in
        favour of the default: a job must never run with a limit that would
        send everything, or nothing, to review.
        """
        row = self.db.get(SystemSettingModel, CONFIDENCE_THRESHOLD_KEY)
        if row is None:
            return DEFAULT_CONFIDENCE_THRESHOLD
        try:
            value = float(row.value)
        except (TypeError, ValueError):
            return DEFAULT_CONFIDENCE_THRESHOLD
        return value if 0.0 <= value <= 1.0 else DEFAULT_CONFIDENCE_THRESHOLD

    def set_confidence_threshold(self, value: float, user_id: int | None) -> SettingView:
        """Change the limit, recording who did it and when (FR-067).

        Jobs already finished keep the limit they ran under, because each job
        stores it on its attempts; the new limit applies to later jobs only.
        """
        if not 0.0 <= value <= 1.0:
            raise ValueError("The confidence limit must be between 0 and 1")

        row = self.db.get(SystemSettingModel, CONFIDENCE_THRESHOLD_KEY)
        if row is None:
            row = SystemSettingModel(
                key=CONFIDENCE_THRESHOLD_KEY,
                description="Fields the extraction is less sure of than this "
                            "go to review (FR-046)",
            )
            self.db.add(row)

        row.value = repr(float(value))
        row.updated_by = user_id
        row.updated_at = datetime.now(timezone.utc)
        self.db.flush()
        return _view(row)

    def list_settings(self) -> list[SettingView]:
        rows = self.db.scalars(
            select(SystemSettingModel).order_by(SystemSettingModel.key)
        ).all()
        return [_view(r) for r in rows]


def _view(row: SystemSettingModel) -> SettingView:
    return SettingView(row.key, row.value, row.description,
                       row.updated_by, row.updated_at)
