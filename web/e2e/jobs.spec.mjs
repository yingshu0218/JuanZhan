import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { login, createSpace, api } from "./helpers.mjs";

test("upload links directly to persistent automatically refreshed task progress", async ({ page }) => {
  const errors = []; page.on("pageerror", error => errors.push(error.message));
  page.on("console", entry => { if (entry.type() === "error") errors.push(entry.text()); });
  await login(page); await createSpace(page, "进度入口验证");
  const buffer = execFileSync("../.venv/bin/python", ["-c", "import sys;sys.path.insert(0,'../tests');from format_samples import docx;sys.stdout.buffer.write(docx())"]);
  const responsePromise = page.waitForResponse(r => r.url().endsWith("/api/v1/documents/upload") && r.request().method() === "POST");
  await page.getByLabel("选择上传文件", { exact: true }).setInputFiles({ name: "进度验证.docx", mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document", buffer });
  const receipt = await (await responsePromise).json();
  await page.getByRole("button", { name: "查看解析进度", exact: true }).click();
  const center = page.getByRole("dialog", { name: "任务中心", exact: true });
  await expect(center.getByRole("region", { name: "任务详情", exact: true }).getByText(receipt.job_id, { exact: true })).toBeVisible();
  await expect(center.getByRole("heading", { name: "解析 · 已完成", exact: true })).toBeVisible({ timeout: 30000 });
  const detail = center.getByRole("region", { name: "任务详情", exact: true });
  await expect(detail.locator(".job-filename")).toHaveText("进度验证.docx");
  await expect(detail.getByRole("list", { name: "按顺序排列的处理步骤" }).getByRole("listitem")).toHaveCount(5);
  await expect(detail.getByRole("progressbar")).toHaveCount(6);
  await expect(detail.getByLabel("文件总体步骤进度")).toHaveAttribute("value", "5");
  for (const label of ["读取并校验原件", "提交转换任务", "提取正文 / OCR（如启用）", "保存派生文件", "写入正文与候选"]) {
    await expect(detail.getByLabel(label + "进度", { exact: true })).toHaveAttribute("value", "1");
  }

  const space = await page.getByLabel("当前空间").inputValue();
  const csrf = (await api(page, "/auth/session")).data.csrf_token;
  const response = await page.request.post("/api/v1/documents/upload", { headers: { "X-CSRF-Token": csrf }, multipart: { space_id: space, file: { name: "自动刷新.txt", mimeType: "text/plain", buffer: Buffer.from("New background task") } } });
  expect(response.status()).toBe(201); const second = await response.json();
  await expect(center.locator(".task-row").filter({ hasText: second.job_id })).toBeVisible({ timeout: 10000 });
  await page.screenshot({ path: "/tmp/juanzhan-progress-center-desktop.png" });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: "/tmp/juanzhan-progress-center-mobile.png" });
  await center.getByRole("button", { name: "关闭任务中心", exact: true }).click();
  await expect(page.getByRole("button", { name: "任务中心", exact: true })).toContainText(/排队 \d+ · 处理中 \d+/);
  await page.reload(); await page.getByRole("button", { name: "任务中心", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "任务中心", exact: true }).locator(".task-row").filter({ hasText: receipt.job_id })).toBeVisible();
  expect(errors).toEqual([]);
});

