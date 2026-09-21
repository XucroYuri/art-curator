// Browser drafts only. The CLI owns authoritative staging, freshness and confirmation.
const clusterTypes = ["work", "artist", "original-series", "character", "ordinary-person", "undetermined"];
function parseClusterPayload(data) {
  const hash = /^[0-9a-f]{64}$/;
  if (data?.schema_version !== "gallery-clusters-v1" || !Array.isArray(data.clusters)
      || data.manifest?.schema_version !== "album-member-manifest-v1" || !Array.isArray(data.manifest.members)
      || !data.subjects || !data.assets || !Array.isArray(data.entities)) throw new Error("冻结簇数据不可用");
  for (const value of [data.profile, data.manifest_digest, data.corpus_fingerprint, data.parent?.root_digest])
    if (!hash.test(value)) throw new Error("缺少完整摘要绑定");
  if (!data.parent.library_id || !Number.isInteger(data.parent.revision)) throw new Error("相册父版本不可用");
  const members = new Map();
  for (const member of data.manifest.members) {
    if (!member.legacy_id || !member.subject_id || members.has(member.legacy_id)
        || ![member.image_id, member.crop_id, member.profile].every((v) => hash.test(v))) throw new Error("成员绑定缺失或重复");
    const subject = data.subjects[member.legacy_id];
    if (!subject || !Array.isArray(subject.relations) || typeof subject.disposition !== "string") throw new Error("缺少成员状态；不能预览冲突");
    members.set(member.legacy_id, member);
  }
  const ids = new Set();
  for (const cluster of data.clusters) {
    const snapshot = cluster.snapshot;
    if (!snapshot || !hash.test(snapshot.snapshot_id) || ids.has(snapshot.snapshot_id)
        || !Array.isArray(snapshot.parents) || !snapshot.members?.length || !Array.isArray(cluster.wall?.representatives)) throw new Error("冻结父簇或代表墙不可用");
    ids.add(snapshot.snapshot_id);
    const selected = new Set();
    for (const member of snapshot.members) {
      const bound = members.get(member.legacy_id);
      if (!bound || selected.has(member.legacy_id) || ["image_id", "subject_id", "crop_id", "profile"].some((key) => member[key] !== bound[key])) throw new Error("簇与 manifest 不一致");
      selected.add(member.legacy_id);
    }
    if (cluster.wall.representatives.some((id) => !selected.has(id))) throw new Error("代表图不在冻结簇中");
  }
  for (const entity of data.entities)
    if (!entity.entity_id || !entity.name || !clusterTypes.includes(entity.entity_type)) throw new Error("类型实体不可用");
  return data;
}
function clusterDraft(data, choice) {
  const cluster = data.clusters.find((c) => c.snapshot.snapshot_id === choice.cluster);
  if (!cluster) throw new Error("请选择冻结簇");
  const members = cluster.snapshot.members;
  const ids = new Set(members.map((m) => m.legacy_id));
  if (choice.selected.some((id) => !ids.has(id))) throw new Error("选择不在冻结簇内");
  const parents = [cluster.snapshot];
  const command = {action: choice.action, cluster_id: cluster.snapshot.snapshot_id, parent_clusters: parents};
  let affected = choice.selected;
  let conflicts = [];
  switch (choice.action) {
    case "name":
    case "promote":
      if (!choice.selected.length || !choice.entity?.name.trim() || !clusterTypes.includes(choice.entity.entity_type)) throw new Error("请选择成员并填写类型名称");
      command.entity_id = choice.entity.entity_id; command.face_ids = choice.selected;
      if (choice.action === "promote") {
        const proposal = data.discovery?.clusters.find((c) => c.cluster_id === choice.cluster);
        const count = new Set(members.filter((m) => choice.selected.includes(m.legacy_id)).map((m) => m.image_id)).size;
        const gate = data.discovery?.pool.inputs.minimum_seed_images ?? 10;
        if (!proposal?.seed_eligible || count < gate || data.discovery.pool.reembedding_required.length) throw new Error(`晋升需要至少 ${gate} 张不同图片；当前 ${count} 张。较小集合仍可手动命名。`);
      }
      break;
    case "split": {
      const parts = choice.partitions.filter((p) => p.length);
      const flat = parts.flat();
      if (!parts.length || new Set(flat).size !== flat.length || flat.length >= ids.size || flat.some((id) => !ids.has(id))) throw new Error("拆分需要非空、不重叠分区，并保留非空余集");
      command.partitions = parts; affected = [...ids]; break;
    }
    case "outlier":
    case "exclusion":
      if (!choice.selected.length || choice.selected.length >= ids.size) throw new Error("视觉排除需要非空选择与非空余集");
      command.face_ids = choice.selected; affected = [...ids]; break;
    case "merge": {
      parents.push(...data.clusters.filter((c) => choice.merge.includes(c.snapshot.snapshot_id) && c !== cluster).map((c) => c.snapshot));
      const all = parents.flatMap((p) => p.members);
      if (parents.length < 2 || new Set(all.map((m) => `${m.image_id}:${m.subject_id}`)).size !== all.length) throw new Error("合并需要至少两个互不重叠的冻结簇");
      affected = all.map((m) => m.legacy_id);
      conflicts = [...new Set(affected.flatMap((id) => data.subjects[id].relations.filter((r) => r.disposition === "assigned").map((r) => `${r.entity_type}:${r.entity_id}`)))];
      if (conflicts.length < 2) conflicts = [];
      command.conflict_resolution = choice.defer ? "defer" : "reject";
      break;
    }
    default: throw new Error("操作不可用");
  }
  return {command, affected, conflicts, blocked: conflicts.length > 0 && !choice.defer};
}
async function clusterEnvelope(data, choice) {
  const draft = clusterDraft(data, choice);
  if (draft.blocked) throw new Error("存在已接受实体冲突；请明确选择 defer，不能多数覆盖");
  if (!choice.actor.trim()) throw new Error("操作者 ID 不能为空");
  if (choice.action === "promote") return {filename: "cluster-promotion.json", wire: {
    discovery: data.discovery, actor: choice.actor.trim(), cluster_id: choice.cluster,
    entity: choice.entity, selected_members: choice.selected,
  }, journal: null};
  const journal = JSON.stringify({clusterDecisions: [draft.command], faceLabels: {}}, null, 2);
  const bytes = new TextEncoder().encode(journal);
  const hex = (values) => [...values].map((v) => v.toString(16).padStart(2, "0")).join("");
  const digest = hex(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)));
  return {filename: "cluster-envelope.json", journal, wire: {
    schema_version: "album-mapping-decisions-v1", source: "review-studio",
    corpus_fingerprint: data.corpus_fingerprint, parent: data.parent, export_id: crypto.randomUUID(),
    actor: choice.actor.trim(), profile: data.profile, manifest_digest: data.manifest_digest,
    original_journal: {kind: "browser-journal", logical_id: digest, schema_version: "opaque-v1", payload_hex: hex(bytes), digest, length: bytes.length},
    entities: choice.action === "name" ? [choice.entity] : [], operations: [],
  }};
}
