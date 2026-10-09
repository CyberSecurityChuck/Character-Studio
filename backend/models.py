from sqlalchemy import CheckConstraint, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class StudioPreferences(Base):
    __tablename__ = "studio_preferences"
    __table_args__ = (CheckConstraint("id = 1", name="singleton_preferences"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    studio_name: Mapped[str] = mapped_column(String(60), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
