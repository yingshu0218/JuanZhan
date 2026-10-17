import { test, expect } from "@playwright/test";
import { readFile, writeFile, rename, unlink, chmod } from "node:fs/promises";
import { createSpace, api } from "./helpers.mjs";
const root = process.env.JUANZHAN_E2E_SOURCE_ROOT;
async function login(page) {
  await page.goto("/");
  await expect(page).toHaveTitle("JuanZhan · 档案库");
  await expect(page).toHaveURL("http://127.0.0.1:8768/");
  await page
    .getByLabel("密码", { exact: true })
    .fill(process.env.JUANZHAN_E2E_PASSWORD);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.getByRole("button", { name: "退出登录" })).toBeVisible();
}
async function createSource(page, name, alias, policy = "tree") {
  await page.getByRole("button", { name: "配置来源", exact: true }).click();
  await page.getByLabel("来源名称").fill(name);
  await page.getByLabel("挂载别名").selectOption(alias);
  await page.getByRole("button", { name: "下一步", exact: true }).click();
  await page.getByLabel("首次导入方式").selectOption(policy);
  if (alias === "collection")
    await page.screenshot({
      path: "/tmp/juanzhan-t28-wizard.png",
      fullPage: true,
    });
  await page.getByRole("button", { name: "创建来源", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByRole("heading", { name, exact: true })).toBeVisible();
}
async function scan(page, mode) {
  const button = {
    initial: "首次导入",
    incremental: "增量扫描",
    preview: "预扫描",
  }[mode];
  await page.getByRole("button", { name: button, exact: true }).click();
  if (mode !== "preview") {
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "确认执行" })
      .click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
  }
  await expect(
    page.getByLabel("来源任务结果").getByText(new RegExp(button + " · 已完成")),
  ).toBeVisible({ timeout: 60000 });
}

