from datetime import date, timedelta

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Basin, BathReading, Filature, StopDateSticker, User, utcnow
from app.security import hash_password


async def seed_demo() -> None:
    async with SessionLocal() as session:
        existing = await session.execute(select(User).where(User.username == "admin"))
        admin = existing.scalar_one_or_none()
        if admin is None:
            admin = User(username="admin", password_hash=hash_password("123456"), role="admin")
            session.add(admin)
        else:
            admin.password_hash = hash_password("123456")
            admin.role = "admin"

        existing_w = await session.execute(select(User).where(User.username == "worker"))
        worker = existing_w.scalar_one_or_none()
        if worker is None:
            session.add(User(username="worker", password_hash=hash_password("123456"), role="worker"))
        else:
            worker.password_hash = hash_password("123456")
            worker.role = "worker"

        mill = (await session.execute(select(Filature))).scalars().first()
        if mill is None:
            mill = Filature(name="江口缫丝坞", riverside="东津渡")
            session.add(mill)
            await session.flush()
            now = utcnow()
            specs = [
                ("甲-1", Basin.STATUS_REELING, 40.5, 0),
                ("甲-2", Basin.STATUS_SOAKING, None, 1),
                ("乙-1", Basin.STATUS_REELED, 39.2, 2),
                ("乙-2", Basin.STATUS_REELING, 36.0, 3),
                ("丙-1", Basin.STATUS_SOAKING, None, 4),
                ("丙-2", Basin.STATUS_REELED, 41.0, 5),
            ]
            for code, status, temp, idx in specs:
                basin = Basin(filature_id=mill.id, code=code, status=status, ring_index=idx)
                session.add(basin)
                await session.flush()
                if temp is not None:
                    session.add(
                        BathReading(
                            basin_id=basin.id,
                            water_temp_c=temp,
                            operator="worker",
                            taken_at=now - timedelta(hours=2),
                        )
                    )

        await session.flush()
        # 乙-2 恒有一张昨日止日的停缫贴纸（盆位仍可点，但保存汤温会被挡）。
        yi2 = (
            await session.execute(select(Basin).where(Basin.code == "乙-2"))
        ).scalar_one_or_none()
        if yi2 is not None:
            yesterday = date.today() - timedelta(days=1)
            has_active = (
                await session.execute(
                    select(StopDateSticker.id).where(
                        StopDateSticker.basin_id == yi2.id,
                        StopDateSticker.voided_at.is_(None),
                    )
                )
            ).first()
            if has_active is None:
                session.add(
                    StopDateSticker(
                        basin_id=yi2.id, stop_date=yesterday, issued_by="admin"
                    )
                )
        await session.commit()
