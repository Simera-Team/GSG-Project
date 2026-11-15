"""Human review of flagged fields and failed jobs (FR-041 - FR-044, FR-062, FR-066).

A decision never edits the profile directly. It is saved as a new field
record (rule "review_decision", confidence 1.0) next to the flagged one, and
the profile is rebuilt from the field records (FR-036, FR-063). So every
profile value - including reviewed ones - traces back to a field record, and
the flagged original stays in the audit trail.

Decisions:
  option  - pick one of the item's values (FR-043)
  custom  - type a corrected value (FR-043)
  reject  - no value is correct; the field stays empty
  dismiss - close a failed-job item (it has no field)
A typed or picked value goes through the same rules as extracted values:
dates (FR-028), country list (FR-070), skill names (FR-029 / FR-062).
"""

import json
import re

from app.application.dto.review_views import ReviewItemView, ReviewOptionView
from app.application.interfaces.processing_repository import (
    ICatalogRepository,
    IProcessingRepository,
)
from app.application.interfaces.review_repository import IReviewRepository
from app.application.interfaces.unit_of_work import IUnitOfWork
from app.application.services.profile_rebuild_service import ProfileRebuildService
from app.core.exceptions import ReviewInputError, ReviewNotFoundError, ReviewStateError
from app.domain.entities.user import User
from app.domain.services.dates import parse_date
from app.domain.services.skills import clean_skill_name

ACTIONS = {"option", "custom", "reject", "dismiss"}
RESOLUTION = {"option": "option", "custom": "custom", "reject": "rejected", "dismiss": "dismissed"}
DATE_FIELDS = {"start_date", "end_date", "issue_date"}
PROFICIENCY = {"native", "fluent", "intermediate", "basic"}
EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+(\.[\w-]+)+$")


