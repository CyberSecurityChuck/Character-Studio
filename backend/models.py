from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class StudioPreferences(Base):
    __tablename__ = "studio_preferences"
    __table_args__ = (CheckConstraint("id = 1", name="singleton_preferences"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    studio_name: Mapped[str] = mapped_column(String(60), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)


class Character(Base):
    __tablename__ = "characters"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    age_category: Mapped[str] = mapped_column(String(10))
    notes: Mapped[str] = mapped_column(Text)
    primary_photo_id: Mapped[str | None] = mapped_column(String(32))
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class ReferencePhoto(Base):
    __tablename__ = "reference_photos"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    character_id: Mapped[str] = mapped_column(ForeignKey("characters.id"), index=True)
    label: Mapped[str] = mapped_column(String(30))
    original_path: Mapped[str] = mapped_column(String(100))
    thumbnail_path: Mapped[str] = mapped_column(String(100))
    media_type: Mapped[str] = mapped_column(String(20))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(String(40))


class CharacterGroup(Base):
    __tablename__ = "character_groups"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class GroupMember(Base):
    __tablename__ = "group_members"
    group_id: Mapped[str] = mapped_column(ForeignKey("character_groups.id"), primary_key=True)
    character_id: Mapped[str] = mapped_column(ForeignKey("characters.id"), primary_key=True)


class PendingFileDeletion(Base):
    __tablename__ = "pending_file_deletions"
    path: Mapped[str] = mapped_column(String(100), primary_key=True)
