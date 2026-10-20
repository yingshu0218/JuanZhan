import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { login, createSpace, api } from "./helpers.mjs";

async function upload(page, space, name, buffer, mimeType) {
  const response = await page.request.post("/api/v1/documents/upload", {
    headers: { "X-CSRF-Token": (await api(page, "/auth/session")).data.csrf_token },
    multipart: { space_id: space, file: { name, mimeType, buffer } },
  });
  expect(response.status()).toBe(201);
  const doc = await response.json();
  await expect.poll(async () => (await api(page, `/documents/${doc.document_id}`)).data.processing_status, { timeout: 30000 }).toBe("completed");
  return doc.document_id;
}
async function open(page, name, space) {
  await page.reload();
  await page.getByLabel("当前空间").selectOption(space);
  await page.getByRole("region", { name: "档案列表", exact: true }).getByRole("button").filter({ hasText: name }).click();
}

test("real paginated reading, safe source text, explicit candidate adoption, history and responsive return", async ({ page }) => {
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (e) => { if (e.type() === "error" && !e.text().includes("409 (Conflict)")) errors.push(e.text()); });
  await login(page); await createSpace(page, "正文阅读实物");
  const space = (await api(page, "/spaces")).data.find((x) => x.name === "正文阅读实物").id;
  const field = await api(page, "/field-definitions", "POST", { space_id: space, key: "source_title", label: "原始标题", type: "text" });
  expect(field.status).toBe(201);
  const docx = execFileSync("../.venv/bin/python", ["-c", "import sys;sys.path.insert(0,'../tests');from format_samples import docx;sys.stdout.buffer.write(docx())"]);
  const id = await upload(page, space, "真实候选.docx", docx, "application/vnd.openxmlformats-officedocument.wordprocessingml.document");
  await page.reload();
  await open(page, "真实候选.docx", space);
  const reader = page.getByRole("region", { name: "正文阅读", exact: true });
  await expect(reader.getByRole("heading", { name: "内容概览", exact: true })).toBeVisible();
  await expect(reader.getByRole("heading", { name: "项目规划" })).toBeVisible();
  await expect(reader.getByRole("columnheader", { name: "字段", exact: true })).toBeVisible();
  await expect(reader.getByRole("cell", { name: "内容", exact: true })).toBeVisible();
  await reader.getByRole("button", { name: "阅读本节完整内容", exact: true }).click();
  await expect(reader.getByText("定位未知", { exact: true })).not.toBeVisible();
  await reader.locator(".reader-diagnostics > summary").click();
  await reader.getByLabel("显示每段来源定位与置信度").check();
  await expect(reader.locator(".block-annotation").first()).toBeVisible();
  await reader.getByLabel("显示每段来源定位与置信度").uncheck();
  await reader.locator(".reader-diagnostics > summary").click();
  await expect(reader.getByRole("cell", { name: "内容", exact: true })).toBeVisible();
  const candidates = page.getByRole("region", { name: "提取候选", exact: true });
  await expect(candidates.getByText('"真实标题"', { exact: true })).toBeVisible();
  await expect(candidates.getByText("置信度未提供", { exact: false }).first()).toBeVisible();
  await candidates.locator("li").filter({ hasText: '"真实标题"' }).getByRole("button", { name: "采纳此候选" }).click();
  await page.getByLabel("目标业务字段").selectOption(field.data.id);
  const version = (await api(page, `/documents/${id}`)).data.document_version;
  expect((await api(page, `/documents/${id}`, "PATCH", { expected_document_version: version, description: "并发编辑保护" })).status).toBe(200);
  await page.getByRole("button", { name: "确认覆盖并采纳" }).click();
  await expect(page.getByRole("dialog", { name: "确认采纳候选" }).getByRole("alert")).toContainText("已被更新");
  expect((await api(page, `/documents/${id}/metadata`)).data).toEqual([]);
  await page.getByRole("button", { name: "关闭确认采纳候选" }).click();
  await reader.getByRole("button", { name: "刷新内容" }).click();
  await candidates.locator("li").filter({ hasText: '"真实标题"' }).getByRole("button", { name: "采纳此候选" }).click();
  await page.getByLabel("目标业务字段").selectOption(field.data.id);
  await page.getByRole("button", { name: "确认覆盖并采纳" }).click();
  await expect(page.getByRole("dialog", { name: "确认采纳候选" })).not.toBeVisible();
  await expect(page.locator(".business-fields")).toContainText("真实标题");
  expect((await api(page, `/documents/${id}`)).data.title).toBe("真实候选.docx");
  await reader.getByLabel("阅读格式").selectOption("markdown");
  await expect(reader.locator("pre")).toContainText("项目规划");
  await expect(reader.locator("script,img,iframe")).toHaveCount(0);
  const doc = (await api(page, `/documents/${id}`)).data;
  const request = await api(page, `/documents/${id}/reprocess`, "POST", { expected_document_version: doc.document_version, expected_revision_id: doc.current_revision_id, request_id: "browser-history", force: true });
  expect(request.status).toBe(202);
  await expect.poll(async () => (await api(page, `/documents/${id}/parse-runs`)).data.total).toBe(2);
  await expect.poll(async () => (await api(page, `/documents/${id}`)).data.processing_status).toBe("completed");
  await page.getByRole("button", { name: "刷新档案详情" }).click();
  const history = page.getByRole("region", { name: "解析历史", exact: true });
  await expect(history.locator(".parse-history > li")).toHaveCount(2);
  await history.getByRole("button", { name: "查看此次结果" }).last().click();
  await expect(reader.getByRole("button", { name: "返回当前成功正文" })).toBeVisible();
  await expect(candidates.getByRole("button", { name: "采纳此候选" })).toHaveCount(0);
  await reader.getByRole("button", { name: "返回当前成功正文" }).click();
  await page.screenshot({ path: "/tmp/juanzhan-t29-desktop.png", fullPage: false });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(reader.getByRole("heading", { name: "内容概览", exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: "/tmp/juanzhan-t29-mobile.png", fullPage: false });
  await page.getByRole("button", { name: "返回档案列表" }).click();
  await expect(page.getByRole("region", { name: "档案列表", exact: true })).toBeVisible();
  expect(errors).toEqual([]);
});

