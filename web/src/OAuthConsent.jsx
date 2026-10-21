import { useEffect, useState } from "react";
import { Notice, InfoTip } from "./ui.jsx";

export function OAuthConsent({ api }) {
  const [request, setRequest] = useState(null);
  const [spaces, setSpaces] = useState([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    const params = new URLSearchParams(window.location.search);
    const values = Object.fromEntries(params);
    if ([...params.keys()].some((key) => params.getAll(key).length > 1)) {
      setError("授权参数重复，请从客户端重新发起授权。");
      return () => controller.abort();
    }
    api.request("/oauth/requests", { method: "POST", body: values, signal: controller.signal })
      .then(setRequest)
      .catch((e) => { if (e.name !== "AbortError") setError("授权请求无效或已过期，请从客户端重新发起授权。"); });
    return () => controller.abort();
  }, [api]);
  async function decide(decision) {
    setBusy(true);
    setError("");
    try {
      const result = await api.request("/oauth/authorize", {
        method: "POST", body: { request_id: request.request_id, decision, space_ids: spaces },
      });
      window.location.assign(result.redirect_uri);
    } catch {
      setError("授权未完成，请检查空间选择，或从客户端重新发起授权。");
      setBusy(false);
    }
  }
  return <main className="login-page"><section className="login-form oauth-consent" aria-labelledby="oauth-title">
    <h1 id="oauth-title">授权访问文档</h1>
    {error && <Notice error>{error}</Notice>}
    {!request && !error && <p role="status">正在读取授权请求…</p>}
    {request && <>
      <h2>{request.client_name}</h2>
      <p>只读访问所选空间的文档、概要和检索结果。</p>
      <p>授权返回地址：<span style={{ overflowWrap: "anywhere" }}>{request.redirect_uri}</span></p>
      <InfoTip>访问令牌有效期1小时；允许刷新时授权最长30天。可在 Agent 接入中随时撤销。客户端名称由注册者提供，请核对返回地址。</InfoTip>
      <fieldset disabled={busy}><legend>选择允许访问的空间</legend>
        {request.spaces.map((space) => <label className="check-label" key={space.id}>
          <input type="checkbox" checked={spaces.includes(space.id)} onChange={(e) => setSpaces((current) => e.target.checked ? [...current, space.id] : current.filter((id) => id !== space.id))} />
          {space.name}
        </label>)}
      </fieldset>
      <button className="primary" disabled={busy || !spaces.length} onClick={() => decide("allow")}>允许只读访问</button>
      <button disabled={busy} onClick={() => decide("deny")}>拒绝</button>
    </>}
  </section></main>;
}
