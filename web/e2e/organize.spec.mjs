import { test, expect } from "@playwright/test";
import { randomUUID } from "node:crypto";
import { login, createSpace, api } from "./helpers.mjs";
async function seed(page, names, reload = true) {
  const space = await page.getByLabel("当前空间").inputValue();
  const saved = await page.evaluate(
    async ({ space, names }) => {
      const session = await fetch("/api/v1/auth/session").then((r) => r.json());
      const saved = [];
      for (const name of names) {
        const body = new FormData();
        body.set("space_id", space);
        body.set(
          "file",
          new File(["原件 " + name], name, { type: "text/plain" }),
        );
        const response = await fetch("/api/v1/documents/upload", {
          method: "POST",
          headers: { "X-CSRF-Token": session.csrf_token },
          body,
        });
        if (response.status !== 201) throw Error("Upload fixture failed");
        saved.push(await response.json());
      }
      return saved;
    },
    { space, names },
  );
  if (!reload) return saved;
  await page.reload();
  await page.getByLabel("当前空间").selectOption(space);
  await expect(
    page
      .getByRole("region", { name: "档案列表", exact: true })
      .getByText(names.length + " 份", { exact: true }),
  ).toBeVisible();
  return saved;
}
async function closeResult(page, title = "操作结果") {
  await page.getByRole("button", { name: "关闭" + title, exact: true }).click();
}
async function submit(page, operation) {
  if (operation)
    await page.getByLabel("操作类型", { exact: true }).selectOption(operation);
  await page.getByRole("button", { name: "确认提交", exact: true }).click();
  await expect(page.locator(".result-counts")).toBeVisible({ timeout: 30000 });
}
async function createFolder(page, name) {
  await page.getByRole("button", { name: "新建目录", exact: true }).click();
  await page.getByLabel("目录名称").fill(name);
  await page.getByRole("button", { name: "创建", exact: true }).click();
  await expect(
    page.getByRole("dialog", { name: "新建目录" }),
  ).not.toBeVisible();
  await expect(
    page.getByRole("navigation").getByRole("button", { name, exact: true }),
  ).toBeVisible();
}
async function createTag(page, name) {
  await page.getByRole("button", { name: "新建标签", exact: true }).click();
  await page.getByLabel("标签名称").fill(name);
  await page.getByRole("button", { name: "创建", exact: true }).click();
  await expect(
    page.getByRole("dialog", { name: "新建标签" }),
  ).not.toBeVisible();
  await expect(
    page.getByRole("button", { name: "标签 " + name, exact: true }),
  ).toBeVisible();
}