test("batch reprocessing confirms options and tracks actual child tasks", async ({ page }) => {
  const errors = []; page.on("pageerror", error => errors.push(error.message));
  await login(page); await createSpace(page, "批量解析验证");
  const space = await page.getByLabel("当前空间").inputValue();
  const csrf = (await api(page, "/auth/session")).data.csrf_token;
  const ids = [];
  for (let index = 0; index < 2; index++) {
    const response = await page.request.post("/api/v1/documents/upload", {
      headers: { "X-CSRF-Token": csrf },
      multipart: { space_id: space, file: { name: `批量原件${index}.txt`, mimeType: "text/plain", buffer: Buffer.from(`Batch original ${index}`) } },
    });
    expect(response.status()).toBe(201); ids.push((await response.json()).document_id);
  }
  for (const id of ids) await expect.poll(async () => (await api(page, `/documents/${id}`)).data.processing_status, { timeout: 30000 }).toBe("completed");
  await page.reload();
  await page.getByLabel("全选当前页", { exact: true }).check();
  await page.getByRole("button", { name: "批量操作", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "档案操作", exact: true });
  await dialog.getByLabel("操作类型").selectOption("reprocess");
  await expect(dialog.getByLabel("启用 OCR（耗时较长）")).not.toBeChecked();
  await expect(dialog.getByRole("button", { name: "确认提交", exact: true })).toBeDisabled();
  await dialog.getByLabel("启用 OCR（耗时较长）").check();
  await dialog.getByLabel("OCR 语言").selectOption("chi_sim");
  await dialog.getByLabel("启用 OCR（耗时较长）").uncheck();
  await dialog.getByLabel("确认重新处理所选原件，包括已有成功结果").check();
  await dialog.getByRole("button", { name: "确认提交", exact: true }).click();
  const result = page.getByRole("dialog", { name: "操作结果", exact: true });
  await expect(result.locator(".result-counts")).toHaveText(/成功 2.*失败 0/);
  await expect(result.getByText("成功表示已排入解析队列", { exact: false })).toBeVisible();
  await expect(result.getByRole("button", { name: "撤销本次成功变更" })).toHaveCount(0);
  await result.getByRole("button", { name: "查看解析任务", exact: true }).first().click();
  await expect(result.getByRole("heading", { name: "解析 · 已完成", exact: true })).toBeVisible({ timeout: 30000 });
  for (const id of ids) { await expect.poll(async () => (await api(page, `/documents/${id}/parse-runs`)).data.total, {timeout:30000}).toBe(2); await expect.poll(async () => (await api(page, `/documents/${id}`)).data.processing_status, {timeout:30000}).toBe("completed"); }
  await page.screenshot({ path: "/tmp/juanzhan-batch-reprocess-desktop.png" });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: "/tmp/juanzhan-batch-reprocess-mobile.png" });
  expect(errors).toEqual([]);
});
test("durable tasks and explicit real reprocessing on desktop and mobile", async ({ page }) => {
  const errors = []; page.on("pageerror", e => errors.push(e.message));
  page.on("console", e => { if(e.type()==="error") errors.push(e.text()); });
  await login(page); await createSpace(page, "任务验证");
  const space = (await api(page, "/spaces")).data.find(x => x.name === "任务验证").id;
  const buffer = execFileSync("../.venv/bin/python", ["-c", "import sys;sys.path.insert(0,'../tests');from format_samples import docx;sys.stdout.buffer.write(docx())"]);
  const response = await page.request.post("/api/v1/documents/upload", { headers: {"X-CSRF-Token": (await api(page, "/auth/session")).data.csrf_token}, multipart: { space_id: space, file: {name:"任务原件.docx",mimeType:"application/vnd.openxmlformats-officedocument.wordprocessingml.document",buffer} } });
  expect(response.status()).toBe(201); const upload = await response.json();
  await expect.poll(async () => (await api(page, `/documents/${upload.document_id}`)).data.processing_status, {timeout:30000}).toBe("completed");
  await page.reload(); await page.getByLabel("当前空间").selectOption(space);
  await page.getByRole("region",{name:"档案列表",exact:true}).getByRole("button").filter({hasText:"任务原件"}).click();
  await page.getByRole("button",{name:"整理操作",exact:true}).click();
  const dialog = page.getByRole("dialog", {name:"档案操作",exact:true});
  await dialog.getByLabel("操作类型").selectOption("reprocess");
  await expect(dialog.getByLabel("启用 OCR（耗时较长）")).not.toBeChecked();
  await expect(dialog.getByRole("button",{name:"确认提交",exact:true})).toBeDisabled();
  await dialog.getByLabel("启用 OCR（耗时较长）").check();
  await dialog.getByLabel("OCR 语言").selectOption("eng,chi_sim");
  await expect(dialog.getByLabel("OCR 语言")).toHaveValue("eng,chi_sim");
  await dialog.getByLabel("启用 OCR（耗时较长）").uncheck();
  await dialog.getByLabel("确认重新处理所选原件，包括已有成功结果").check();
  await dialog.getByRole("button",{name:"确认提交",exact:true}).click();
  const result = page.getByRole("dialog", {name:"操作结果",exact:true});
  await expect(result.locator(".result-counts")).toHaveText(/成功 1.*失败 0/);
  await result.getByRole("button",{name:"查看解析任务",exact:true}).click();
  await expect(result.getByRole("heading",{name:"解析 · 已完成"})).toBeVisible({timeout:30000});
  const jobId = await result.locator(".task-status code").textContent();
  await result.getByRole("button",{name:"关闭操作结果"}).click();
  await page.reload(); await page.getByRole("button",{name:"任务中心",exact:true}).click();
  const center = page.getByRole("dialog",{name:"任务中心",exact:true});
  await expect(center.locator(".task-row").filter({hasText:jobId})).toBeVisible();
  await center.locator(".task-row").filter({hasText:jobId}).click();
  await expect(center.getByRole("heading",{name:"解析 · 已完成"})).toBeVisible();
  await expect(center.getByRole("button",{name:"确认重试（沿用剩余次数）"})).toHaveCount(0);
  await page.screenshot({path:"/tmp/juanzhan-t31-desktop.png"});
  await page.setViewportSize({width:390,height:844});
  await expect(center).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({path:"/tmp/juanzhan-t31-mobile.png"});
  await center.getByLabel("任务状态").selectOption("failed"); await expect(center.getByText("暂无任务",{exact:true})).toBeVisible();
  await expect(page.locator("vite-error-overlay")).toHaveCount(0); expect(errors).toEqual([]);
});