test("real multi-page blocks and untrusted markup remain safe across format changes", async ({ page }) => {
  await login(page); await createSpace(page, "分页与安全文本");
  const space = (await api(page, "/spaces")).data.find((x) => x.name === "分页与安全文本").id;
  const text = Array.from({ length: 45 }, (_, i) => `段落 ${String(i + 1).padStart(2, "0")} <img src=x onerror=alert(1)>`).join("\n\n");
  await upload(page, space, "分页.txt", Buffer.from(text), "text/plain");
  await open(page, "分页.txt", space);
  const reader = page.getByRole("region", { name: "正文阅读", exact: true });
  await expect(reader.getByText("段落 01", { exact: false })).toBeVisible();
  await reader.getByRole("button", { name: "阅读完整正文", exact: true }).click();
  const pager = page.getByRole("navigation", { name: "正文分页" });
  await pager.getByRole("button", { name: "下一页" }).click();
  await expect(reader.getByText("段落 21", { exact: false })).toBeVisible();
  await reader.getByLabel("阅读格式").selectOption("text");
  await expect(reader.locator("pre")).toContainText("段落 45");
  await reader.getByLabel("阅读格式").selectOption("blocks");
  await expect(reader.getByText("段落 01", { exact: false })).toBeVisible();
  await expect(reader.locator("img,script,iframe,a")).toHaveCount(0);
  await expect(page.locator("vite-error-overlay")).toHaveCount(0);
});

test("failed parsing leaves truthful empty reading and expired sessions return to login", async ({ page }) => {
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await login(page); await createSpace(page, "失败正文");
  const space = (await api(page, "/spaces")).data.find((x) => x.name === "失败正文").id;
  const response = await page.request.post("/api/v1/documents/upload", {
    headers: { "X-CSRF-Token": (await api(page, "/auth/session")).data.csrf_token },
    multipart: { space_id: space, file: { name: "损坏.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4\ninvalid") } },
  });
  expect(response.status()).toBe(201);
  const id = (await response.json()).document_id;
  await expect.poll(async () => (await api(page, `/documents/${id}`)).data.processing_status).toBe("failed");
  await open(page, "损坏.pdf", space);
  const reader = page.getByRole("region", { name: "正文阅读", exact: true });
  await expect(reader).toContainText("尚无成功解析的正文。处理失败");
  await expect(page.getByRole("region", { name: "解析历史", exact: true })).toContainText("此尝试没有成功正文");
  await expect(page.locator(".business-fields")).toBeVisible();
  await api(page, "/auth/logout", "POST");
  await reader.getByRole("button", { name: "刷新内容" }).click();
  await expect(page.getByLabel("密码", { exact: true })).toBeVisible();
  expect(errors).toEqual([]);
});
