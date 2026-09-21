// Reuses the studio's safe DOM, card and download primitives; no companion calls.
function installClusters() {
  const tab = negNode("button", "簇命名", "mode-button"); tab.id = "clusters-mode"; tab.type = "button";
  tab.setAttribute("role", "tab"); tab.setAttribute("aria-selected", "false"); tab.setAttribute("aria-controls", "clusters-view");
  document.querySelector(".mode-switch").append(tab);
  const view = negNode("section", undefined, "negotiation-view"); view.id = "clusters-view"; view.hidden = true;
  view.setAttribute("role", "tabpanel"); view.setAttribute("aria-labelledby", tab.id); els("main-region").append(view);
  tab.addEventListener("click", () => setMode("clusters"));
  view.append(negNode("p", "G3 / 冻结成员 · 仅导出", "neg-kicker"), negNode("h2", "先看成员，再决定名字"),
    negNode("p", "仅明确选中的成员参与批量映射。同图其他主体、未选成员及未来成员不会获得隐含指派。代表墙不是全体身份的证明。", "neg-status"));
  let data;
  try { data = parseClusterPayload(columnar.cl); }
  catch (error) { view.append(negNode("p", `簇操作不可用：${error.message}。请由本地工具提供 cluster-payload.json 后重新生成工作台。`, "neg-warning")); return; }
  const layout = negNode("div", undefined, "neg-layout"); const wall = negNode("div", undefined, "cluster-wall");
  const form = negNode("form", undefined, "neg-card cluster-fields"); form.addEventListener("submit", (e) => e.preventDefault());
  layout.append(wall, form); view.append(layout);
  const field = (id, title, options) => {
    const label = negNode("label", title); const control = negNode(options ? "select" : "input"); control.id = id;
    if (options) for (const [value, text] of options) { const option = negNode("option", text); option.value = value; control.append(option); }
    label.append(control); form.append(label); return control;
  };
  const clusterSelect = field("cl-cluster", "01 / 选择冻结簇", data.clusters.map((c) => [c.snapshot.snapshot_id, c.label]));
  const action = field("cl-action", "02 / 操作", [["name", "批量命名"], ["split", "拆分（分区 + 余集）"], ["merge", "视觉合并（不合并实体）"],
    ["outlier", "离群成员"], ["exclusion", "视觉成员排除"], ["promote", "未知池晋升"]]);
  const existing = field("cl-existing", "已有实体或新建", [["", "新建类型实体"], ...data.entities.map((e, i) => [e.entity_id, `${i + 1} / ${e.entity_type}`])]);
  const entityText = negNode("p"); entityText.id = "cl-entity-text"; form.append(entityText); existing.setAttribute("aria-describedby", entityText.id);
  const type = field("cl-type", "类型命名空间", clusterTypes.map((t) => [t, t]));
  const name = field("cl-name", "新实体名称（允许中文长标签）");
  const actor = field("cl-actor", "本地操作者 ID"); actor.value = "local:review-studio";
  const memberBox = negNode("fieldset"); const mergeBox = negNode("fieldset"); form.append(memberBox, mergeBox);
  const deferLabel = negNode("label", undefined, "neg-option"); const defer = negNode("input"); defer.type = "checkbox"; defer.id = "cl-defer";
  deferLabel.append(defer, negNode("span", "明确选择 defer：保留所有已接受关系，将合并范围主体标为待查证，不做多数覆盖。")); form.append(deferLabel);
  const semantics = negNode("p", "离群 / 排除仅是视觉成员操作，不是身份拒绝、不是参考删除、不是源文件删除。", "neg-warning"); form.append(semantics);
  const gate = negNode("p", "", "neg-status"); gate.id = "cl-gate"; gate.setAttribute("role", "status"); form.append(gate);
  const previewButton = negNode("button", "预览所选操作", "neg-export"); previewButton.type = "button"; previewButton.id = "cl-preview-button"; form.append(previewButton);
  const preview = negNode("section", undefined, "neg-card"); preview.id = "cl-preview"; preview.tabIndex = -1; preview.setAttribute("aria-label", "批次草稿预览"); form.append(preview);
  const ackLabel = negNode("label", undefined, "neg-option"); const ack = negNode("input"); ack.type = "checkbox"; ack.id = "cl-ack";
  ackLabel.append(ack, negNode("span", "我已核对冻结成员及后果，明确确认导出此草稿；尚未提交或应用映射。")); form.append(ackLabel);
  const exportButton = negNode("button", "确认并导出操作 envelope", "neg-export"); exportButton.type = "button"; exportButton.id = "cl-export"; exportButton.disabled = true; form.append(exportButton);
  const status = negNode("p", "尚无已应用的批次；预览和下载都不会写入相册。", "neg-status"); status.id = "cl-status"; status.setAttribute("role", "status"); form.append(status);
  const files = negNode("div", undefined, "neg-actions"); form.append(files);
  const manifestButton = negNode("button", "下载冻结 manifest"); manifestButton.type = "button"; manifestButton.id = "cl-manifest";
  manifestButton.onclick = () => download("cluster-manifest.json", JSON.stringify(data.manifest, null, 2), "application/json"); files.append(manifestButton);
  const journalButton = negNode("button", "下载原始 journal 字节"); journalButton.type = "button"; journalButton.disabled = true; files.append(journalButton);
  const cli = negNode("pre", "", "neg-json"); form.append(cli);
  const unavailable = negNode("section", undefined, "neg-card"); unavailable.id = "cl-unavailable";
  unavailable.append(negNode("h3", "能力边界 · 不可用"), negNode("p", "本离线页不执行相册写入、批次撤销或重嵌入。实体合并、身份/参考拒绝级联未受此导出合同支持。"));
  for (const text of ["在浏览器应用映射", "在浏览器撤销已提交批次", "实体合并", "删除参考支持", "重新生成嵌入"]) {
    const button = negNode("button", `${text} · 不可用`); button.type = "button"; button.disabled = true; button.setAttribute("aria-describedby", "cl-unavailable"); unavailable.append(button);
  }
  form.append(unavailable);
  let prepared = null; let generation = 0; let entityId = crypto.randomUUID();
  const current = () => data.clusters.find((c) => c.snapshot.snapshot_id === clusterSelect.value);
  function choice() {
    return {cluster: clusterSelect.value, action: action.value, actor: actor.value,
      selected: [...memberBox.querySelectorAll('input:checked')].map((c) => c.value),
      partitions: ["a", "b"].map((group) => [...memberBox.querySelectorAll("select")].filter((s) => s.value === group).map((s) => s.dataset.member)),
      merge: [...mergeBox.querySelectorAll('input:checked')].map((c) => c.value), defer: defer.checked,
      entity: data.entities.find((e) => e.entity_id === existing.value) || {entity_id: entityId, entity_type: type.value, name: name.value.trim()}};
  }
  function invalidate() {
    generation++; prepared = null; ack.checked = false; exportButton.disabled = true; journalButton.disabled = true; preview.replaceChildren();
    status.textContent = "选择已更新 · 必须重新预览和确认导出；未应用映射。";
  }
  function update() {
    const naming = ["name", "promote"].includes(action.value);
    for (const control of [existing, type, name]) control.parentElement.hidden = !naming;
    name.parentElement.hidden = !naming || Boolean(existing.value);
    type.disabled = name.disabled = Boolean(existing.value);
    const entity = data.entities.find((e) => e.entity_id === existing.value);
    if (entity) { type.value = entity.entity_type; name.value = entity.name; }
    entityText.hidden = !naming || !entity;
    entityText.textContent = entity ? `${entity.entity_type} · ${entity.name} · ${entity.entity_id}` : "";
    memberBox.hidden = action.value === "merge"; mergeBox.hidden = deferLabel.hidden = action.value !== "merge";
    memberBox.querySelectorAll("select").forEach((s) => { s.parentElement.hidden = action.value !== "split"; });
    memberBox.querySelectorAll("input").forEach((c) => { c.disabled = action.value === "split"; });
    const chosen = choice(); const count = new Set(current()?.snapshot.members.filter((m) => chosen.selected.includes(m.legacy_id)).map((m) => m.image_id)).size;
    const minimum = data.discovery?.pool.inputs.minimum_seed_images ?? 10;
    gate.textContent = `已选 ${chosen.selected.length} 个成员 / ${count} 张不同图片。晋升门槛 ≥${minimum} 张：${count >= minimum ? "数量达标（不代表身份正确）" : "未达标"}；较小集合与噪声仍可手动命名。`;
    previewButton.disabled = !current() || action.value === "promote" && (!data.discovery || count < minimum);
    cli.textContent = action.value === "promote"
      ? "album-map --album-db <db> --album-op promote --album-file cluster-promotion.json\n→ 保存 StagedImport → 审阅 → confirm --album-authorize <staged fingerprint>"
      : "album-map --album-db <db> --album-op stage --album-file cluster-envelope.json --album-manifest cluster-manifest.json\n→ 保存 StagedImport → 审阅 → confirm --album-file <staged.json> --album-authorize <staged fingerprint>";
  }
  function renderCluster() {
    invalidate(); memberBox.replaceChildren(negNode("legend", "03 / 检查全部冻结成员（不默认全选）")); mergeBox.replaceChildren(negNode("legend", "选择其他冻结父簇")); wall.replaceChildren();
    const cluster = current(); if (!cluster) { update(); return; }
    const card = negNode("section", undefined, "neg-card"); card.append(negNode("h3", cluster.label), negNode("p", `${cluster.snapshot.members.length} 个冻结成员 · 后端代表墙`, "neg-kicker"));
    const strip = negNode("div", undefined, "neg-thumbs");
    for (const id of cluster.wall.representatives) {
      const figure = negNode("figure"); const source = data.assets[id];
      if (typeof source === "string" && /^data:image\/(png|jpeg|webp);base64,/.test(source)) {
        const image = negNode("img"); image.src = source; image.alt = `代表成员 ${id}`; image.width = image.height = 120;
        image.onerror = () => image.replaceWith(negNode("span", "本地代表图不可用")); figure.append(image);
      } else figure.append(negNode("span", "代表图不可用 · 未嵌入本地资源"));
      figure.append(negNode("figcaption", id)); strip.append(figure);
    }
    card.append(strip, negDetails("完整父簇 / 谱系 / 全哈希绑定", cluster.snapshot)); wall.append(card);
    for (const member of cluster.snapshot.members) {
      const subject = data.subjects[member.legacy_id]; const row = negNode("div", undefined, "neg-option"); const label = negNode("label");
      const check = negNode("input"); check.type = "checkbox"; check.value = member.legacy_id; check.dataset.member = member.legacy_id;
      label.append(check, negNode("span", member.legacy_id)); row.append(label);
      row.append(negNode("p", `${subject.disposition === "deferred" ? "待查证 · deferred" : subject.disposition} · ${subject.notes || "无备注"}`, subject.disposition === "deferred" ? "cl-deferred" : ""));
      row.append(negDetails("成员图像 / 接受关系", {image_id: member.image_id, subject_id: member.subject_id, relations: subject.relations}));
      const partitionLabel = negNode("label", `${member.legacy_id} 分区`); const partition = negNode("select"); partition.dataset.member = member.legacy_id;
      for (const [value, text] of [["", "保留在自动余集"], ["a", "分区 A"], ["b", "分区 B"]]) { const option = negNode("option", text); option.value = value; partition.append(option); }
      partitionLabel.append(partition); row.append(partitionLabel); memberBox.append(row);
    }
    memberBox.className = "cluster-members";
    for (const other of data.clusters.filter((c) => c !== cluster)) {
      const label = negNode("label", undefined, "neg-option"); const check = negNode("input"); check.type = "checkbox"; check.value = other.snapshot.snapshot_id;
      label.append(check, negNode("span", `${other.label} · ${other.snapshot.members.length} 成员`)); mergeBox.append(label);
    }
    const pool = data.pool || data.discovery?.pool;
    const poolCard = negNode("section", undefined, "neg-card"); poolCard.id = "cl-pool"; poolCard.append(negNode("h3", "冻结未知池 / 兼容性与成本"));
    if (pool) poolCard.append(negEvidence({member_digest: pool.member_digest, frozen_members: pool.members.map((m) => m.legacy_id),
      profile: pool.inputs.profile, parameters_changed: pool.parameters_changed, reembedding_required: pool.reembedding_required,
      pair_comparison_upper_bound: pool.pair_comparison_upper_bound}), negNode("p", "成本仅为算术比较上界，不是实测时间或重嵌入报价；不自动执行重嵌入。", "neg-warning"),
      negDetails("参数、缺失向量、谱系与噪声", {options: pool.inputs.options, unresolved_without_vectors: pool.unresolved_without_vectors,
        prior_memberships: pool.prior_memberships, additions: data.discovery?.additions, splits: data.discovery?.splits, merges: data.discovery?.merges, noise: data.discovery?.noise}));
    else poolCard.append(negNode("p", "未知池与晋升不可用 · 未提供后端 Discovery 输出。", "neg-warning"));
    wall.append(poolCard); update();
  }
  form.addEventListener("input", (event) => {
    if (event.target === ack) { exportButton.disabled = !prepared || !ack.checked; return; }
    invalidate(); update();
  });
  clusterSelect.addEventListener("change", renderCluster);
  existing.addEventListener("change", () => { if (!existing.value) { entityId = crypto.randomUUID(); name.value = ""; } update(); });
  previewButton.addEventListener("click", async () => {
    invalidate(); const version = generation; const selected = choice();
    try {
      const draft = clusterDraft(data, selected);
      preview.append(negNode("h3", "批次草稿预览 · 尚未 stage"), negNode("p", `影响 ${draft.affected.length} 个主体：${draft.affected.join("、")}`));
      if (draft.conflicts.length) preview.append(negNode("p", `已接受实体冲突：${draft.conflicts.join("、")}`, "neg-warning"),
        negNode("p", selected.defer ? "拟待查证 · deferred（尚未应用）：所有合并主体延后判断，全部已接受关系保留。" : "合并被阻止；请明确勾选 defer 后重新预览。", "cl-deferred"));
      if (draft.blocked) { preview.focus(); return; }
      preview.append(negNode("p", ["name", "promote"].includes(selected.action)
        ? `${selected.entity.entity_type} · ${selected.entity.name}：仅在 CLI 显式 confirm 提交后，所选关系 source=human、verified=true；当前未核实、未应用。`
        : "仅改变视觉成员关系；现有身份关系保留。拆分包含自动非空余集。"), negDetails("精确命令与冻结父簇", draft.command));
      const result = await clusterEnvelope(data, selected); if (version !== generation) return;
      prepared = result; status.textContent = "草稿已预览 · 请核对后明确确认导出。CLI 仍须 stage / confirm，且会重新检查父版本与绑定。";
      preview.focus();
    } catch (error) { status.textContent = `不能导出：${error.message}`; }
  });
  exportButton.addEventListener("click", () => {
    if (!prepared || !ack.checked) return;
    download(prepared.filename, JSON.stringify(prepared.wire, null, 2), "application/json");
    journalButton.disabled = !prepared.journal;
    journalButton.onclick = () => { if (prepared?.journal) download("cluster-journal.json", prepared.journal, "application/json"); };
    status.textContent = "已导出 · 未应用、未提交。保留原始文件，检查 CLI staging；只有匹配的执行回执代表已应用。";
    ack.checked = false; exportButton.disabled = true;
  });
  view.addEventListener("keydown", (event) => { if (event.key === "Escape") { invalidate(); status.textContent = "已取消本次预览；不代表提交，也不撤回已下载的草稿。"; } });
  renderCluster();
}
installClusters();