test("read-only source wizard, real preview/tree/flat import, pagination, absence, ambiguity and exclusion", async ({
  page,
}) => {
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => {
    if (m.type() === "error" && !m.text().includes("409 (Conflict)"))
      errors.push(m.text());
  });
  await login(page);
  await createSpace(page, "来源浏览器验收");
  await page
    .getByRole("navigation", { name: "档案导航" })
    .getByRole("button", { name: "来源", exact: true })
    .click();
  await page.getByRole("button", { name: "配置来源", exact: true }).click();
  await expect(
    page.getByLabel("挂载别名").locator('option[value="writable"]'),
  ).toHaveAttribute("disabled", "");
  await expect(
    page.getByLabel("挂载别名").locator('option[value="offline"]'),
  ).toHaveAttribute("disabled", "");
  await page.getByRole("button", { name: "取消", exact: true }).click();
  await createSource(page, "项目原地资料", "collection");
  await page.evaluate(() => {
    const dataTransfer = new DataTransfer();
    dataTransfer.items.add(
      new File(["should not upload"], "source-drop.txt", {
        type: "text/plain",
      }),
    );
    document.querySelector(".sources-view").dispatchEvent(
      new DragEvent("drop", {
        bubbles: true,
        cancelable: true,
        dataTransfer,
      }),
    );
  });
  await expect(
    page.getByText("来源为只读。请返回档案列表上传，或将文件拖到逻辑目录。", {
      exact: true,
    }),
  ).toBeVisible();
  await page.getByRole("button", { name: "关闭提示", exact: true }).click();
  await scan(page, "preview");
  expect((await api(page, "/documents")).data.total).toBe(0);
  await expect(page.getByLabel("来源任务结果")).toContainText("预计文件33");
  await expect(page.getByLabel("来源任务结果")).toContainText("忽略文件1");
  await scan(page, "initial");
  expect((await api(page, "/documents")).data.total).toBe(33);
  await expect(page.getByText("共 33 项", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "下一页", exact: true }).click();
  await page
    .locator(".source-file-path")
    .getByRole("button", { name: "设计", exact: true })
    .click();
  await expect(page.locator(".source-entry")).toHaveCount(1);
  await expect(page.locator(".source-entry")).toContainText("计划.txt");
  await page.getByRole("button", { name: "查看档案", exact: true }).click();
  await expect(
    page.getByRole("dialog", { name: "来源档案详情", exact: true }),
  ).toContainText("结构化信息");
  await page
    .getByRole("button", { name: "关闭来源档案详情", exact: true })
    .click();
  await expect(page.locator(".source-entry")).toHaveCount(1);
  await page.screenshot({
    path: "/tmp/juanzhan-t28-sources.png",
    fullPage: true,
  });
  // Delay a real GET, navigate away, then release it: no stale confirmation may open.
  const contextSource = (await api(page, "/sources")).data[0];
  const contextEntry = (
    await api(
      page,
      `/sources/${contextSource.id}/entries?relative_prefix=${encodeURIComponent("设计")}`,
    )
  ).data.items[0];
  let releaseRead;
  let markRead;
  const readGate = new Promise((resolve) => {
    releaseRead = resolve;
  });
  const readSeen = new Promise((resolve) => {
    markRead = resolve;
  });
  const docUrl = `**/api/v1/documents/${contextEntry.document_id}`;
  await page.route(docUrl, async (route) => {
    markRead();
    await readGate;
    await route.continue().catch(() => {}); // The app has intentionally aborted this real request.
  });
  await page.getByRole("button", { name: "取消索引", exact: true }).click();
  await readSeen;
  await page
    .getByRole("navigation", { name: "档案导航" })
    .getByRole("button", { name: "全部档案", exact: true })
    .click();
  releaseRead();
  await page.unroute(docUrl);
  await page
    .getByRole("navigation", { name: "档案导航" })
    .getByRole("button", { name: "来源", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.locator(".source-entry")).toHaveCount(1);
  // An offline source retains its stored inventory; restoring the same directory keeps identity.
  await rename(root + "/collection", root + "/collection-offline");
  await page.getByRole("button", { name: "刷新来源" }).click();
  await expect(page.locator(".source-status")).toHaveText("来源离线");
  await expect(
    page.getByRole("button", { name: "增量扫描", exact: true }),
  ).toBeDisabled();
  await expect(page.locator(".source-entry")).toContainText("计划.txt");
  await page.screenshot({
    path: "/tmp/juanzhan-t28-offline.png",
    fullPage: true,
  });
  await rename(root + "/collection-offline", root + "/collection");
  await page.getByRole("button", { name: "刷新来源" }).click();
  await expect(page.locator(".source-status")).toHaveText("在线 · 只读");
  await unlink(root + "/collection/设计/计划.txt");
  await scan(page, "incremental");
  await expect(page.locator(".source-entry")).toContainText("待核验失联");
  await scan(page, "incremental");
  await expect(page.locator(".source-entry")).toContainText("已确认失联");
  await writeFile(root + "/collection/设计/计划.txt", "真实只读来源。\n");
  await chmod(root + "/collection/设计/计划.txt", 0o644);
  await scan(page, "incremental");
  await expect(page.locator(".source-entry")).toContainText("原件可用");
  const before = await readFile(root + "/collection/设计/计划.txt", "utf8");
  await page.getByRole("button", { name: "取消索引", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("外部原文件保留");
  const sourceId = (await api(page, "/sources")).data.find(
    (source) => source.root_alias === "collection",
  ).id;
  const entry = (
    await api(
      page,
      `/sources/${sourceId}/entries?relative_prefix=${encodeURIComponent("设计")}`,
    )
  ).data.items[0];
  const document = (await api(page, `/documents/${entry.document_id}`)).data;
  expect(
    (
      await api(page, `/documents/${document.id}`, "PATCH", {
        expected_document_version: document.document_version,
        description: "并发人工整理",
      })
    ).status,
  ).toBe(200);
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "确认执行" })
    .click();
  await expect(page.getByRole("dialog").getByRole("alert")).toContainText(
    "档案已被更新",
  );
  expect(
    (await api(page, `/documents/${document.id}`)).data.deleted_at,
  ).toBeNull();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "取消", exact: true })
    .click();
  await page.getByRole("button", { name: "取消索引", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("外部原文件保留");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "确认执行" })
    .click();
  await expect(page.getByLabel("来源任务结果")).toContainText(
    "取消索引 · 已完成",
  );
  expect(await readFile(root + "/collection/设计/计划.txt", "utf8")).toBe(
    before,
  );
  await page.getByRole("button", { name: /排除规则/ }).click();
  await expect(page.locator(".source-entry")).toContainText("设计/计划.txt");
  await page.getByRole("button", { name: "移除规则", exact: true }).click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "确认执行" })
    .click();
  await expect(
    page.getByText("排除规则已移除；未自动恢复档案。", { exact: true }),
  ).toBeVisible();
  expect((await api(page, "/documents?trash=only")).data.total).toBe(1);
  // Two new identical paths remain ambiguous; the UI never offers an invented matching action.
  await writeFile(root + "/collection/duplicate-a.txt", "保留原件\n");
  await writeFile(root + "/collection/duplicate-b.txt", "保留原件\n");
  await chmod(root + "/collection/duplicate-a.txt", 0o644);
  await chmod(root + "/collection/duplicate-b.txt", 0o644);
  await unlink(root + "/collection/keep.txt");
  await scan(page, "incremental");
  await page.getByRole("button", { name: "来源文件", exact: true }).click();
  await page.getByRole("button", { name: "来源根目录", exact: true }).click();
  await expect(
    page.locator(".source-entry").filter({ hasText: "duplicate-a.txt" }),
  ).toContainText("待人工匹配");
  await page.setViewportSize({ width: 1024, height: 768 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.setViewportSize({ width: 390, height: 844 });
  await page
    .locator(".source-entry")
    .filter({ hasText: "duplicate-a.txt" })
    .scrollIntoViewIfNeeded();
  await page.screenshot({
    path: "/tmp/juanzhan-t28-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await createSource(page, "平铺来源", "flat", "flat");
  await scan(page, "initial");
  await expect(page.locator(".source-entry")).toContainText("one.txt");
  await expect(page.locator("vite-error-overlay")).toHaveCount(0);
  expect(errors).toEqual([]);
});
