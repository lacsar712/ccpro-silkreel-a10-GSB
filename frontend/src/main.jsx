import { render } from "preact";
import { useEffect, useState } from "preact/hooks";
import {
  api,
  clearStoredUser,
  clearToken,
  setStoredUser,
  setToken,
  storedUser,
  token,
} from "./api.js";
import "./app.css";

const STATUS_LABEL = { soaking: "浸茧", reeling: "缫丝中", reeled: "已缫完" };
const ROLE_LABEL = { admin: "管理员", worker: "缫丝工" };

function Login({ onOk }) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("123456");
  const [err, setErr] = useState("");
  async function submit(e) {
    e.preventDefault();
    setErr("");
    try {
      const data = await api("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      setToken(data.access_token);
      setStoredUser(data.user);
      onOk(data.user);
    } catch (ex) {
      setErr(ex.message);
    }
  }
  return (
    <div class="login">
      <h1>江口缫丝坞</h1>
      <p>汤温环盆作业台，不是列表台账。</p>
      <form onSubmit={submit} autocomplete="off">
        <label>
          用户名
          <input name="username" autocomplete="off" value={username} onInput={(e) => setUsername(e.target.value)} />
        </label>
        <label>
          密码
          <input name="password" type="password" autocomplete="off" value={password} onInput={(e) => setPassword(e.target.value)} />
        </label>
        <p class="hint">已预填 admin / 123456，另有 worker / 123456</p>
        <button type="submit">登录</button>
      </form>
      {err && <p class="err">{err}</p>}
    </div>
  );
}

function Yard() {
  const [board, setBoard] = useState(null);
  const [picked, setPicked] = useState(null);
  const [temp, setTemp] = useState("40");
  const [err, setErr] = useState("");

  async function refresh() {
    const data = await api("/api/board");
    setBoard(data);
    if (picked) {
      setPicked(data.basins.find((b) => b.id === picked.id) || data.basins[0]);
    }
  }

  useEffect(() => {
    refresh().catch((e) => setErr(e.message));
  }, []);

  if (!board) {
    return (
      <div>
        {err || "装载环盆…"}
      </div>
    );
  }

  const n = board.basins.length;
  async function writeTemp() {
    setErr("");
    try {
      const row = await api(`/api/basins/${picked.id}/readings`, {
        method: "POST",
        body: JSON.stringify({ waterTempC: Number(temp) }),
      });
      await refresh();
      setPicked(row);
    } catch (ex) {
      setErr(ex.message);
    }
  }
  async function setStatus(status) {
    setErr("");
    try {
      const row = await api(`/api/basins/${picked.id}/status`, {
        method: "POST",
        body: JSON.stringify({ status }),
      });
      await refresh();
      setPicked(row);
    } catch (ex) {
      setErr(ex.message);
    }
  }

  return (
    <div>
      <header class="pagehead">
        <h1>{board.filature}</h1>
        <p>{board.riverside} · 点盆登记汤温；已缫完须最近汤温 38～42℃</p>
      </header>
      <div class="ring">
        {board.basins.map((b, i) => {
          const angle = (Math.PI * 2 * i) / n - Math.PI / 2;
          const left = 50 + Math.cos(angle) * 38;
          const top = 50 + Math.sin(angle) * 38;
          return (
            <button
              key={b.id}
              class={`basin ${b.status}`}
              style={{ left: `${left}%`, top: `${top}%` }}
              onClick={() => setPicked(b)}
            >
              <strong>{b.code}</strong>
              <span>{STATUS_LABEL[b.status]}</span>
            </button>
          );
        })}
      </div>
      {picked && (
        <div class="drawer">
          <h3>
            {picked.code} · {STATUS_LABEL[picked.status]}
          </h3>
          <p>最近汤温：{picked.latestTempC ?? "无"} ℃ · 记录 {picked.readingCount} 次</p>
          {picked.stopDate && (
            <p class="hint">停缫止日：{picked.stopDate}，止日后禁止登记汤温，改盆态仍可</p>
          )}
          <input value={temp} onInput={(e) => setTemp(e.target.value)} />
          <button onClick={writeTemp}>登记汤温</button>
          <div>
            <button onClick={() => setStatus("soaking")}>浸茧</button>
            <button onClick={() => setStatus("reeling")}>缫丝中</button>
            <button onClick={() => setStatus("reeled")}>已缫完</button>
          </div>
          {err && <p class="err">{err}</p>}
        </div>
      )}
    </div>
  );
}

