export class ApiError extends Error {
  constructor(status, error) {
    super(error?.message || "请求未完成");
    this.status = status;
    this.code = error?.code || "NETWORK_ERROR";
    this.details = error?.details;
  }
}
const messages = {
  SOURCE_ENTRY_MANAGED: "该来源条目已纳入托管；保留排除规则以防重复导入。",
  SOURCE_ENTRY_BUSY: "该来源条目已有操作或排除规则，请先核对。",
  EXTERNAL_REVISION_REQUIRED: "当前原件已不再是外部版本，请刷新档案。",
  ADOPTION_LIMIT: "外部原件超过当前托管输入限制。",
  ORIGINAL_UNAVAILABLE: "原件离线、已变化或完整性核验未通过，未提供下载。",
  ORIGINAL_NOT_AVAILABLE: "当前原件不存在。",
  PREVIEW_STALE: "预览属于旧原件，请重新解析当前版本。",
  PREVIEW_UNAVAILABLE: "缓存预览完整性核验未通过。",
  DOWNLOAD_CAPACITY: "下载准备繁忙，请稍后重试。",
  DOWNLOAD_LIMIT: "原件超过当前下载上限。",
  REVISION_CONFLICT: "原件版本已改变，请刷新档案。",
  PARSE_ALREADY_RUNNING: "当前版本已有解析任务，请在任务中心查看。",
  DOCUMENT_TRASHED: "请先恢复回收站中的档案。",
  CROSS_SPACE_REFERENCE: "引用项不属于当前空间，请重新选择。",
  INVALID_SEARCH_TEXT: "请输入较短且包含文字或数字的检索词。",
  FIELD_NOT_FILTERABLE: "所选字段已停用或不可筛选，请移除条件后重试。",
  UNKNOWN_SEARCH_FIELD: "检索字段已不可用，请刷新并调整条件。",
  INVALID_METADATA_VALUE: "字段筛选值的类型、精度或日期无效，请核对后重试。",
  INVALID_SEARCH_VALUE: "筛选值或区间无效，请核对起止值与类型。",
  SEARCH_TIMEOUT: "检索超时，请缩小范围后重试。",
  SEARCH_STATUS_LIMIT: "实时状态核验范围过大，请先缩小目录、类型或字段范围。",
  SEARCH_RESPONSE_LIMIT: "结果内容过大，请缩小检索范围。",
  SEARCH_REQUEST_LIMIT: "检索条件过长，请减少条件。",
  DERIVED_CONTENT_UNAVAILABLE: "缓存文本暂时不可读，请切换结构化正文或联系管理员检查派生产物。",
  CONTENT_NOT_COMPLETED: "所选解析尚未成功，请查看其他结果。",
  CONTENT_RESPONSE_LIMIT: "内容超过读取上限，请使用结构化正文分页读取。",
  STALE_CANDIDATE: "候选所属结果已过期，请刷新后核对当前候选。",
  SOURCE_OFFLINE: "来源离线，请检查挂载后刷新。",
  SOURCE_NOT_READ_ONLY: "来源挂载可写，必须由管理员改为只读。",
  SOURCE_UNREADABLE: "来源无法读取，请检查挂载权限。",
  SOURCE_ALIAS_NOT_ALLOWED: "挂载别名未获授权，请刷新来源。",
  SOURCE_OVERLAP: "此目录已被来源覆盖，请选择独立挂载。",
  SOURCE_OVERLAP_UNVERIFIED: "已有来源不可用，暂时无法验证目录是否重叠。",
  SOURCE_SCAN_BUSY: "此来源已有其他扫描任务，请等待完成后刷新。",
  SOURCE_INITIAL_REQUIRED: "请先完成首次导入。",
  SOURCE_ROOT_CHANGED: "挂载根身份发生变化，请管理员核对原挂载。",
  SOURCE_ROOT_UNVERIFIED: "尚无法验证原挂载身份，请管理员核对。",
  SOURCE_CHANGED: "扫描期间来源变化，请确认稳定后重试。",
  SOURCE_FOLDER_CONFLICT: "逻辑目录名称冲突，请调整后重试。",
  SOURCE_MANIFEST_LIMIT: "来源超过本次扫描限制，请缩小来源范围。",
  SOURCE_PREVIEW_LIMIT: "来源超过预扫描限制，请缩小来源范围。",
  JOB_NOT_RETRYABLE: "此任务当前不能重试，请刷新核对。",
  JOB_TIMEOUT: "任务执行超时，请检查来源规模及连接。",
  INVALID_CREDENTIALS: "用户名或密码不正确",
  ADMIN_NOT_CONFIGURED: "管理员尚未初始化，请由服务管理员完成初始化。",
  LOGIN_THROTTLED: "登录尝试过于频繁，请稍后重试。",
  DUPLICATE_DETECTED: "此空间已有相同原件，请核对后决定是否另存档案。",
  BATCH_TOO_LARGE: "本次操作内容过多，请减少选择的档案或标签。",
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
