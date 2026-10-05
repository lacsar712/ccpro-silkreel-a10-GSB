from datetime import date

from quart import Quart, g, jsonify, request
from quart.helpers import make_response

from app.db import SessionLocal
from app.models import Basin
from app.repositories import BasinRepo, StickerRepo, UserRepo
from app.security import make_token, parse_token, verify_password
from app.services import (
    RuleError,
    active_sticker,
    assert_can_add_reading,
    assert_can_set_status,
    latest_temp,
    stop_date_passed,
)

app = Quart(__name__)


def _bearer() -> str | None:
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[7:]
    return None


@app.before_request
async def load_user():
    g.user = None
    token = _bearer()
    if not token:
        return
    username = parse_token(token)
    if not username:
        return
    async with SessionLocal() as session:
        g.user = await UserRepo(session).by_username(username)


def require_user():
    if g.user is None:
        return jsonify({"detail": "未登录"}), 401
    return None


def require_admin():
    denied = require_user()
    if denied:
        return denied
    if g.user.role != "admin":
        return jsonify({"detail": "仅管理员可贴与作废停缫止日贴纸"}), 403
    return None


@app.route("/api/health")
async def health():
    return {"status": "ok", "service": "SilkReel"}


@app.route("/api/auth/login", methods=["POST"])
async def login():
    body = await request.get_json(force=True)
    username = (body or {}).get("username", "")
    password = (body or {}).get("password", "")
    async with SessionLocal() as session:
        user = await UserRepo(session).by_username(username)
        if user is None or not verify_password(password, user.password_hash):
            return jsonify({"detail": "用户名或密码错误"}), 401
        return {
            "access_token": make_token(user.username),
            "user": {"username": user.username, "role": user.role},
        }


@app.route("/api/auth/me")
async def me():
    denied = require_user()
    if denied:
        return denied
    return {"username": g.user.username, "role": g.user.role}


def _sticker_json(sticker, today: date | None = None) -> dict:
    if today is None:
        today = date.today()
    return {
        "id": sticker.id,
        "basinId": sticker.basin_id,
        "stopDate": sticker.stop_date.isoformat(),
        "issuedBy": sticker.issued_by,
        "createdAt": sticker.created_at.isoformat() if sticker.created_at else None,
        "voidedAt": sticker.voided_at.isoformat() if sticker.voided_at else None,
        "passed": today > sticker.stop_date,
    }


def _basin_json(basin: Basin) -> dict:
    sticker = active_sticker(basin)
    today = date.today()
    return {
        "id": basin.id,
        "code": basin.code,
        "status": basin.status,
        "ringIndex": basin.ring_index,
        "latestTempC": latest_temp(basin),
        "readingCount": len(basin.readings or []),
        "stopDate": sticker.stop_date.isoformat() if sticker else None,
        "stopDatePassed": stop_date_passed(sticker, today),
    }


@app.route("/api/board")
async def board():
    denied = require_user()
    if denied:
        return denied
    async with SessionLocal() as session:
        mill = await BasinRepo(session).board()
        if mill is None:
            return jsonify({"detail": "尚无缫丝坞"}), 404
        basins = sorted(mill.basins, key=lambda b: b.ring_index)
        return {
            "filature": mill.name,
            "riverside": mill.riverside,
            "serverDate": date.today().isoformat(),
            "basins": [_basin_json(b) for b in basins],
        }


@app.route("/api/basins/<int:basin_id>/readings", methods=["POST"])
async def add_reading(basin_id: int):
    denied = require_user()
    if denied:
        return denied
    body = await request.get_json(force=True)
    try:
        temp = float((body or {}).get("waterTempC"))
    except (TypeError, ValueError):
        return jsonify({"detail": "汤温必须是数字"}), 400
    async with SessionLocal() as session:
        repo = BasinRepo(session)
        basin = await repo.get(basin_id)
        if basin is None:
            return jsonify({"detail": "盆不存在"}), 404
        try:
            # 保存汤温时实时读取该盆未作废的止日；已过则挡住且不入库。
            assert_can_add_reading(basin)
        except RuleError as exc:
            return jsonify({"detail": str(exc)}), 400
        await repo.add_reading(basin, temp, g.user.username)
        basin = await repo.get(basin_id)
        return _basin_json(basin)


@app.route("/api/basins/<int:basin_id>/status", methods=["POST"])
async def set_status(basin_id: int):
    denied = require_user()
    if denied:
        return denied
    body = await request.get_json(force=True)
    status = (body or {}).get("status", "")
    async with SessionLocal() as session:
        repo = BasinRepo(session)
        basin = await repo.get(basin_id)
        if basin is None:
            return jsonify({"detail": "盆不存在"}), 404
        try:
            # 止日只管汤温登记，不改盆态：已缫完的 38～42℃ 校验原样保留。
            assert_can_set_status(basin, status)
        except RuleError as exc:
            return jsonify({"detail": str(exc)}), 400
        await repo.save_status(basin, status)
        basin = await repo.get(basin_id)
        return _basin_json(basin)


@app.route("/api/stickers")
async def list_stickers():
    denied = require_user()
    if denied:
        return denied
    basin_id = request.args.get("basin_id", type=int)
    async with SessionLocal() as session:
        stickers = await StickerRepo(session).list(basin_id)
        mill = await BasinRepo(session).board()
        basins = sorted(mill.basins, key=lambda b: b.ring_index) if mill else []
        today = date.today()
        return {
            "serverDate": today.isoformat(),
            "basins": [{"id": b.id, "code": b.code} for b in basins],
            "stickers": [_sticker_json(s, today) for s in stickers],
        }


@app.route("/api/stickers", methods=["POST"])
async def create_sticker():
    denied = require_admin()
    if denied:
        return denied
    body = await request.get_json(force=True) or {}
    basin_id = body.get("basinId")
    raw_date = body.get("stopDate", "")
    try:
        basin_id = int(basin_id)
    except (TypeError, ValueError):
        return jsonify({"detail": "必须指定盆"}), 400
    try:
        stop_date = date.fromisoformat(str(raw_date))
    except ValueError:
        return jsonify({"detail": "止日必须是 YYYY-MM-DD 日历日期"}), 400
    async with SessionLocal() as session:
        repo = StickerRepo(session)
        basin, sticker = await repo.create(basin_id, stop_date, g.user.username)
        if basin is None:
            return jsonify({"detail": "盆不存在"}), 404
        return _sticker_json(sticker)


@app.route("/api/stickers/<int:sticker_id>/void", methods=["POST"])
async def void_sticker(sticker_id: int):
    denied = require_admin()
    if denied:
        return denied
    async with SessionLocal() as session:
        sticker, changed = await StickerRepo(session).void(sticker_id)
        if sticker is None:
            return jsonify({"detail": "贴纸不存在"}), 404
        if not changed:
            return jsonify({"detail": "贴纸已作废，请勿重复操作"}), 400
        return _sticker_json(sticker)
