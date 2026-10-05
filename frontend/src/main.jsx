import { render } from "preact";
import { useEffect, useState } from "preact/hooks";
import { api, clearToken, setToken, token } from "./api.js";
import "./app.css";

const STATUS_LABEL = { soaking: "浸茧", reeling: "缫丝中", reeled: "已缫完" };

function useCurrentUser() {
  const [user, setUser] = useState(null);
  useEffect(() => {
    api("/api/auth/me")
      .then(setUser)
      .catch(() => setUser({ username: "", role: "worker" }));
  }, []);
  return user;
}

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
      onOk();
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

function TopNav({ view, setView, user }) {
  return (
    <nav class="topnav">
      <button
        class={view === "yard" ? "active" : ""}
        onClick={() => setView("yard")}
      >
        环盆作业台
      </button>
      <button
        class={view === "stickers" ? "active" : ""}
        onClick={() => setView("stickers")}
      >
        停缫止日
      </button>
      <span class="who">{user ? `${user.username}（${user.role === "admin" ? "管理员" : "缫丝工"}）` : ""}</span>
      <button
        class="logout"
        onClick={() => {
          clearToken();
          location.reload();
        }}
      >
        退出
      </button>
    </nav>
  );
}

function StopTag({ basin }) {
  if (!basin.stopDate) return null;
  return (
    <span class={`stop-tag ${basin.stopDatePassed ? "passed" : ""}`}>
      止日 {basin.stopDate}
      {basin.stopDatePassed ? "（已过）" : ""}
    </span>
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
      <div class="yard">
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
      // 止日已过等中文拦截由后端给出，原样显示；本格汤温不入库。
      setErr(ex.message);
      await refresh();
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
    <div class="yard">
      <div class="topbar">
        <div>
          <h1>{board.filature}</h1>
          <p>
            {board.riverside} · 点盆登记汤温；已缫完须最近汤温 38～42℃ ·
            服务器今日 {board.serverDate}
          </p>
        </div>
      </div>
      <div class="ring">
        {board.basins.map((b, i) => {
          const angle = (Math.PI * 2 * i) / n - Math.PI / 2;
          const left = 50 + Math.cos(angle) * 38;
          const top = 50 + Math.sin(angle) * 38;
          return (
            <button
              key={b.id}
              class={`basin ${b.status} ${b.stopDatePassed ? "stopped" : ""}`}
              style={{ left: `${left}%`, top: `${top}%` }}
              onClick={() => {
                setErr("");
                setPicked(b);
              }}
            >
              <strong>{b.code}</strong>
              <span>{STATUS_LABEL[b.status]}</span>
              {b.stopDatePassed && <span class="seal">止</span>}
            </button>
          );
        })}
      </div>
      {picked && (
        <div class="drawer">
          <h3>
            {picked.code} · {STATUS_LABEL[picked.status]} <StopTag basin={picked} />
          </h3>
          <p>最近汤温：{picked.latestTempC ?? "无"} ℃ · 记录 {picked.readingCount} 次</p>
          {picked.stopDatePassed && (
            <p class="err">
              该盆停缫止日 {picked.stopDate} 已过，禁止再登记汤温；仍可改盆态。
            </p>
          )}
          <input value={temp} onInput={(e) => setTemp(e.target.value)} />
          <button onClick={writeTemp}>保存汤温</button>
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

function Stickers({ user }) {
  const isAdmin = user && user.role === "admin";
  const [data, setData] = useState(null);
  const [filterBasin, setFilterBasin] = useState("");
  const [newBasin, setNewBasin] = useState("");
  const [newDate, setNewDate] = useState("");
  const [err, setErr] = useState("");
  const [ok, setOk] = useState("");

  async function refresh() {
    const qs = filterBasin ? `?basin_id=${encodeURIComponent(filterBasin)}` : "";
    setData(await api(`/api/stickers${qs}`));
  }

  useEffect(() => {
    refresh().catch((e) => setErr(e.message));
  }, [filterBasin]);

  useEffect(() => {
    if (data && !newBasin && data.basins.length) setNewBasin(String(data.basins[0].id));
    if (data && !newDate) setNewDate(data.serverDate);
  }, [data]);

  async function paste(e) {
    e.preventDefault();
    setErr("");
    setOk("");
    try {
      await api("/api/stickers", {
        method: "POST",
        body: JSON.stringify({ basinId: Number(newBasin), stopDate: newDate }),
      });
      setOk("贴纸已贴出；同盆旧版已当场作废，只留一版。");
      await refresh();
    } catch (ex) {
      setErr(ex.message);
    }
  }

  async function voidSticker(id) {
    setErr("");
    setOk("");
    try {
      await api(`/api/stickers/${id}/void`, { method: "POST" });
      setOk("贴纸已作废。");
      await refresh();
    } catch (ex) {
      setErr(ex.message);
    }
  }

  if (!data) return <div class="page">{err || "装载止日贴纸…"}</div>;

  const basinCode = (id) => {
    const b = data.basins.find((x) => x.id === id);
    return b ? b.code : `盆#${id}`;
  };

  return (
    <div class="page">
      <div class="topbar">
        <div>
          <h1>停缫止日</h1>
          <p>每盆至多一张未作废贴纸；服务器自然日晚于止日后，该盆禁止登记汤温（今日 {data.serverDate}）。</p>
        </div>
      </div>

      <div class="toolbar">
        <label>
          按盆筛选
          <select value={filterBasin} onChange={(e) => setFilterBasin(e.target.value)}>
            <option value="">全部盆</option>
            {data.basins.map((b) => (
              <option key={b.id} value={b.id}>{b.code}</option>
            ))}
          </select>
        </label>
      </div>

      {isAdmin && (
        <form class="paste-card" onSubmit={paste}>
          <h3>新贴止日</h3>
          <label>
            盆
            <select value={newBasin} onChange={(e) => setNewBasin(e.target.value)}>
              {data.basins.map((b) => (
                <option key={b.id} value={b.id}>{b.code}</option>
              ))}
            </select>
          </label>
          <label>
            止日
            <input type="date" value={newDate} onInput={(e) => setNewDate(e.target.value)} />
          </label>
          <button type="submit">贴出</button>
        </form>
      )}
      {!isAdmin && <p class="hint">缫丝工只读：贴与作废请找管理员。</p>}

      {err && <p class="err">{err}</p>}
      {ok && <p class="ok">{ok}</p>}

      <table class="sticker-table">
        <thead>
          <tr>
            <th>盆</th>
            <th>止日</th>
            <th>贴出人</th>
            <th>状态</th>
            {isAdmin && <th>操作</th>}
          </tr>
        </thead>
        <tbody>
          {data.stickers.length === 0 && (
            <tr><td colspan={isAdmin ? 5 : 4} class="hint">暂无贴纸。</td></tr>
          )}
          {data.stickers.map((s) => (
            <tr key={s.id} class={s.voidedAt ? "voided" : ""}>
              <td>{basinCode(s.basinId)}</td>
              <td>{s.stopDate}{!s.voidedAt && s.passed && <span class="stop-tag passed">已过</span>}</td>
              <td>{s.issuedBy}</td>
              <td>{s.voidedAt ? `已作废 ${s.voidedAt.slice(0, 16).replace("T", " ")}` : "生效中"}</td>
              {isAdmin && (
                <td>
                  {!s.voidedAt && (
                    <button onClick={() => voidSticker(s.id)}>作废</button>
                  )}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function App() {
  const [ready, setReady] = useState(Boolean(token()));
  const [view, setView] = useState("yard");
  const user = useCurrentUser();
  if (!ready) return <Login onOk={() => setReady(true)} />;
  return (
    <div class="shell">
      <TopNav view={view} setView={setView} user={user} />
      {view === "yard" ? <Yard /> : <Stickers user={user} />}
    </div>
  );
}

render(<App />, document.getElementById("app"));
