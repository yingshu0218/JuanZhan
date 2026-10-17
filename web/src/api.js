export class ApiError extends Error {
  constructor(status, error) {
    super(error?.message || "请求未完成");
    this.status = status;
    this.code = error?.code || "NETWORK_ERROR";
    this.details = error?.details;
  }
}
const messages = {
  INVALID_CREDENTIALS: "用户名或密码不正确",
  ADMIN_NOT_CONFIGURED: "管理员尚未初始化，请由服务管理员完成初始化。",
  LOGIN_THROTTLED: "登录尝试过于频繁，请稍后重试。",
  DUPLICATE_DETECTED: "此空间已有相同原件，请核对后决定是否另存档案。",
  VERSION_CONFLICT: "档案已被更新，请刷新后重试。",
  CSRF_REJECTED: "会话已变更，请重新登录。",
  UNAUTHORIZED: "会话已过期，请重新登录。",
  UPLOAD_TOO_LARGE: "文件超过当前上传限制。",
  UPLOAD_CAPACITY: "上传繁忙，请稍后重试。",
  UPLOAD_TIMEOUT: "上传等待超时，请刷新核对后重试。",
  CATALOG_CONFLICT: "名称或引用发生冲突，请检查是否重名。",
  INVALID_REQUEST: "输入内容不符合要求，请检查后重试。",
  NOT_FOUND: "所选资料已不可用，请刷新后重试。",
  STORAGE_UNAVAILABLE: "原件暂时无法安全保存，请稍后重试。",
};
export function message(error) {
  return (
    messages[error.code] ||
    (error.status
      ? "操作未完成，请稍后重试。"
      : "网络连接中断，请检查连接后重试。")
  );
}
export class ApiClient {
  csrf = null;
  onExpired = () => {};
  async request(path, { method = "GET", body, signal } = {}) {
    let response;
    try {
      response = await fetch("/api/v1" + path, {
        method,
        signal,
        credentials: "same-origin",
        headers: {
          ...(body ? { "Content-Type": "application/json" } : {}),
          ...(method !== "GET" && this.csrf
            ? { "X-CSRF-Token": this.csrf }
            : {}),
        },
        ...(body ? { body: JSON.stringify(body) } : {}),
      });
    } catch (error) {
      if (error.name === "AbortError") throw error;
      throw new ApiError(0);
    }
    const data = response.status === 204 ? null : await response.json();
    if (!response.ok) {
      if (
        (response.status === 401 ||
          (response.status === 403 && data?.error?.code === "CSRF_REJECTED")) &&
        !path.startsWith("/auth/")
      )
        this.onExpired();
      throw new ApiError(response.status, data?.error);
    }
    if (data?.csrf_token) this.csrf = data.csrf_token;
    return data;
  }
  upload(item, { onProgress, signal }) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      const abort = () => xhr.abort();
      xhr.open("POST", "/api/v1/documents/upload");
      xhr.timeout = 90000;
      xhr.withCredentials = true;
      if (this.csrf) xhr.setRequestHeader("X-CSRF-Token", this.csrf);
      xhr.upload.onprogress = (e) =>
        onProgress(
          e.lengthComputable ? Math.round((e.loaded / e.total) * 100) : null,
        );
      const clean = () => signal.removeEventListener("abort", abort);
      xhr.onload = () => {
        clean();
        let data;
        try {
          data = JSON.parse(xhr.responseText);
        } catch {
          reject(new ApiError(0));
          return;
        }
        if (xhr.status === 201) resolve(data);
        else {
          if (
            xhr.status === 401 ||
            (xhr.status === 403 && data?.error?.code === "CSRF_REJECTED")
          )
            this.onExpired();
          reject(new ApiError(xhr.status, data.error));
        }
      };
      xhr.onerror = xhr.ontimeout = () => {
        clean();
        reject(new ApiError(0));
      };
      xhr.onabort = () => {
        clean();
        reject(new DOMException("Aborted", "AbortError"));
      };
      signal.addEventListener("abort", abort, { once: true });
      const body = new FormData();
      body.set("space_id", item.spaceId);
      if (item.folderId) body.set("folder_id", item.folderId);
      body.set("duplicate_policy", item.policy);
      body.set("file", item.file);
      if (signal.aborted) {
        clean();
        reject(new DOMException("Aborted", "AbortError"));
        return;
      }
      xhr.send(body);
    });
  }
}
