from datetime import date, datetime, timezone

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(20), default="worker")


class Filature(Base):
    __tablename__ = "filatures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    riverside: Mapped[str] = mapped_column(String(120), default="")
    basins: Mapped[list["Basin"]] = relationship(back_populates="filature")


class Basin(Base):
    __tablename__ = "basins"
    __table_args__ = (UniqueConstraint("filature_id", "code"),)

    STATUS_SOAKING = "soaking"
    STATUS_REELING = "reeling"
    STATUS_REELED = "reeled"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filature_id: Mapped[int] = mapped_column(ForeignKey("filatures.id"))
    code: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default=STATUS_SOAKING)
    ring_index: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str] = mapped_column(Text, default="")
    filature: Mapped[Filature] = relationship(back_populates="basins")
    readings: Mapped[list["BathReading"]] = relationship(back_populates="basin")
    stop_stickers: Mapped[list["StopSticker"]] = relationship(back_populates="basin")


class BathReading(Base):
    __tablename__ = "bath_readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    basin_id: Mapped[int] = mapped_column(ForeignKey("basins.id"))
    taken_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    water_temp_c: Mapped[float] = mapped_column(Float)
    operator: Mapped[str] = mapped_column(String(64), default="")
    basin: Mapped[Basin] = relationship(back_populates="readings")


class StopSticker(Base):
    """停缫止日贴纸：同一盆未作废的最多一张（数据库部分唯一索引兜底并发）。"""

    __tablename__ = "stop_stickers"
    __table_args__ = (
        Index(
            "uq_stop_stickers_active_basin",
            "basin_id",
            unique=True,
            sqlite_where=text("voided_at IS NULL"),
            postgresql_where=text("voided_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    basin_id: Mapped[int] = mapped_column(ForeignKey("basins.id"))
    stop_date: Mapped[date] = mapped_column(Date)
    posted_by: Mapped[str] = mapped_column(String(64))
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    basin: Mapped[Basin] = relationship(back_populates="stop_stickers")
