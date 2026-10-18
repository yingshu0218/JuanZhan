import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { login, createSpace, api } from "./helpers.mjs";
const library = (page) => page.getByRole("region", { name: "档案列表", exact: true });
const form = (page) => page.getByRole("search", { name: "档案检索" });
async function put(page, space, name, bytes) {
  const response = await page.request.post("/api/v1/documents/upload", {
    headers: { "X-CSRF-Token": (await api(page, "/auth/session")).data.csrf_token },
    multipart: { space_id: space, file: { name, mimeType: name.endsWith(".pdf") ? "application/pdf" : "text/plain", buffer: Buffer.from(bytes) } },
  });
  expect(response.status()).toBe(201);
  const id = (await response.json()).document_id;
  await expect.poll(async () => (await api(page, `/documents/${id}`)).data.processing_status, { timeout: 30000 }).toBe("completed");
  return id;
}
async function settle(page, space) {
  await expect.poll(async () => { const r = await api(page, "/documents/search", "POST", { space_id: space }); return r.data.search_index?.missing + r.data.search_index?.pending; }, { timeout: 30000 }).toBe(0);
  await page.reload(); await page.getByLabel("当前空间").selectOption(space);
}
async function submit(page, text) {
  if (text !== undefined) await form(page).getByLabel("搜索正文、标题和字段").fill(text);
  await form(page).getByRole("button", { name: "搜索", exact: true }).click();
}
async function advanced(page) {
  if (!(await form(page).locator("details").evaluate((d) => d.open))) await form(page).locator("summary").click();
}

test("real Chinese search, typed combinations, URL history, exact batch scope and mobile return", async ({ page }) => {
  const errors = []; page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (e) => { if (e.type() === "error") errors.push(e.text()); });
  await login(page); await createSpace(page, "真实组合检索");
  const space = await page.getByLabel("当前空间").inputValue();
  for (const [key, label, type] of [["amount", "金额", "decimal"], ["verified", "核验", "boolean"]]) expect((await api(page, "/field-definitions", "POST", { space_id: space, key, label, type, filterable: true })).status).toBe(201);
  const tags = [], types = [];
  for (const name of ["重要", "审核"]) tags.push((await api(page, "/tags", "POST", { space_id: space, name })).data.id);
  for (const [key, label] of [["report", "报告"], ["letter", "信函"]]) types.push((await api(page, "/document-types", "POST", { space_id: space, key, label })).data.id);
  const first = await put(page, space, "合同甲.txt", "繁體檔案 Archive2026 合同甲");
  const second = await put(page, space, "合同乙.txt", "档案 Archive2026 合同乙");
  await put(page, space, "其他.txt", "没有目标词 unrelated");
  for (const [id, amount, verified, date, tagIds, type] of [[first, "2.0001", false, "2024-02-29", tags, types[0]], [second, "10.0000", true, "2025-01-01", tags.slice(0, 1), types[1]]]) {
    let doc = (await api(page, `/documents/${id}`)).data;
    expect((await api(page, `/documents/${id}/metadata`, "PATCH", { expected_document_version: doc.document_version, values: { amount, verified }, confirm: true })).status).toBe(200);
    doc = (await api(page, `/documents/${id}`)).data;
    expect((await api(page, `/documents/${id}`, "PATCH", { expected_document_version: doc.document_version, document_date: date, tags_add: tagIds, document_type_id: type })).status).toBe(200);
  }
  await settle(page, space);
  await expect(library(page).getByText("3 份", { exact: true })).toBeVisible();
  await form(page).getByLabel("搜索正文、标题和字段").fill("檔案 Archive2026");
  await expect(library(page).getByText("3 份", { exact: true })).toBeVisible();
  await submit(page); await expect(library(page).getByText("2 份", { exact: true })).toBeVisible();
  await expect(page.getByLabel("排序", { exact: true })).toHaveValue("-relevance");
  await advanced(page);
  for (const label of ["重要", "审核", "报告", "信函"]) await form(page).getByLabel(label, { exact: true }).check();
  await submit(page); await expect(library(page).getByText("2 份", { exact: true })).toBeVisible();
  await advanced(page); await form(page).getByLabel("标签匹配").selectOption("all");
  await submit(page); await expect(library(page).getByText("1 份", { exact: true })).toBeVisible();
  await advanced(page);
  await form(page).getByRole("button", { name: "添加字段条件" }).click();
  await form(page).getByRole("combobox", { name: "筛选字段 1", exact: true }).selectOption("amount");
  await form(page).getByRole("combobox", { name: "比较方式 1", exact: true }).selectOption("between");
  await form(page).getByLabel("筛选值 1", { exact: true }).fill("2.0000");
  await form(page).getByLabel("范围上限 1", { exact: true }).fill("2.0001");
  await form(page).getByRole("button", { name: "添加字段条件" }).click();
  await form(page).getByRole("combobox", { name: "筛选字段 2", exact: true }).selectOption("verified");
  await form(page).getByRole("combobox", { name: "筛选值 2", exact: true }).selectOption("false");
  await form(page).getByLabel("业务日期起").fill("2024-02-28");
  await form(page).getByLabel("业务日期止").fill("2024-02-29");
  await submit(page); await expect(library(page).getByText("1 份", { exact: true })).toBeVisible();
  const hash = new URL(page.url()).hash; await page.reload();
  await expect(form(page).getByLabel("搜索正文、标题和字段")).toHaveValue("檔案 Archive2026");
  await expect(library(page).getByText("1 份", { exact: true })).toBeVisible();
  expect(new URL(page.url()).hash).toBe(hash);
  await form(page).getByRole("button", { name: "清除搜索" }).click();
  await expect(library(page).getByText("3 份", { exact: true })).toBeVisible();
  await page.goBack(); await expect(library(page).getByText("1 份", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "选择筛选结果", exact: true }).click();
  await expect(page.getByRole("region", { name: "已选档案" })).toContainText("已选 1 份");
  await expect(page.getByLabel("选择档案 合同甲.txt", { exact: true })).toBeChecked();
  await page.getByRole("button", { name: "清除选择" }).click();
  await page.screenshot({ path: "/tmp/juanzhan-t30-desktop.png", fullPage: false });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: "/tmp/juanzhan-t30-mobile.png", fullPage: false });
  await library(page).getByRole("button").filter({ hasText: "合同甲.txt" }).click();
  await expect(page.getByRole("heading", { name: "正文内容", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "返回档案列表" }).click();
  await expect(library(page).getByText("1 份", { exact: true })).toBeVisible();
  expect(errors).toEqual([]);
});

