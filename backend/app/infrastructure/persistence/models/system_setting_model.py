from datetime import datetime

from sqlalchemy import TIMESTAMP, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.persistence.db.base import Base


class SystemSettingModel(Base):
    """A setting an administrator can change at runtime (FR-046, FR-067).

    Stored rather than read from the environment, so changing the review limit
    does not need a redeploy and so the change is attributable. The limit a
    job used is recorded on that job, so a change applies to later jobs only.
    """

    __tablename__ = "system_setting"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # FR-067: null until an administrator changes it from the seeded default.
    updated_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("app_user.user_id", ondelete="SET NULL")
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default=func.now()
    )
