from datetime import date

from quart import Quart, g, jsonify, request
from quart.helpers import make_response

from app.db import SessionLocal
from app.models import Basin, StopSticker
from app.repositories import BasinRepo, StickerRepo, UserRepo
from app.security import make_token, parse_token, verify_password
from app.services import (
    RuleError,
    active_sticker,
    assert_can_add_reading,
    assert_can_set_status,
    latest_temp,
    server_today,
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
        return jsonify({"detail": "仅管理员可贴或作废停缫止日"}), 403
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


def _basin_json(basin: Basin) -> dict:
    sticker = active_sticker(basin)
    return {
        "id": basin.id,
        "code": basin.code,
        "status": basin.status,
        "ringIndex": basin.ring_index,
        "latestTempC": latest_temp(basin),
        "readingCount": len(basin.readings or []),
        "stopDate": sticker.stop_date.isoformat() if sticker else None,
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
            assert_can_add_reading(basin, server_today())
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
            assert_can_set_status(basin, status)
        except RuleError as exc:
            return jsonify({"detail": str(exc)}), 400
        await repo.save_status(basin, status)
        basin = await repo.get(basin_id)
        return _basin_json(basin)


def _sticker_json(sticker: StopSticker) -> dict:
    return {
        "id": sticker.id,
        "basinId": sticker.basin_id,
        "basinCode": sticker.basin.code if sticker.basin else "",
        "stopDate": sticker.stop_date.isoformat(),
        "postedBy": sticker.posted_by,
        "postedAt": sticker.posted_at.isoformat() if sticker.posted_at else None,
        "voidedAt": sticker.voided_at.isoformat() if sticker.voided_at else None,
    }


@app.route("/api/stop-stickers")
async def list_stickers():
    denied = require_user()
    if denied:
        return denied
    basin_id = request.args.get("basinId", type=int)
    async with SessionLocal() as session:
        stickers = await StickerRepo(session).list(basin_id)
        return {"stickers": [_sticker_json(s) for s in stickers]}


@app.route("/api/stop-stickers", methods=["POST"])
async def create_sticker():
    denied = require_admin()
    if denied:
        return denied
    body = await request.get_json(force=True)
    basin_id = (body or {}).get("basinId")
    raw_date = (body or {}).get("stopDate", "")
    try:
        stop_date = date.fromisoformat(str(raw_date))
    except ValueError:
        return jsonify({"detail": "止日格式应为 YYYY-MM-DD"}), 400
    async with SessionLocal() as session:
        basin = await BasinRepo(session).get(basin_id or 0)
        if basin is None:
            return jsonify({"detail": "盆不存在"}), 404
        try:
            sticker = await StickerRepo(session).create(basin, stop_date, g.user.username)
        except RuleError as exc:
            return jsonify({"detail": str(exc)}), 409
        return _sticker_json(sticker), 201


@app.route("/api/stop-stickers/<int:sticker_id>/void", methods=["POST"])
async def void_sticker(sticker_id: int):
    denied = require_admin()
    if denied:
        return denied
    async with SessionLocal() as session:
        repo = StickerRepo(session)
        sticker = await repo.get(sticker_id)
        if sticker is None:
            return jsonify({"detail": "贴纸不存在"}), 404
        if sticker.voided_at is not None:
            return jsonify({"detail": "该贴纸已作废"}), 400
        await repo.void(sticker)
        return _sticker_json(sticker)