function StickerBoard({ user }) {
  const isAdmin = user.role === "admin";
  const [basins, setBasins] = useState([]);
  const [stickers, setStickers] = useState([]);
  const [filter, setFilter] = useState("");
  const [basinId, setBasinId] = useState("");
  const [stopDate, setStopDate] = useState("");
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");

  async function loadStickers(basinFilter) {
    const q = basinFilter ? `?basinId=${basinFilter}` : "";
    const data = await api(`/api/stop-stickers${q}`);
    setStickers(data.stickers);
  }

  useEffect(() => {
    api("/api/board")
      .then((d) => setBasins(d.basins))
      .catch((e) => setErr(e.message));
    loadStickers("").catch((e) => setErr(e.message));
  }, []);

  async function onFilter(e) {
    const value = e.target.value;
    setFilter(value);
    setErr("");
    try {
      await loadStickers(value);
    } catch (ex) {
      setErr(ex.message);
    }
  }

  async function create(e) {
    e.preventDefault();
    setErr("");
    setMsg("");
    try {
      await api("/api/stop-stickers", {
        method: "POST",
        body: JSON.stringify({ basinId: Number(basinId), stopDate }),
      });
      setMsg("已贴出");
      setStopDate("");
      await loadStickers(filter);
    } catch (ex) {
      setErr(ex.message);
    }
  }

  async function voidSticker(id) {
    setErr("");
    setMsg("");
    try {
      await api(`/api/stop-stickers/${id}/void`, { method: "POST" });
      setMsg("已作废");
      await loadStickers(filter);
    } catch (ex) {
      setErr(ex.message);
    }
  }

  const today = new Date().toLocaleDateString("sv-SE");
  const fmt = (iso) => (iso ? iso.slice(0, 16).replace("T", " ") : "—");

  return (
    <div>
      <header class="pagehead">
        <h1>停缫止日</h1>
        <p>
          每盆最多一张未作废贴纸；服务器自然日晚于止日后禁止再登汤温，改盆态仍可。
          {!isAdmin && "缫丝工仅可查看，贴与作废请联系管理员。"}
        </p>
      </header>

      <div class="panel">
        <label class="inline">
          按盆筛
          <select value={filter} onChange={onFilter}>
            <option value="">全部盆</option>
            {basins.map((b) => (
              <option key={b.id} value={b.id}>
                {b.code}
              </option>
            ))}
          </select>
        </label>

        {isAdmin && (
          <form class="inline" onSubmit={create} autocomplete="off">
            <label class="inline">
              新贴·盆
              <select value={basinId} onInput={(e) => setBasinId(e.target.value)} required>
                <option value="">选盆</option>
                {basins.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.code}
                  </option>
                ))}
              </select>
            </label>
            <label class="inline">
              止日
              <input type="date" value={stopDate} onInput={(e) => setStopDate(e.target.value)} required />
            </label>
            <button type="submit">贴出</button>
          </form>
        )}
        {msg && <p class="ok">{msg}</p>}
        {err && <p class="err">{err}</p>}
      </div>

      <table class="stickers">
        <thead>
          <tr>
            <th>盆</th>
            <th>止日</th>
            <th>贴出人</th>
            <th>贴出时刻</th>
            <th>作废时刻</th>
            <th>状态</th>
            {isAdmin && <th>操作</th>}
          </tr>
        </thead>
        <tbody>
          {stickers.length === 0 && (
            <tr>
              <td colspan={isAdmin ? 7 : 6} class="hint">
                暂无贴纸
              </td>
            </tr>
          )}
          {stickers.map((s) => {
            const voided = Boolean(s.voidedAt);
            const expired = !voided && s.stopDate < today;
            return (
              <tr key={s.id} class={voided ? "voided" : ""}>
                <td>{s.basinCode}</td>
                <td>{s.stopDate}</td>
                <td>{s.postedBy}</td>
                <td>{fmt(s.postedAt)}</td>
                <td>{fmt(s.voidedAt)}</td>
                <td>
                  {voided ? (
                    <span class="tag void">已作废</span>
                  ) : expired ? (
                    <span class="tag expired">已过止日</span>
                  ) : (
                    <span class="tag active">生效中</span>
                  )}
                </td>
                {isAdmin && (
                  <td>
                    {!voided && <button onClick={() => voidSticker(s.id)}>作废</button>}
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function App() {
  const [user, setUser] = useState(() => (token() ? storedUser() : null));
  const [page, setPage] = useState("yard");

  function logout() {
    clearToken();
    clearStoredUser();
    setUser(null);
  }

  if (!user) {
    return <Login onOk={(u) => setUser(u)} />;
  }

  return (
    <div class="yard">
      <div class="topbar">
        <nav class="nav">
          <button class={page === "yard" ? "on" : ""} onClick={() => setPage("yard")}>
            环盆作业台
          </button>
          <button class={page === "stickers" ? "on" : ""} onClick={() => setPage("stickers")}>
            停缫止日
          </button>
        </nav>
        <div>
          <span class="who">
            {user.username}（{ROLE_LABEL[user.role] || user.role}）
          </span>
          <button onClick={logout}>退出</button>
        </div>
      </div>
      {page === "yard" ? <Yard /> : <StickerBoard user={user} />}
    </div>
  );
}

render(<App />, document.getElementById("app"));
