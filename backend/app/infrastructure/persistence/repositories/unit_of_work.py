
from sqlalchemy.orm import Session

from app.application.interfaces.unit_of_work import IUnitOfWork


class SqlAlchemyUnitOfWork(IUnitOfWork):

    def __init__(self, db: Session):
        self.db = db

    def commit(self) -> None:
        self.db.commit()

    def rollback(self) -> None:
        self.db.rollback()