test("empty results distinguish incomplete OCR from complete scope and network failure", async ({ page, context }) => {
  await login(page); await createSpace(page, "索引不全与空结果"); const space = await page.getByLabel("当前空间").inputValue();
  await put(page, space, "普通.txt", "普通正文"); await settle(page, space);
  await submit(page, "不存在的星河编号");
  await expect(page.getByRole("heading", { name: "没有匹配的档案", exact: true })).toBeVisible();
  const pdf = execFileSync("../.venv/bin/python", ["-c", "import sys;sys.path.insert(0,'../tests');from format_samples import raster_sample;sys.stdout.buffer.write(raster_sample('PDF'))"]);
  await put(page, space, "扫描未OCR.pdf", pdf);
  await expect.poll(async () => (await api(page, "/documents/search", "POST", { space_id: space })).data.search_index?.limited_content).toBe(1);
  await page.getByRole("button", { name: "刷新检索结果" }).click();
  await expect(page.getByRole("heading", { name: "暂未找到匹配档案", exact: true })).toBeVisible();
  await expect(page.getByLabel("检索范围状态")).toContainText("当前结果可能不完整");
  await context.setOffline(true); await page.getByRole("button", { name: "刷新检索结果" }).click();
  await expect(page.getByRole("heading", { name: "档案暂时无法读取" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "没有匹配的档案", exact: true })).toHaveCount(0);
  await context.setOffline(false); await page.getByRole("button", { name: "重新加载", exact: true }).click();
  await expect(page.getByRole("heading", { name: "暂未找到匹配档案", exact: true })).toBeVisible();
});

test("invalid URL criteria fail visibly without breaking the app", async ({ page }) => {
  const errors = []; page.on("pageerror", (e) => errors.push(e.message)); await login(page);
  await page.goto("/#library=not-json");
  await expect(page.getByText("链接中的检索条件无效，已回到默认列表。", { exact: true })).toBeVisible();
  await expect(library(page)).toBeVisible(); await expect(page.locator("vite-error-overlay")).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("typed controls preserve select identifiers and reject unsafe integer precision", async ({ page }) => {
  await login(page); await createSpace(page, "类型输入保护"); const space = await page.getByLabel("当前空间").inputValue();
  for (const [key, label, type] of [["count", "数量", "integer"], ["day", "日期字段", "date"], ["note", "文本字段", "text"], ["long_note", "长文本字段", "long_text"], ["choice", "单选字段", "single_select"]]) {
    const constraints = type === "single_select" ? { options: [{ id: "stable", label: "稳定选项" }] } : {};
    expect((await api(page, "/field-definitions", "POST", { space_id: space, key, label, type, filterable: true, constraints })).status).toBe(201);
  }
  const id = await put(page, space, "类型.txt", "类型输入保护");
  const doc = (await api(page, `/documents/${id}`)).data;
  expect((await api(page, `/documents/${id}/metadata`, "PATCH", { expected_document_version: doc.document_version, confirm: true, values: { count: 42, day: "2024-02-29", note: "literal %_", long_note: "长文本", choice: "stable" } })).status).toBe(200);
  await settle(page, space); await advanced(page);
  for (const [index, key, value] of [[1, "count", "42"], [2, "day", "2024-02-29"], [3, "note", "literal %_"], [4, "long_note", "长文本"], [5, "choice", "stable"]]) {
    await form(page).getByRole("button", { name: "添加字段条件" }).click();
    await form(page).getByRole("combobox", { name: `筛选字段 ${index}`, exact: true }).selectOption(key);
    if (key === "choice") await form(page).getByRole("combobox", { name: `筛选值 ${index}`, exact: true }).selectOption(value);
    else await form(page).getByLabel(`筛选值 ${index}`, { exact: true }).fill(value);
  }
  await submit(page); await expect(library(page).getByText("1 份", { exact: true })).toBeVisible();
  const hash = new URL(page.url()).hash;
  await advanced(page); await form(page).getByLabel("筛选值 1", { exact: true }).fill("9007199254740993");
  await submit(page);
  await expect(form(page).getByRole("alert")).toContainText("安全整数");
  expect(new URL(page.url()).hash).toBe(hash);
});
