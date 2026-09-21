// Frozen report renderer. Never derive eligibility, confidence, copy or digests.
function negNode(tag, text, className = "") {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = String(text);
  node.className = className;
  return node;
}
function negList(values) {
  const list = negNode("ul");
  values.forEach((value) => list.append(negNode("li", value)));
  return list;
}
function negValue(value) {
  return value === null || value === undefined ? "未知 · 报告未提供可用证据" : String(value);
}
function negEvidence(data) {
  const list = negNode("dl", undefined, "neg-evidence");
  for (const [key, value] of Object.entries(data)) {
    const row = negNode("div");
    const description = negNode("dd");
    if (value !== null && typeof value === "object") {
      if (Array.isArray(value)) {
        if (!value.length) description.textContent = "无记录（不等于零置信度）";
        else value.forEach((item) => description.append(item !== null && typeof item === "object"
          ? negEvidence(item) : negNode("span", `${negValue(item)} `)));
      } else description.append(negEvidence(value));
    } else description.textContent = negValue(value);
    row.append(negNode("dt", key), description); list.append(row);
  }
  return list;
}
function negDetails(title, data) {
  const details = negNode("details", undefined, "neg-details");
  details.append(negNode("summary", title), negEvidence(data));
  return details;
}
function negFraction(title, fraction) {
  const box = negNode("div", undefined, "neg-metric");
  box.append(negNode("strong", title));
  if (!fraction) { box.append(negNode("p", "未知 · 报告没有此项测量")); return box; }
  const available = fraction.method !== "unavailable" && fraction.value !== null;
  box.append(negNode("p", available
    ? `${fraction.numerator}/${fraction.denominator} · ${(fraction.value * 100).toFixed(1)}%`
    : `未知 · method: ${fraction.method} · 分母 ${negValue(fraction.denominator)}`));
  box.append(negNode("p", `${fraction.method} · ${fraction.limits}`));
  if (fraction.interval) box.append(negNode("p", `区间：${fraction.interval.join(" – ")} · ${fraction.method}`));
  else box.append(negNode("p", fraction.method === "census-exact"
    ? "全量描述性比例；不是模型正确率区间。" : "总体区间不可用；不推断身份准确率。"));
  return box;
}
function renderNegotiationReport(report, assets) {
  const root = negNode("div", undefined, "neg-report");
  const copy = report.presentation.text;
  const summary = negNode("section", undefined, "neg-card");
  summary.append(negNode("p", "01 / 冻结测量", "neg-kicker"), negNode("h3", "先看证据，再选工作方式"));
  const counts = negNode("div", undefined, "neg-counts");
  for (const [key, label] of [["files", "文件"], ["unique_images", "独立图片"], ["faces", "人脸"]]) {
    const cell = negNode("div");
    cell.append(negNode("span", label), negNode("strong", negValue(report.global_evidence[key]))); counts.append(cell);
  }
  summary.append(counts, negNode("p", report.global_evidence.scope));
  summary.append(negNode("p", `不可用信号：${report.global_evidence.unavailable_signals.join(" · ") || "无记录"}`, "neg-warning"));
  summary.append(negDetails("全局分母、模型版本与成本", report.global_evidence));
  summary.append(negDetails("快照绑定与人工标签", {
    report_digest: report.report_digest, snapshot_digest: report.snapshot_digest,
    analysis_profile_digest: report.analysis_profile_digest, seal_digest: report.seal_digest,
    profile_digest: report.profile_digest, labels_digest: report.labels_digest, labels: report.labels,
  }));
  const g1 = report.g1_report_ref;
  if (typeof g1 === "string" && !/[:\\]/.test(g1) && !g1.startsWith("/") && !g1.split("/").includes("..")) {
    const link = negNode("a", "打开封存 G1 分析报告（本地文件）"); link.href = g1; summary.append(link);
  } else summary.append(negNode("p", "G1 链接不可用 · 非本地相对路径"));
  root.append(summary);
  const wall = negNode("section", undefined, "neg-card");
  wall.append(negNode("h3", "视觉一致分组"), negNode("p", copy.coherent_clusters), negNode("p", copy.reference_tier));
  const clusterCard = (cluster) => {
    const card = negNode("article", undefined, "neg-cluster");
    card.append(negNode("h4", `分组 ${cluster.cluster_id} · ${negValue(cluster.unique_images)} 图 / ${negValue(cluster.faces)} 人脸`));
    const strip = negNode("div", undefined, "neg-thumbs");
    for (const rep of cluster.representatives) {
      const source = assets[rep.crop_ref] || assets[rep.image_ref];
      const figure = negNode("figure");
      if (typeof source === "string" && /^data:image\/(png|jpeg|webp);base64,/.test(source)) {
        const image = negNode("img"); image.src = source; image.alt = `代表图 ${rep.image_id}`;
        image.width = 120; image.height = 120; image.loading = "lazy";
        image.addEventListener("error", () => image.replaceWith(negNode("span", "缩略图不可用")), {once: true});
        figure.append(image);
      } else figure.append(negNode("span", "缩略图不可用 · 未嵌入本地资源"));
      figure.append(negNode("figcaption", rep.face_id || rep.image_id)); strip.append(figure);
    }
    card.append(strip, negNode("p", copy.model_tier, "neg-warning"));
    if (cluster.candidates.length) card.append(negEvidence({candidates: cluster.candidates}));
    else card.append(negNode("p", "模型候选不可用 · 报告无候选证据"));
    const contested = cluster.candidates.some((c) => c.model_demoted || c.disagreements?.length || c.conflict);
    if (contested) card.append(negNode("p", copy.conflict, "neg-warning"));
    const {representatives, candidates, ...metrics} = cluster;
    card.append(negDetails("成员、来源、参考支持与一致性限制", metrics));
    return card;
  };
  report.clusters.filter((c) => report.eligible_cluster_ids.includes(c.cluster_id)).forEach((c) => wall.append(clusterCard(c)));
  if (!report.eligible_cluster_ids.length) wall.append(negNode("p", "没有通过冻结门槛的分组；不是同一角色的否定结论。"));
  const remaining = negNode("details", undefined, "neg-details"); remaining.id = "neg-remaining-clusters";
  remaining.append(negNode("summary", `其余分组 (${report.remaining_cluster_ids.length})`));
  report.clusters.filter((c) => !report.eligible_cluster_ids.includes(c.cluster_id)).forEach((c) => remaining.append(clusterCard(c)));
  wall.append(remaining, negDetails("推荐阈值（不替你选择）", report.recommendations)); root.append(wall);
  const folders = negNode("section", undefined, "neg-card");
  folders.append(negNode("p", "02 / 目录证据", "neg-kicker"), negNode("h3", "测量不是使用授权"),
    negNode("p", "同意本身不授权使用目录上下文；context_enabled = false。未测量目录仍可人工整理为集合。"));
  for (const folder of report.folders) {
    const card = negNode("article", undefined, "neg-folder");
    card.append(negNode("h4", folder.path), negNode("p", report.presentation.folder_text[folder.folder_id]));
    if (folder.conflict_C?.value > 0) card.append(negNode("p", copy.conflict, "neg-warning"));
    if (folder.purity.method === "unavailable") card.append(negNode("p", copy.purity_missing, "neg-warning"));
    card.append(negFraction(`身份纯度 · ${negValue(folder.purity_identity)}`, folder.purity));
    card.append(negNode("p", `独立人工标签 ${folder.independent_labels} · 未解决 ${folder.unresolved_labels}（保留在分母中）`));
    card.append(negNode("p", `视觉一致性 median ${negValue(folder.coherence.median)} · p10 ${negValue(folder.coherence.p10)}`));
    card.append(negNode("p", `${folder.coherence.method} · ${folder.coherence.limits}`));
    card.append(negNode("p", folder.thresholds, "neg-mono"));
    const regimes = negNode("details", undefined, "neg-details");
    regimes.append(negNode("summary", `四种目录假设 · ${folder.regimes.status} · ${folder.regimes.passing.join(" / ") || "无通过项"}`),
      negNode("p", `${folder.regimes.profile} · ${folder.regimes.limits} · confidence: ${negValue(folder.regimes.confidence)}`));
    for (const detector of folder.regimes.detectors) {
      const block = negNode("div", undefined, "neg-detector");
      block.append(negNode("h4", `${detector.regime} · ${detector.status}`));
      detector.gates.forEach((gate) => block.append(negNode("p",
        `${gate.feature}: ${negValue(gate.value)} · 门槛 ${gate.operator} ${gate.threshold} · ${gate.passed === null ? "未知（证据缺失）" : gate.passed ? "通过" : "未通过"}`, "neg-mono")));
      block.append(negNode("p", detector.consequence)); regimes.append(block);
    }
    const {regimes: ignored, ...evidence} = folder;
    card.append(regimes, negDetails("抽样身份、弱符合率、缺失项与全部限制", evidence)); folders.append(card);
  }
  root.append(folders); return root;
}
