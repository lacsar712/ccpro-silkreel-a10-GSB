from datetime import date

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Basin, BathReading, Filature, StopSticker, User, utcnow
from app.services import RuleError


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
                selectinload(Filature.basins).selectinload(Basin.stop_stickers),
            )
        )
        return result.scalars().first()

    async def get(self, basin_id: int) -> Basin | None:
        result = await self.session.execute(
            select(Basin)
            .options(selectinload(Basin.readings), selectinload(Basin.stop_stickers))
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

    async def list(self, basin_id: int | None = None) -> list[StopSticker]:
        stmt = (
            select(StopSticker)
            .options(selectinload(StopSticker.basin))
            .order_by(StopSticker.id.desc())
        )
        if basin_id is not None:
            stmt = stmt.where(StopSticker.basin_id == basin_id)
        result = await self.session.execute(stmt)
        return list(result.scalars())

    async def get(self, sticker_id: int) -> StopSticker | None:
        result = await self.session.execute(
            select(StopSticker)
            .options(selectinload(StopSticker.basin))
            .where(StopSticker.id == sticker_id)
        )
        return result.scalar_one_or_none()

    async def create(self, basin: Basin, stop_date: date, posted_by: str) -> StopSticker:
        row = StopSticker(basin_id=basin.id, stop_date=stop_date, posted_by=posted_by)
        self.session.add(row)
        try:
            await self.session.commit()
        except IntegrityError:
            # 唯一部分索引兜底：并发贴同一盆时只留一版，后到者在此被挡
            await self.session.rollback()
            raise RuleError("该盆已有未作废的停缫止日贴纸，请先作废再贴")
        await self.session.refresh(row)
        row.basin = basin
        return row

    async def void(self, sticker: StopSticker) -> None:
        sticker.voided_at = utcnow()
        await self.session.commit()