test("actual corrupt original reports failure without offering terminal retry", async ({ page }) => {
  await login(page); await createSpace(page, "损坏原件任务");
  const space = (await api(page, "/spaces")).data.find(x => x.name === "损坏原件任务").id;
  const response = await page.request.post("/api/v1/documents/upload", { headers: {"X-CSRF-Token":(await api(page,"/auth/session")).data.csrf_token}, multipart: {space_id:space,file:{name:"损坏.pdf",mimeType:"application/pdf",buffer:Buffer.from("%PDF-1.7\ncorrupt-original")}} });
  expect(response.status()).toBe(201); const receipt = await response.json();
  await expect.poll(async () => (await api(page,`/jobs/${receipt.job_id}`)).data.status,{timeout:30000}).toBe("failed");
  await page.getByRole("button",{name:"任务中心",exact:true}).click();
  const center = page.getByRole("dialog",{name:"任务中心",exact:true});
  await center.getByLabel("任务状态").selectOption("failed");
  await center.locator(".task-row").filter({hasText:receipt.job_id}).click();
  await expect(center.getByRole("heading",{name:"解析 · 失败"})).toBeVisible();
  const detail = center.getByRole("region", { name: "任务详情", exact: true });
  await expect(detail.locator(".job-filename")).toHaveText("损坏.pdf");
  await expect(detail.locator(".job-step.failed")).toHaveCount(1);
  await expect(detail.locator(".job-step.pending")).toHaveCount(2);

  await expect(center.getByText("错误代码：",{exact:false})).toBeVisible();
  await expect(center.getByRole("button",{name:"确认重试（沿用剩余次数）"})).toHaveCount(0);
  const doc = (await api(page,`/documents/${receipt.document_id}`)).data;
  expect(doc.processing_status).toBe("failed"); expect(doc.current_revision_id).toBeTruthy();
});
