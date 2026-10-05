from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Basin, BathReading, Filature, StopDateSticker, User, utcnow


class UserRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def by_username(self, username: str) -> User | None:
        result = await self.session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()


class BasinRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def board(self) -> Filature | None:
        result = await self.session.execute(
            select(Filature).options(
                selectinload(Filature.basins).selectinload(Basin.readings),
                selectinload(Filature.basins).selectinload(Basin.stickers),
            )
        )
        return result.scalars().first()

    async def get(self, basin_id: int) -> Basin | None:
        result = await self.session.execute(
            select(Basin)
            .options(selectinload(Basin.readings), selectinload(Basin.stickers))
            .where(Basin.id == basin_id)
        )
        return result.scalar_one_or_none()

    async def add_reading(self, basin: Basin, temp_c: float, operator: str) -> BathReading:
        row = BathReading(basin=basin, water_temp_c=temp_c, operator=operator)
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def save_status(self, basin: Basin, status: str) -> None:
        basin.status = status
        await self.session.commit()


class StickerRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list(self, basin_id: int | None = None) -> list[StopDateSticker]:
        stmt = select(StopDateSticker).order_by(
            StopDateSticker.basin_id, StopDateSticker.id.desc()
        )
        if basin_id is not None:
            stmt = stmt.where(StopDateSticker.basin_id == basin_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def _lock_basin(self, basin_id: int) -> Basin | None:
        """锁住盆行，把同一盆贴纸的新贴/作废串行化。"""
        result = await self.session.execute(
            select(Basin).where(Basin.id == basin_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def active_for_basin(self, basin_id: int) -> StopDateSticker | None:
        result = await self.session.execute(
            select(StopDateSticker)
            .where(StopDateSticker.basin_id == basin_id, StopDateSticker.voided_at.is_(None))
            .with_for_update()
        )
        return result.scalars().first()

    async def create(self, basin_id: int, stop_date, issued_by: str) -> tuple[Basin | None, StopDateSticker]:
        """贴一张新止日；同盆已有未作废贴纸则旧版当场作废，只留新版一版。"""
        basin = await self._lock_basin(basin_id)
        if basin is None:
            return None, None
        active = await self.active_for_basin(basin_id)
        if active is not None:
            active.voided_at = utcnow()
        sticker = StopDateSticker(
            basin_id=basin_id, stop_date=stop_date, issued_by=issued_by
        )
        self.session.add(sticker)
        await self.session.commit()
        await self.session.refresh(sticker)
        return basin, sticker

    async def void(self, sticker_id: int) -> tuple[StopDateSticker | None, bool]:
        result = await self.session.execute(
            select(StopDateSticker)
            .where(StopDateSticker.id == sticker_id)
            .with_for_update()
        )
        sticker = result.scalar_one_or_none()
        if sticker is None or sticker.voided_at is not None:
            return sticker, False
        sticker.voided_at = utcnow()
        await self.session.commit()
        await self.session.refresh(sticker)
        return sticker, True
