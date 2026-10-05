"""缫丝盆门槛：

* 标成已缫完须最近一次汤温落在 38～42℃；
* 盆上贴有未作废的停缫止日贴纸，且服务器自然日已晚于止日时，禁止再登记汤温。
"""

from datetime import date

from app.models import Basin, StopDateSticker

MIN_TEMP = 38.0
MAX_TEMP = 42.0


class RuleError(ValueError):
    pass


def latest_temp(basin: Basin) -> float | None:
    if not basin.readings:
        return None
    latest = max(basin.readings, key=lambda r: r.taken_at)
    return latest.water_temp_c


def active_sticker(basin: Basin) -> StopDateSticker | None:
    """该盆当前未作废的止日贴纸；正常情况下至多一张。"""
    active = [s for s in (basin.stickers or []) if s.voided_at is None]
    if not active:
        return None
    return max(active, key=lambda s: (s.created_at, s.id))


def stop_date_passed(sticker: StopDateSticker | None, today: date | None = None) -> bool:
    if sticker is None:
        return False
    if today is None:
        today = date.today()
    return today > sticker.stop_date


def assert_can_add_reading(basin: Basin, today: date | None = None) -> None:
    sticker = active_sticker(basin)
    if stop_date_passed(sticker, today):
        raise RuleError(
            f"该盆停缫止日为{sticker.stop_date:%Y年%m月%d日}，"
            f"今日已过止日，禁止再登记汤温"
        )


def assert_can_set_status(basin: Basin, new_status: str) -> None:
    allowed = {Basin.STATUS_SOAKING, Basin.STATUS_REELING, Basin.STATUS_REELED}
    if new_status not in allowed:
        raise RuleError(f"无效状态：{new_status}")
    if new_status != Basin.STATUS_REELED:
        return
    temp = latest_temp(basin)
    if temp is None:
        raise RuleError("该盆尚无汤温记录，不能标已缫完")
    if temp < MIN_TEMP or temp > MAX_TEMP:
        raise RuleError(
            f"最近汤温 {temp}℃ 不在 {MIN_TEMP:.0f}～{MAX_TEMP:.0f}℃，不能标已缫完"
        )
