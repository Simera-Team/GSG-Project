from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.interfaces.processing_repository import ICatalogRepository
from app.domain.services.countries import CountryCatalog
from app.domain.services.skills import SkillCatalog
from app.infrastructure.persistence.models import CountryModel, SkillAliasModel, SkillModel


class SqlCatalogRepository(ICatalogRepository):
    """Loads the country and skill lists from the database, so changes made
    by the administrator apply to the next job."""

    def __init__(self, db: Session):
        self.db = db

    def country_catalog(self) -> CountryCatalog:
        rows = self.db.execute(select(CountryModel.country_name, CountryModel.country_code)).all()
        return CountryCatalog([(name, code) for name, code in rows])

    def skill_catalog(self) -> SkillCatalog:
        names = self.db.scalars(select(SkillModel.canonical_name)).all()
        aliases = self.db.execute(
            select(SkillAliasModel.alias_name, SkillModel.canonical_name)
            .join(SkillModel, SkillModel.skill_id == SkillAliasModel.skill_id)
        ).all()
        return SkillCatalog(names, {alias: name for alias, name in aliases})