test("seven typed business fields set, clear and undo without losing other values", async ({ page }) => {
  const errors=[]; page.on("pageerror", error => errors.push(error.message));
  await login(page); await createSpace(page, "字段编辑-"+randomUUID().slice(0,5));
  const space=await page.getByLabel("当前空间").inputValue();
  const fields=[
    {key:"short",label:"简述",type:"text",value:"保留其他字段"},
    {key:"long",label:"说明",type:"long_text",value:"第一行\n第二行"},
    {key:"number",label:"数量",type:"integer",value:9007199254740991},
    {key:"money",label:"金额",type:"decimal",value:"2.0001"},
    {key:"date",label:"日期",type:"date",value:"2026-10-19"},
    {key:"flag",label:"复核",type:"boolean",value:false},
    {key:"choice",label:"选项",type:"single_select",value:"stable-a",constraints:{options:[{id:"stable-a",label:"选项甲"}]}},
  ];
  for(const field of fields){
    const response=await api(page,"/field-definitions","POST",{space_id:space,key:field.key,label:field.label,type:field.type,constraints:field.constraints||{}});
    expect(response.status).toBe(201); field.id=response.data.id;
  }
  const docs=await seed(page,["字段甲.txt","字段乙.txt"]);
  const expected={};
  for(const field of fields){
    await page.getByLabel("全选当前页",{exact:true}).check();
    await page.getByRole("button",{name:"批量操作",exact:true}).click();
    await page.getByLabel("操作类型").selectOption("set_metadata");
    await page.getByRole("combobox",{name:"业务字段",exact:true}).selectOption(field.id);
    await expect(page.getByRole("button",{name:"确认提交",exact:true})).toBeDisabled();
    if(["boolean","single_select"].includes(field.type)) await page.getByLabel(/^字段值/).selectOption(String(field.value));
    else await page.getByLabel(/^字段值/).fill(String(field.value));
    await page.getByLabel("确认对所选档案设置此字段",{exact:true}).check();
    await submit(page);
    await expect(page.locator(".result-counts")).toHaveText(/成功 2.*失败 0/);
    expected[field.key]=field.value;
    for(const doc of docs) expect(Object.fromEntries((await api(page,`/documents/${doc.document_id}/metadata`)).data.map(row=>[row.key,row.value]))).toEqual(expected);
    await closeResult(page);
  }
  await page.getByLabel("全选当前页",{exact:true}).check();
  await page.getByRole("button",{name:"批量操作",exact:true}).click();
  await page.getByLabel("操作类型").selectOption("set_metadata");
  await page.getByRole("combobox",{name:"业务字段",exact:true}).selectOption(fields[5].id);
  await page.getByRole("combobox",{name:"字段操作",exact:true}).selectOption("clear");
  await page.getByLabel("确认对所选档案清空此字段",{exact:true}).check();
  await page.screenshot({path:"/tmp/juanzhan-batch-fields-desktop.png"});
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:"/tmp/juanzhan-batch-fields-mobile.png"});
  await submit(page);
  await expect(page.locator(".result-counts")).toHaveText(/成功 2.*失败 0/);
  for(const doc of docs) expect((await api(page,`/documents/${doc.document_id}/metadata`)).data.some(row=>row.key==="flag")).toBe(false);
  await page.getByRole("button",{name:"撤销本次成功变更",exact:true}).click();
  await expect(page.getByRole("dialog",{name:"撤销结果",exact:true}).locator(".result-counts")).toHaveText(/成功 2.*失败 0/);
  for(const doc of docs) expect(Object.fromEntries((await api(page,`/documents/${doc.document_id}/metadata`)).data.map(row=>[row.key,row.value]))).toEqual(expected);
  expect(errors).toEqual([]);
});

test("metadata batch preserves concurrent edits and rejects unsafe browser integers", async ({ page }) => {
  await login(page); await createSpace(page,"字段冲突-"+randomUUID().slice(0,5));
  const space=await page.getByLabel("当前空间").inputValue();
  const definition=await api(page,"/field-definitions","POST",{space_id:space,key:"count",label:"数量",type:"integer"});
  const docs=await seed(page,["并发甲.txt","并发乙.txt"]);
  await page.getByLabel("全选当前页",{exact:true}).check();
  await page.getByRole("button",{name:"批量操作",exact:true}).click();
  await page.getByLabel("操作类型").selectOption("set_metadata");
  await page.getByRole("combobox",{name:"业务字段",exact:true}).selectOption(definition.data.id);
  await page.getByLabel(/^字段值/).fill("9007199254740992");
  await page.getByLabel("确认对所选档案设置此字段",{exact:true}).check();
  await page.getByRole("button",{name:"确认提交",exact:true}).click();
  await expect(page.getByRole("alert")).toContainText("安全整数");
  expect((await api(page,`/documents/${docs[0].document_id}/metadata`)).data).toEqual([]);
  await page.getByLabel(/^字段值/).fill("42");
  expect((await api(page,`/documents/${docs[1].document_id}`,"PATCH",{expected_document_version:1,title:"并发保留"})).status).toBe(200);
  await submit(page);
  await expect(page.locator(".result-counts")).toHaveText(/成功 1.*失败 1/);
  await page.getByRole("button",{name:"撤销本次成功变更",exact:true}).click();
  await expect(page.getByRole("dialog",{name:"撤销结果",exact:true}).locator(".result-counts")).toHaveText(/成功 1.*失败 0/);
  expect((await api(page,`/documents/${docs[0].document_id}/metadata`)).data).toEqual([]);
  expect((await api(page,`/documents/${docs[1].document_id}`)).data.title).toBe("并发保留");
});

