"""Rebuild a candidate's live profile from the stored field records (FR-036).

Used after a file is processed and after a reviewer decision, so the profile
always matches the field records (FR-063). Cross-source conflicts are
recomputed each time (FR-033); unchanged open conflicts keep their review item.
"""

from app.application.interfaces.processing_repository import IProcessingRepository
from app.application.services.profile_builder import ProfileBuilder, ProfileBuildResult
from app.domain.entities.field_record import is_cross_source
from app.domain.services.confidence import DEFAULT_REVIEW_CONFIDENCE


class ProfileRebuildService:

    def __init__(self, repository: IProcessingRepository,
                 confidence_threshold: float = DEFAULT_REVIEW_CONFIDENCE):
        self.repo = repository
        # Passed on to the builder, which needs it for the agreement boost
        # (M-04): a record two sources confirm can come back over the limit.
        self.confidence_threshold = confidence_threshold

    def rebuild(self, profile_id: int, trigger_file_id: int) -> ProfileBuildResult:
        records = self.repo.load_profile_field_records(profile_id)
        built = ProfileBuilder(confidence_threshold=self.confidence_threshold).build(
            records, include_field_reviews=False)
        if built.profile is not None:
            self.repo.replace_profile(profile_id, built.profile, records)

        conflicts = [i for i in built.review_items if is_cross_source(i.reasons)]
        self.repo.replace_open_reviews(profile_id, trigger_file_id, conflicts, {},
                                       conflicts_only=True)
        built.review_items = conflicts
        return built
