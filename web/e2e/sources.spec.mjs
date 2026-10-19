import { test, expect } from "@playwright/test";
import {execFileSync} from "node:child_process";
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

test("adopt a real scanned readonly original through the managed copy dialog",async({page})=>{
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await login(page);await createSpace(page,'托管接管验证');
  const space=await page.getByLabel('当前空间').inputValue();
  const source=await api(page,'/sources','POST',{space_id:space,name:'托管接管来源',kind:'external',root_alias:'adoption',initial_import_policy:'flat'});
  expect(source.status).toBe(201);
  const scan=await api(page,`/sources/${source.data.id}/scan`,'POST',{mode:'initial'});expect(scan.status).toBe(202);
  await expect.poll(async()=>(await api(page,`/jobs/${scan.data.job_id}`)).data.status,{timeout:30000}).toBe('completed');
  const entries=(await api(page,`/sources/${source.data.id}/entries`)).data.items;
  expect(entries).toHaveLength(1);const id=entries[0].document_id;
  const old=(await api(page,`/documents/${id}`)).data.current_revision_id;
  const original=await readFile(root+'/adoption/one.txt');
  await page.reload();await page.getByLabel('当前空间').selectOption(space);
  await page.getByRole('region',{name:'档案列表',exact:true}).getByRole('button').filter({hasText:'one.txt'}).click();
  await page.getByRole('button',{name:'关联原文件',exact:true}).click();
  const dialog=page.getByRole('dialog',{name:'关联原文件',exact:true});
  await expect(dialog.getByRole('button',{name:'确认纳入托管',exact:true})).toBeDisabled();
  await dialog.getByLabel('确认将当前外部原件复制为托管版本').check();
  await dialog.getByRole('button',{name:'确认纳入托管',exact:true}).click();
  await expect(dialog.getByRole('heading',{name:'批量操作 · 已完成',exact:true})).toBeVisible({timeout:30000});
  const doc=(await api(page,`/documents/${id}`)).data;expect(doc.current_revision_id).not.toBe(old);
  expect(await readFile(root+'/adoption/one.txt')).toEqual(original);
  const bytes=await page.request.get(`/api/v1/documents/${id}/download`);expect(await bytes.body()).toEqual(original);
  const rules=(await api(page,`/sources/${source.data.id}/exclusions`)).data;
  expect(rules).toHaveLength(1);expect(rules[0].protected).toBe(true);
  const incremental=await api(page,`/sources/${source.data.id}/scan`,'POST',{mode:'incremental'});
  expect(incremental.status).toBe(202);
  await expect.poll(async()=>(await api(page,`/jobs/${incremental.data.job_id}`)).data.status,{timeout:30000}).toBe('completed');
  expect((await api(page,`/documents/${id}`)).data.current_revision_id).toBe(doc.current_revision_id);
  expect((await api(page,`/sources/${source.data.id}/entries`)).data.items[0].is_managed).toBe(true);
  // Temporarily hide this fixture file from the readonly mount; managed bytes stay usable.
  await rename(root+'/adoption/one.txt',root+'/adoption/hidden.bin');
  try {
    expect(await (await page.request.get(`/api/v1/documents/${id}/download`)).body()).toEqual(original);
    expect((await page.request.get(`/api/v1/documents/${id}/download?revision_id=${old}`)).status()).toBe(409);
  } finally {await rename(root+'/adoption/hidden.bin',root+'/adoption/one.txt');}
  await page.setViewportSize({width:390,height:844});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:'/tmp/juanzhan-adoption-mobile.png'});
  await dialog.getByRole('button',{name:'关闭并刷新档案',exact:true}).click();
  await expect(dialog).toHaveCount(0);
  await page.getByRole('button',{name:'关联原文件',exact:true}).click();
  await expect(page.getByRole('region',{name:'纳入托管',exact:true})).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("persistent scan plan queues real daemon incremental work and can be paused",async({page})=>{
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await login(page);await createSpace(page,'自动扫描验证');
  const space=await page.getByLabel('当前空间').inputValue();
  const source=await api(page,'/sources','POST',{space_id:space,name:'自动扫描来源',kind:'external',root_alias:'scheduled',initial_import_policy:'flat'});
  expect(source.status).toBe(201);const id=source.data.id;
  const initial=await api(page,`/sources/${id}/scan`,'POST',{mode:'initial'});expect(initial.status).toBe(202);
  await expect.poll(async()=>(await api(page,`/jobs/${initial.data.job_id}`)).data.status,{timeout:30000}).toBe('completed');
  await page.getByRole('navigation',{name:'档案导航'}).getByRole('button',{name:'来源',exact:true}).click();
  await expect(page.getByRole('heading',{name:'自动扫描来源',exact:true})).toBeVisible();
  await page.getByText('自动扫描设置',{exact:true}).click();
  const form=page.getByRole('form',{name:'自动扫描设置',exact:true});
  await form.getByLabel('扫描间隔（分钟，0为关闭）').fill('1');
  await form.getByRole('button',{name:'保存扫描计划',exact:true}).click();
  await expect(page.getByText('每 1 分钟自动增量扫描',{exact:false})).toBeVisible();
  await expect(form.locator('time')).toHaveText(/\d{1,2}:\d{2}/);
  await expect(form.locator('time')).toHaveAttribute('datetime',/Z$/);
  // Advance the persisted fixture deadline, then let the normal daemon tick enqueue.
  const container=(await readFile(root+'/.container-name','utf8')).trim();
  await writeFile(root+'/scheduled/timed.txt','automatically discovered bytes\n',{mode:0o644});
  execFileSync('docker',['exec',container,'python','-c',"import sqlite3,sys;db=sqlite3.connect('/data/database/archive.sqlite3');db.execute('UPDATE source_scan_schedules SET next_due_at=0 WHERE source_id=?',(sys.argv[1],));db.commit()",id]);
  await expect.poll(async()=>(await api(page,`/sources/${id}/entries`)).data.total,{timeout:30000}).toBe(2);
  const scheduled=(await api(page,`/sources/${id}`)).data.scan_schedule.last_job_id;expect(scheduled).toBeTruthy();
  await expect.poll(async()=>(await api(page,`/jobs/${scheduled}`)).data.status).toBe('completed');
  await page.getByRole('button',{name:'刷新来源',exact:true}).click();
  await form.getByLabel('扫描间隔（分钟，0为关闭）').fill('0');
  await form.getByRole('button',{name:'保存扫描计划',exact:true}).click();
  await expect(page.getByText('自动扫描已关闭',{exact:false})).toBeVisible();
  await page.reload();await page.getByLabel('当前空间').selectOption(space);
  await page.getByRole('navigation',{name:'档案导航'}).getByRole('button',{name:'来源',exact:true}).click();
  await expect(page.getByText('自动扫描已关闭',{exact:false})).toBeVisible();
  await page.setViewportSize({width:390,height:844});await page.getByText('自动扫描设置',{exact:true}).click();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:'/tmp/juanzhan-source-schedule-mobile.png'});
  expect(errors).toEqual([]);
});

