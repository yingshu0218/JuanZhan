import { InfoTip } from "./ui.jsx";
import { useEffect, useState } from "react";
import { Archive } from "@phosphor-icons/react";
import { ApiClient, message } from "./api.js";
import { Notice } from "./ui.jsx";
import { Workspace } from "./Workspace.jsx";
import { OAuthConsent } from "./OAuthConsent.jsx";

export function App() {
  const [api] = useState(() => new ApiClient());
  const [session, setSession] = useState(undefined);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    api.onExpired = () => {
      if (active) {
        api.csrf = null;
        setSession(null);
        setError("会话已过期，请重新登录。");
      }
    };
    api
      .request("/auth/session", { signal: controller.signal })
      .then((data) => {
        if (active) setSession(data.authenticated ? data : null);
      })
      .catch((e) => {
        if (active) {
          setSession(null);
          setError(message(e));
        }
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [api]);
  async function login(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const values = new FormData(event.currentTarget);
    try {
      await api.request("/auth/session");
      const data = await api.request("/auth/login", {
        method: "POST",
        body: {
          username: values.get("username"),
          password: values.get("password"),
        },
      });
      setSession(data);
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }
  async function logout() {
    try {
      await api.request("/auth/logout", { method: "POST" });
      api.csrf = null;
      setSession(null);
    } catch (e) {
      setError(message(e));
    }
  }
  if (session === undefined)
    return (
      <div className="loading-screen" role="status">
        正在连接档案库…
      </div>
    );
  if (!session)
    return (
      <div className="login-page">
        <form onSubmit={login} className="login-form">
          <Archive size={38} weight="duotone" />
          <h1>欢迎回到档案库</h1>
          <InfoTip>让资料有序，让信息可查。</InfoTip>
          <label>
            用户名
            <input
              name="username"
              autoComplete="username"
              defaultValue="admin"
              required
            />
          </label>
          <label>
            密码
            <input
              name="password"
              type="password"
              autoComplete="current-password"
              required
            />
          </label>
          {error ? <Notice error>{error}</Notice> : null}
          <button className="primary" disabled={busy}>
            {busy ? "正在登录…" : "登录"}
          </button>
        </form>
      </div>
    );
  if (window.location.pathname === "/oauth/authorize") return <OAuthConsent api={api} />;
  return <Workspace api={api} logout={logout} authError={error} />;
}
