"""缫丝盆门槛：标成已缫完须最近一次汤温落在 38～42℃；止日已过禁止再登汤温。"""

from datetime import date, datetime

from app.models import Basin, StopSticker

MIN_TEMP = 38.0
MAX_TEMP = 42.0


class RuleError(ValueError):
    pass


def server_today() -> date:
    """服务器自然日，按服务器本地日历。"""
    return datetime.now().date()


def active_sticker(basin: Basin) -> StopSticker | None:
    """该盆当前未作废的停缫止日贴纸，没有则为 None。"""
    for sticker in basin.stop_stickers or []:
        if sticker.voided_at is None:
            return sticker
    return None


def assert_can_add_reading(basin: Basin, today: date) -> None:
    """服务器自然日晚于止日后，该盆禁止再登记汤温；未贴纸不拦。"""
    sticker = active_sticker(basin)
    if sticker is None:
        return
    if today > sticker.stop_date:
        raise RuleError(
            f"该盆停缫止日为 {sticker.stop_date.isoformat()}，今日 {today.isoformat()} 已过止日，禁止登记汤温"
        )


def latest_temp(basin: Basin) -> float | None:
    if not basin.readings:
        return None
    latest = max(basin.readings, key=lambda r: r.taken_at)
    return latest.water_temp_c


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