test("explicit ambiguity matching preserves manual fields and can register a separate document",async({page})=>{
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await login(page);await createSpace(page,'人工匹配验证');
  const space=await page.getByLabel('当前空间').inputValue();
  const created=await api(page,'/sources','POST',{space_id:space,name:'人工匹配来源',kind:'external',root_alias:'matching',initial_import_policy:'flat'});
  expect(created.status).toBe(201);const source=created.data.id;
  async function scanSource(mode){
    const result=await api(page,`/sources/${source}/scan`,'POST',{mode});expect(result.status).toBe(202);
    await expect.poll(async()=>(await api(page,`/jobs/${result.data.job_id}`)).data.status,{timeout:30000}).toBe('completed');
  }
  await scanSource('initial');
  const originalEntries=(await api(page,`/sources/${source}/entries`)).data.items;
  const original=originalEntries.find(entry=>entry.relative_path==='old-a.txt');
  const old=(await api(page,`/documents/${original.document_id}`)).data;
  expect((await api(page,`/documents/${old.id}`,'PATCH',{expected_document_version:old.document_version,description:'retain manual description',is_favorite:true})).status).toBe(200);
  await rename(root+'/matching/old-a.txt',root+'/matching/new-a.txt');
  await rename(root+'/matching/old-b.txt',root+'/matching/new-b.txt');
  await scanSource('incremental');
  await page.getByRole('navigation',{name:'档案导航'}).getByRole('button',{name:'来源',exact:true}).click();
  await expect(page.getByRole('heading',{name:'人工匹配来源',exact:true})).toBeVisible();
  // Entry names are text, not clickable file links.
  const first=page.locator('.source-entry').filter({has:page.getByText('new-a.txt',{exact:true})});
  await first.getByRole('button',{name:'处理待匹配文件',exact:true}).click();
  let dialog=page.getByRole('dialog',{name:'处理待匹配文件',exact:true});
  await expect(dialog.getByRole('button',{name:'确认处理待匹配文件',exact:true})).toBeDisabled();
  await dialog.getByRole('radio',{name:'old-a.txt · 原路径 old-a.txt',exact:true}).check();
  await dialog.getByLabel('确认此选择，外部文件保持不变').check();
  await page.setViewportSize({width:390,height:844});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:'/tmp/juanzhan-source-match-mobile.png'});
  await dialog.getByRole('button',{name:'确认处理待匹配文件',exact:true}).click();
  await expect(dialog.getByRole('heading',{name:'批量操作 · 已完成',exact:true})).toBeVisible({timeout:30000});
  await dialog.getByRole('button',{name:'关闭并刷新来源',exact:true}).click();
  const linked=(await api(page,`/documents/${old.id}`)).data;
  expect(linked.current_revision_id).toBe(old.current_revision_id);expect(linked.description).toBe('retain manual description');expect(linked.is_favorite).toBe(true);
  const download=await page.request.get(`/api/v1/documents/${old.id}/download`);expect((await download.body()).toString()).toBe('same original bytes for explicit matching\n');
  const second=page.locator('.source-entry').filter({has:page.getByText('new-b.txt',{exact:true})});
  await second.getByRole('button',{name:'处理待匹配文件',exact:true}).click();
  dialog=page.getByRole('dialog',{name:'处理待匹配文件',exact:true});
  await dialog.getByRole('combobox',{name:'处理方式',exact:true}).selectOption('new_document');
  await dialog.getByLabel('确认此选择，外部文件保持不变').check();
  await dialog.getByRole('button',{name:'确认处理待匹配文件',exact:true}).click();
  await expect(dialog.getByRole('heading',{name:'批量操作 · 已完成',exact:true})).toBeVisible({timeout:30000});
  await dialog.getByRole('button',{name:'关闭并刷新来源',exact:true}).click();
  expect((await api(page,`/documents?space_id=${space}`)).data.total).toBe(3);
  expect((await readFile(root+'/matching/new-a.txt','utf8'))).toBe('same original bytes for explicit matching\n');
  expect((await readFile(root+'/matching/new-b.txt','utf8'))).toBe('same original bytes for explicit matching\n');
  expect(errors).toEqual([]);
});