test("frozen batch versions produce partial results and guarded undo", async ({
  page,
}) => {
  await login(page);
  await createSpace(page, "逐项结果-" + randomUUID().slice(0, 5));
  const docs = await seed(page, ["合同说明.txt", "技术资料.txt"]);
  await page.getByLabel("全选当前页", { exact: true }).check();
  await page.getByRole("button", { name: "批量操作", exact: true }).click();
  await page.getByLabel("操作类型").selectOption("set_triage");
  expect(
    (
      await api(page, "/documents/" + docs[1].document_id, "PATCH", {
        expected_document_version: 1,
        is_favorite: true,
      })
    ).status,
  ).toBe(200);
  await submit(page);
  await expect(page.locator(".result-counts")).toHaveText(/成功 1.*失败 1/);
  await expect(
    page.getByText("档案已被更新，本项未修改，请刷新后重新选择。", {
      exact: true,
    }),
  ).toBeVisible();
  expect(
    (await api(page, "/documents/" + docs[0].document_id)).data.triage_status,
  ).toBe("filed");
  expect(
    (await api(page, "/documents/" + docs[1].document_id)).data.triage_status,
  ).toBe("needs_review");
  await page.screenshot({
    path: "/tmp/juanzhan-t27-results.png",
    fullPage: true,
  });
  expect(
    (
      await api(page, "/documents/" + docs[0].document_id, "PATCH", {
        expected_document_version: 2,
        title: "后续人工修改",
      })
    ).status,
  ).toBe(200);
  await page
    .getByRole("button", { name: "撤销本次成功变更", exact: true })
    .click();
  await expect(page.getByRole("dialog", { name: "撤销结果" })).toBeVisible();
  await expect(page.locator(".result-counts")).toHaveText(/成功 0.*失败 1/);
  expect(
    (await api(page, "/documents/" + docs[0].document_id)).data.title,
  ).toBe("后续人工修改");
  await closeResult(page, "撤销结果");
  await page.getByRole("button", { name: "收件箱", exact: true }).click();
  await expect(
    page
      .getByRole("region", { name: "档案列表", exact: true })
      .getByText("1 份", { exact: true }),
  ).toBeVisible();
});