class ReviewService:

    def __init__(self, reviews: IReviewRepository, processing: IProcessingRepository,
                 catalogs: ICatalogRepository, unit_of_work: IUnitOfWork):
        self.reviews = reviews
        self.processing = processing
        self.catalogs = catalogs
        self.uow = unit_of_work

    # ---- queue (FR-041, FR-042) ----

    def list_items(self, status: str = "open", reason: str | None = None,
                   profile_id: int | None = None, limit: int = 50, offset: int = 0):
        return self.reviews.list_items(status, reason, profile_id, limit, offset)

    def get_item(self, review_id: int) -> ReviewItemView:
        item = self.reviews.get_item(review_id)
        if item is None:
            raise ReviewNotFoundError(f"Review item {review_id} does not exist")
        return item

    # ---- decisions (FR-043, FR-066) ----

    def resolve(self, review_id: int, reviewer: User, action: str,
                option_id: int | None = None, value: str | None = None,
                map_to_skill: str | None = None) -> ReviewItemView:
        try:
            item = self._open_item(review_id, lock=True)
            self._check_action(item, action, option_id, value, map_to_skill)

            if action == "dismiss":
                self.reviews.mark_resolved(review_id, "dismissed", None, None, None,
                                           reviewer.user_id)
                self.uow.commit()
                return self.get_item(review_id)

            option = self._option(item, option_id) if action == "option" else None
            raw = option.value if option else (value.strip() if action == "custom" else None)
            source_field = self.reviews.get_field(
                option.field_id if option and option.field_id
                else next((o.field_id for o in item.options if o.field_id), 0) or 0)

            entity_type = item.entity.split("[")[0]
            normalised = None if raw is None else self._normalise(
                entity_type, item.field_name, raw, source_field.value if source_field else None,
                map_to_skill)

            file_id = option.file_id if option else item.file_id
            attempt_id = (source_field.attempt_id if source_field and source_field.file_id == file_id
                          else self.reviews.latest_valid_attempt_id(file_id))
            if attempt_id is None:
                raise ReviewStateError("The source file has no valid extraction to attach the "
                                       "decision to; re-run the file first")

            decision_id = self.reviews.add_decision_field(
                file_id=file_id, attempt_id=attempt_id, entity=item.entity,
                entity_type=entity_type, field_name=item.field_name, raw_value=raw,
                value=normalised, evidence=option.evidence if option else None,
                page=option.page if option else None)
            self.reviews.mark_resolved(review_id, RESOLUTION[action],
                                       option.option_id if option else None,
                                       _as_text(normalised), decision_id, reviewer.user_id)

            # FR-037: profile column changes are logged by the database trigger
            # with this reviewer and reason; other fields are logged here.
            self.processing.set_change_context(reviewer.user_id, "review_decision", file_id)
            ProfileRebuildService(self.processing).rebuild(item.profile_id, item.file_id)
            if entity_type != "personal_info":
                old = item.options[0].value if item.options else None
                self.reviews.log_change(item.profile_id, file_id,
                                        f"{item.entity}.{item.field_name}", old,
                                        _as_text(normalised), reviewer.user_id, "review_decision")

            self.uow.commit()
        except Exception:
            self.uow.rollback()
            raise
        return self.get_item(review_id)

    # ---- FR-044: leave unresolved and ask the candidate ----

    def request_candidate(self, review_id: int, reviewer: User) -> ReviewItemView:
        try:
            self._open_item(review_id, lock=True)
            self.reviews.mark_sent_to_candidate(review_id)
            self.uow.commit()
        except Exception:
            self.uow.rollback()
            raise
        return self.get_item(review_id)

    # ---- helpers ----

    def _open_item(self, review_id: int, lock: bool) -> ReviewItemView:
        item = self.reviews.get_item(review_id, lock=lock)
        if item is None:
            raise ReviewNotFoundError(f"Review item {review_id} does not exist")
        if item.resolved:
            raise ReviewStateError(f"Review item {review_id} is already resolved")
        return item

    @staticmethod
    def _check_action(item, action, option_id, value, map_to_skill) -> None:
        if action not in ACTIONS:
            raise ReviewInputError(f"action must be one of: {', '.join(sorted(ACTIONS))}")
        if item.is_failed_job and action != "dismiss":
            raise ReviewInputError("A failed job has no field to decide: use 'dismiss' "
                                   "(an administrator can re-run the file)")
        if not item.is_failed_job and action == "dismiss":
            raise ReviewInputError("'dismiss' is only for failed jobs; use 'reject' to leave "
                                   "the field empty")
        if action == "option" and option_id is None:
            raise ReviewInputError("option_id is required for action 'option'")
        if action == "custom" and not (value and value.strip()):
            raise ReviewInputError("value is required for action 'custom'")
        if map_to_skill and not (item.entity or "").startswith("skills"):
            raise ReviewInputError("map_to_skill is only for skill items")

    @staticmethod
    def _option(item: ReviewItemView, option_id: int) -> ReviewOptionView:
        for option in item.options:
            if option.option_id == option_id:
                return option
        raise ReviewInputError(f"Option {option_id} does not belong to review item "
                               f"{item.review_id}")

    def _normalise(self, entity_type, field_name, raw: str, original_value, map_to_skill):
        """Apply the same rules as for extracted values; invalid input -> 422."""
        if raw is None or raw == "":
            return None

        if field_name in DATE_FIELDS:
            result = parse_date(raw)
            if result.kind == "date":
                return result.date.to_dict()
            if result.kind == "current" and field_name == "end_date":
                return "current"
            raise ReviewInputError(f"'{raw}' is not a date; use e.g. 2022, 03/2022 or March 2022")

        if entity_type == "personal_info" and field_name == "country":
            country = self.catalogs.country_catalog().match(raw)
            if not country:
                raise ReviewInputError(f"'{raw}' is not in the country list; an administrator "
                                       "must add it first")
            return country.to_dict()

        if entity_type == "skills" and field_name == "name":
            skills = self.catalogs.skill_catalog()
            if map_to_skill:                              # FR-062: map to an existing skill
                standard = skills.lookup(map_to_skill)
                if not standard:
                    raise ReviewInputError(f"'{map_to_skill}' is not a standard skill")
                if raw.strip().casefold() != standard.casefold():
                    self.reviews.add_skill_alias(raw.strip().casefold(), standard)
                return standard
            # FR-062: approve as a new standard skill (or reuse an existing one)
            return skills.lookup(raw) or self.reviews.ensure_skill(clean_skill_name(raw))

        if field_name == "email" and not EMAIL_RE.match(raw):
            raise ReviewInputError(f"'{raw}' is not a valid e-mail address")
        if field_name == "proficiency":
            if raw.lower() not in PROFICIENCY:
                raise ReviewInputError(f"proficiency must be one of: {', '.join(sorted(PROFICIENCY))}")
            return raw.lower()
        if field_name == "is_current":
            if raw.lower() not in ("true", "false"):
                raise ReviewInputError("is_current must be true or false")
            return raw.lower() == "true"
        if entity_type == "links" and field_name == "url":
            link_type = original_value.get("type") if isinstance(original_value, dict) else "other"
            url = raw if isinstance(raw, str) else str(raw)
            if url.startswith("{"):                       # option stored as JSON
                url = json.loads(url).get("url", url)
            return {"type": link_type, "url": url}
        return raw


def _as_text(value) -> str | None:
    if value is None or isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)
