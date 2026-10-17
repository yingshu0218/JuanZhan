import { test, expect } from "@playwright/test";
import { randomUUID } from "node:crypto";

import { login, createSpace, api } from "./helpers.mjs";

test("real login, first space, upload, duplicate decision, details, responsive and logout", async ({
  page,
}) => {
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => {
    if (m.type() === "error" && !m.text().includes("409 (Conflict)"))
      errors.push(m.text());
  });
  await login(page);
  await expect(
    page.getByRole("heading", { name: "建立你的第一个空间" }),
  ).toBeVisible();
  await createSpace(page, "项目资料");
  await expect(
    page.getByRole("heading", { name: "这里还没有档案" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "新建目录", exact: true }).click();
  await page.getByLabel("目录名称").fill("档案库设计");
  await page.getByRole("button", { name: "创建", exact: true }).click();
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "档案库设计", exact: true })
    .click();
  const file = {
    name: "系统设计方案.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("真实的系统设计原件。\n"),
  };
  await page.getByLabel("选择上传文件").setInputFiles(file);
  await expect(
    page.getByLabel("上传队列").getByText("原件已保存", { exact: false }),
  ).toBeVisible();
  await page.getByRole("button", { name: "收起上传队列" }).click();
  await page
    .getByRole("region", { name: "档案列表", exact: true })
    .getByRole("button")
    .filter({ hasText: "系统设计方案.txt" })
    .click();
  await expect(page.getByText("结构化信息", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "正文内容", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "业务字段", exact: true }),
  ).toBeVisible();
  const list = await api(page, "/documents");
  const id = list.data.items[0].id;
  const spaceId = list.data.items[0].space_id;
  const field = await api(page, "/field-definitions", "POST", {
    space_id: spaceId,
    key: "amount",
    label: "合同金额",
    type: "decimal",
    constraints: { min: "2.00", max: "10.00" },
  });
  expect(field.status).toBe(201);
  expect(
    (
      await api(page, "/documents/" + id + "/metadata", "PATCH", {
        expected_document_version: 1,
        values: { amount: "2.00" },
        confirm: true,
      })
    ).status,
  ).toBe(200);
  await page.getByRole("button", { name: "全部档案", exact: true }).click();
  await page
    .getByRole("region", { name: "档案列表", exact: true })
    .getByRole("button")
    .filter({ hasText: "系统设计方案.txt" })
    .click();
  await expect(
    page.getByRole("term").filter({ hasText: "合同金额" }),
  ).toBeVisible();
  await expect(page.getByText("2.0000", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "档案属性" })).toBeVisible();
  await expect(page.getByRole("button", { name: "网格视图" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await page.screenshot({ path: "/tmp/juanzhan-desktop.png", fullPage: true });
  await page.getByRole("button", { name: "关联原文件", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "关联原文件" })).toBeVisible();
  await expect(
    page.getByText("原件预览与下载尚未开放。", { exact: false }),
  ).toBeVisible();
  await expect(page.getByRole("dialog")).toContainText("text/plain");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await page.getByRole("button", { name: "列表视图" }).click();
  await expect(page.getByRole("button", { name: "列表视图" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await page.getByLabel("选择上传文件").setInputFiles(file);
  await expect(
    page.getByRole("button", { name: "仍要另存为独立档案" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "仍要另存为独立档案" }).click();
  await expect(
    page.getByLabel("上传队列").getByText("原件已保存", { exact: false }),
  ).toHaveCount(2);
  await page.getByRole("button", { name: "收起上传队列" }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(
    page.getByRole("heading", { name: "正文内容", exact: true }),
  ).toBeVisible();
  await page.screenshot({ path: "/tmp/juanzhan-mobile.png", fullPage: true });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.getByRole("button", { name: "返回档案列表" }).click();
  await expect(
    page.getByRole("region", { name: "档案列表", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "打开导航" }).click();
  await page.getByRole("button", { name: "已收藏", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "这里还没有档案" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "退出登录" }).click();
  await expect(
    page.getByRole("heading", { name: "欢迎回到档案库" }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "欢迎回到档案库" }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

test("list pagination, sorting, space isolation and rejected stale-session access", async ({
  page,
}) => {
  await login(page);
  const name = "分页-" + randomUUID().slice(0, 6);
  await createSpace(page, name);
  const spaceId = await page.getByLabel("当前空间").inputValue();
  // Seed through the real upload endpoint, never browser route mocks.
  await page.evaluate(async (spaceId) => {
    const session = await fetch("/api/v1/auth/session").then((r) => r.json());
    for (let i = 0; i < 31; i++) {
      const body = new FormData();
      body.set("space_id", spaceId);
      body.set(
        "file",
        new File(
          ["document " + i],
          "档案-" + String(i).padStart(2, "0") + ".txt",
          { type: "text/plain" },
        ),
      );
      const response = await fetch("/api/v1/documents/upload", {
        method: "POST",
        headers: { "X-CSRF-Token": session.csrf_token },
        body,
      });
      if (response.status !== 201) throw Error("Fixture upload failed");
    }
  }, spaceId);
  await page.reload();
  await page.getByLabel("当前空间").selectOption(spaceId);
  await expect(
    page
      .getByRole("region", { name: "档案列表", exact: true })
      .getByText("31 份", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("排序", { exact: true }).selectOption("title");
  await expect(
    page
      .getByRole("region", { name: "档案列表", exact: true })
      .getByRole("button")
      .filter({ hasText: "档案-00.txt" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "下一页" }).click();
  await expect(
    page
      .getByRole("region", { name: "档案列表", exact: true })
      .getByRole("button")
      .filter({ hasText: "档案-30.txt" }),
  ).toBeVisible();
  await page.setViewportSize({ width: 1024, height: 768 });
  await page
    .getByRole("region", { name: "档案列表", exact: true })
    .getByRole("button")
    .filter({ hasText: "档案-30.txt" })
    .click();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await api(page, "/auth/logout", "POST");
  // Detail reads can already receive 401 before this next interaction.
  // Either route must end on the real expired-session login screen.
  await page.getByRole("button", { name: "已收藏", exact: true }).click({ timeout: 2000 }).catch(async () => {
    await expect(page.getByRole("heading", { name: "欢迎回到档案库" })).toBeVisible();
  });
  await expect(
    page.getByRole("heading", { name: "欢迎回到档案库" }),
  ).toBeVisible();
  await expect(
    page.getByText("会话已过期，请重新登录。", { exact: true }),
  ).toBeVisible();
});

test("network failure differs from empty results; upload limits and cancellation are truthful", async ({
  page,
  context,
}) => {
  await login(page);
  await createSpace(page, "异常状态-" + randomUUID().slice(0, 6));
  await context.setOffline(true);
  await page.getByRole("button", { name: "已收藏", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "档案暂时无法读取" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "这里还没有档案" }),
  ).not.toBeVisible();
  await context.setOffline(false);
  await page.getByRole("button", { name: "重新加载", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "这里还没有档案" }),
  ).toBeVisible();
  await page.getByLabel("选择上传文件").setInputFiles({
    name: "too-large.txt",
    mimeType: "text/plain",
    buffer: Buffer.alloc(40000, 65),
  });
  await expect(
    page.getByText("文件超过当前上传限制。", { exact: true }),
  ).toBeVisible();
  let release;
  const gate = new Promise((resolve) => (release = resolve));
  await page.route("**/api/v1/documents/upload", async (route) => {
    await gate;
    try {
      await route.continue();
    } catch {
      /* The real XHR may already have been cancelled. */
    }
  });
  try {
    await page.getByLabel("选择上传文件").setInputFiles([
      {
        name: "active.txt",
        mimeType: "text/plain",
        buffer: Buffer.alloc(8000, 65),
      },
      {
        name: "waiting.txt",
        mimeType: "text/plain",
        buffer: Buffer.from("waiting"),
      },
    ]);
    await page
      .getByRole("button", { name: "取消上传 waiting.txt", exact: true })
      .click();
    await expect(
      page.getByText("已从等待队列移除。", { exact: true }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "取消上传 active.txt", exact: true })
      .click();
    await expect(
      page.getByText("已停止等待，原件可能已保存，请刷新核对。", {
        exact: true,
      }),
    ).toBeVisible();
  } finally {
    release();
    await page.unroute("**/api/v1/documents/upload");
  }
});