test("tag, favorite, trash and durable batch restore retain classification on desktop and mobile", async ({
  page,
}) => {
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await login(page);
  await createSpace(page, "整理流程-" + randomUUID().slice(0, 5));
  await createFolder(page, "项目目录");
  await createTag(page, "重要");
  await createTag(page, "参考");
  const docs = await seed(page, ["项目合同.txt", "项目附件.txt"]);
  await page.getByRole("button", { name: "选择筛选结果", exact: true }).click();
  await expect(page.getByRole("region", { name: "已选档案" })).toContainText(
    "已选 2 份",
  );
  await page.getByRole("button", { name: "批量操作", exact: true }).click();
  await page.getByLabel("目标目录").selectOption({ label: "项目目录" });
  await submit(page);
  await expect(page.locator(".result-counts")).toHaveText(/成功 2.*失败 0/);
  await closeResult(page);
  await expect(
    page.getByLabel("选择档案 项目合同.txt", { exact: true }),
  ).not.toBeChecked();
  await page.getByLabel("全选当前页", { exact: true }).check();
  await page.screenshot({
    path: "/tmp/juanzhan-t27-desktop.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "批量操作", exact: true }).click();
  await page.getByLabel("操作类型").selectOption("add_tags");
  await page.getByRole("dialog", { name: "档案操作", exact: true }).getByLabel("重要", { exact: true }).check();
  await page.getByRole("dialog", { name: "档案操作", exact: true }).getByLabel("参考", { exact: true }).check();
  await submit(page);
  await expect(page.locator(".result-counts")).toHaveText(/成功 2.*失败 0/);
  await closeResult(page);
  await page.getByLabel("全选当前页", { exact: true }).check();
  await page.getByRole("button", { name: "批量操作", exact: true }).click();
  await page.getByLabel("操作类型").selectOption("remove_tags");
  await page.getByRole("dialog", { name: "档案操作", exact: true }).getByLabel("重要", { exact: true }).check();
  await submit(page);
  await expect(page.locator(".result-counts")).toHaveText(/成功 2.*失败 0/);
  await closeResult(page);
  expect(
    (await api(page, "/documents/" + docs[0].document_id)).data.tag_ids,
  ).toHaveLength(1);
  await page.getByLabel("全选当前页", { exact: true }).check();
  await page.getByRole("button", { name: "标签 重要", exact: true }).click();
  await submit(page);
  await expect(page.locator(".result-counts")).toHaveText(/成功 2.*失败 0/);
  await closeResult(page);
  await page
    .getByRole("region", { name: "档案列表", exact: true })
    .getByRole("button")
    .filter({ hasText: "项目合同.txt" })
    .click();
  await page.getByRole("button", { name: "整理操作", exact: true }).click();
  await page.getByLabel("操作类型").selectOption("set_favorite");
  await submit(page);
  await expect(page.locator(".result-counts")).toHaveText(/成功 1/);
  await closeResult(page);
  await page.getByLabel("全选当前页", { exact: true }).check();
  await page.getByRole("button", { name: "批量操作", exact: true }).click();
  await page.getByLabel("操作类型").selectOption("trash");
  await expect(page.getByText(/确认将这 2 份档案加入回收站/)).toBeVisible();
  await submit(page);
  await expect(page.locator(".result-counts")).toHaveText(/成功 2.*失败 0/);
  await closeResult(page);
  await page.getByRole("button", { name: "回收站", exact: true }).click();
  await expect(
    page
      .getByRole("region", { name: "档案列表", exact: true })
      .getByText("2 份", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("全选当前页", { exact: true }).check();
  await page.getByRole("button", { name: "批量操作", exact: true }).click();
  await expect(page.getByLabel("操作类型")).toHaveValue("restore");
  await submit(page);
  await expect(page.locator(".result-counts")).toHaveText(/成功 2.*失败 0/);
  await closeResult(page);
  for (const doc of docs) {
    const result = (await api(page, "/documents/" + doc.document_id)).data;
    expect(result.folder_id).toBeTruthy();
    expect(result.tag_ids).toHaveLength(2);
    expect(result.deleted_at).toBeNull();
    expect(
      (await api(page, "/documents/" + doc.document_id + "/revisions")).data[0]
        .binary_available,
    ).toBe(true);
  }
  await page.getByRole("button", { name: "全部档案", exact: true }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await page
    .getByRole("region", { name: "档案列表", exact: true })
    .getByRole("button")
    .filter({ hasText: "项目合同.txt" })
    .click();
  await page.getByRole("button", { name: "整理操作", exact: true }).click();
  await page.getByLabel("操作类型").selectOption("set_triage");
  await submit(page);
  await expect(page.locator(".result-counts")).toHaveText(/成功 1.*失败 0/);
  await page.screenshot({
    path: "/tmp/juanzhan-t27-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await closeResult(page);
  expect(errors).toEqual([]);
});

test("internal drag moves logical references; OS file drop uploads once and foreign payload is ignored", async ({
  page,
}) => {
  await login(page);
  await createSpace(page, "拖动流程-" + randomUUID().slice(0, 5));
  await createFolder(page, "拖动目标");
  await createTag(page, "拖动标签");
  const [doc] = await seed(page, ["内部档案.txt"]);
  let row = page
    .getByRole("region", { name: "档案列表", exact: true })
    .getByRole("button")
    .filter({ hasText: "内部档案.txt" });
  await row.dragTo(
    page
      .getByRole("navigation")
      .getByRole("button", { name: "拖动目标", exact: true }),
  );
  await expect(page.getByRole("dialog", { name: "档案操作" })).toBeVisible();
  await expect(
    page.getByLabel("目标目录").locator("option:checked"),
  ).toHaveText("拖动目标");
  await submit(page);
  await expect(page.locator(".result-counts")).toHaveText(/成功 1/);
  await closeResult(page);
  expect(
    (await api(page, "/documents/" + doc.document_id)).data.triage_status,
  ).toBe("needs_review");
  row = page
    .getByRole("region", { name: "档案列表", exact: true })
    .getByRole("button")
    .filter({ hasText: "内部档案.txt" });
  await row.dragTo(
    page.getByRole("button", { name: "标签 拖动标签", exact: true }),
  );
  await expect(page.getByLabel("操作类型")).toHaveValue("add_tags");
  await submit(page);
  await expect(page.locator(".result-counts")).toHaveText(/成功 1/);
  await closeResult(page);
  const target = page
    .getByRole("navigation")
    .getByRole("button", { name: "拖动目标", exact: true });
  const transfer = await page.evaluateHandle(() => {
    const data = new DataTransfer();
    data.items.add(
      new File(["OS original"], "系统拖入.txt", { type: "text/plain" }),
    );
    return data;
  });
  await target.dispatchEvent("dragenter", { dataTransfer: transfer });
  await target.dispatchEvent("dragover", { dataTransfer: transfer });
  await target.dispatchEvent("drop", { dataTransfer: transfer });
  await expect(
    page.getByLabel("上传队列").getByText("原件已保存", { exact: false }),
  ).toBeVisible();
  await page.getByRole("button", { name: "收起上传队列" }).click();
  const space = await page.getByLabel("当前空间").inputValue();
  const all = (await api(page, "/documents?space_id=" + space)).data.items;
  expect(all).toHaveLength(2);
  expect(all.find((d) => d.title === "系统拖入.txt").folder_id).toBe(
    (await api(page, "/documents/" + doc.document_id)).data.folder_id,
  );
  const spoof = await page.evaluateHandle(() => {
    const data = new DataTransfer();
    data.setData("application/x-juanzhan-documents", "foreign-token");
    return data;
  });
  await target.dispatchEvent("drop", { dataTransfer: spoof });
  await expect(page.getByRole("dialog")).not.toBeVisible();
  expect((await api(page, "/documents?space_id=" + space)).data.total).toBe(2);
});

test("whole-result selection crosses pages but never includes a later upload", async ({
  page,
}) => {
  await login(page);
  await createSpace(page, "跨页快照-" + randomUUID().slice(0, 5));
  await seed(
    page,
    Array.from(
      { length: 31 },
      (_, i) => "快照-" + String(i).padStart(2, "0") + ".txt",
    ),
  );
  await page.getByRole("button", { name: "收件箱", exact: true }).click();
  await page.getByRole("button", { name: "选择筛选结果", exact: true }).click();
  await expect(page.getByRole("region", { name: "已选档案" })).toContainText(
    "已选 31 份",
  );
  await page.getByRole("button", { name: "批量操作", exact: true }).click();
  await page.getByLabel("操作类型").selectOption("set_triage");
  const [later] = await seed(page, ["稍后导入.txt"], false);
  await submit(page);
  await expect(page.locator(".result-counts")).toHaveText(/成功 31.*失败 0/);
  await closeResult(page);
  await expect(
    page
      .getByRole("region", { name: "档案列表", exact: true })
      .getByText("1 份", { exact: true }),
  ).toBeVisible();
  expect(
    (await api(page, "/documents/" + later.document_id)).data.triage_status,
  ).toBe("needs_review");
});

test("oversized result selection is rejected explicitly rather than silently truncated", async ({
  page,
}) => {
  await login(page);
  await createSpace(page, "范围上限-" + randomUUID().slice(0, 5));
  await seed(
    page,
    Array.from(
      { length: 101 },
      (_, i) => "范围-" + String(i).padStart(3, "0") + ".txt",
    ),
  );
  await page.getByRole("button", { name: "选择筛选结果", exact: true }).click();
  await expect(
    page.getByText("当前筛选结果超过100份，请缩小筛选范围或按当前页操作。", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "已选档案" }),
  ).not.toBeVisible();
});
