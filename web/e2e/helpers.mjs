import { expect } from "@playwright/test";
export async function login(page) {
  await page.goto("/");
  await expect(page).toHaveTitle("JuanZhan · 档案库");
  await expect(page).toHaveURL("http://127.0.0.1:8767/");
  await expect(page.locator("vite-error-overlay")).toHaveCount(0);
  await page
    .getByLabel("密码", { exact: true })
    .fill(process.env.JUANZHAN_E2E_PASSWORD);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.getByRole("button", { name: "退出登录" })).toBeVisible();
}
export async function createSpace(page, name) {
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "新建空间", exact: true })
    .click();
  await page.getByLabel("空间名称").fill(name);
  await page.getByRole("button", { name: "创建", exact: true }).click();
  await expect(
    page.getByRole("dialog", { name: "新建空间", exact: true }),
  ).not.toBeVisible();
  await expect(
    page.getByLabel("当前空间").locator("option:checked"),
  ).toHaveText(name);
}
export async function api(page, path, method = "GET", body) {
  return page.evaluate(
    async ({ path, method, body }) => {
      const session = await fetch("/api/v1/auth/session").then((r) => r.json());
      const response = await fetch("/api/v1" + path, {
        method,
        headers: {
          "X-CSRF-Token": session.csrf_token,
          ...(body ? { "Content-Type": "application/json" } : {}),
        },
        ...(body ? { body: JSON.stringify(body) } : {}),
      });
      return {
        status: response.status,
        data: response.status === 204 ? null : await response.json(),
      };
    },
    { path, method, body },
  );
}
