"""Orchestrates the merge stages: match entities, then resolve each field.

Kept separate from the extraction pipeline because the two run at different
times and over different inputs. Extraction runs once per uploaded file;
merging runs over every source a candidate has, whenever one of them changes.
"""

from collections.abc import Sequence

from app.application.ai.conflict_resolution.conflict_resolver import ConflictResolver
from app.application.ai.conflict_resolution.field_policy import POLICY_VERSION
from app.application.ai.matching.entity_matcher import EntityMatcher
from app.application.ai.schemas.merge import MergeResult, SourceExtraction
from app.application.ai.settings import AISettings


class MergePipeline:
    """Builds one candidate's merged field set from all of their sources."""

    def __init__(
        self,
        matcher: EntityMatcher,
        resolver: ConflictResolver,
        settings: AISettings | None = None,
    ) -> None:
        self._matcher = matcher
        self._resolver = resolver
        self._settings = settings or AISettings()

    def merge(self, extractions: Sequence[SourceExtraction]) -> MergeResult:
        """Return the resolved fields and the conflicts left for a person.

        The rule and policy versions are recorded on the result so an old
        decision stays explainable after the rules change (NFR-023).
        """
        result = MergeResult(
            rule_version=self._settings.rule_version,
            policy_version=POLICY_VERSION,
        )

        for entity in self._matcher.match(extractions):
            resolved, conflicts = self._resolver.resolve(entity)
            result.resolved.extend(resolved)
            result.conflicts.extend(conflicts)

        return result
