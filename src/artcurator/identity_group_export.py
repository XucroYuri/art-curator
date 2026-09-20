"""Frozen many-to-many exports and Chinese evidence report."""
import csv
import io
from pathlib import Path

import numpy as np

from .identity_group_schema import AnchorDocument, Decision, GroupDocument
from .identity_schema import Face, Record
from .identity_store import atomic_bytes, save_model


class FaceExport(Record):
    face: Face
    filename: str
    decision: Decision

    @property
    def role(self) -> str:
        if self.decision.character is not None:
            return self.decision.character
        return f"新人物{self.face.cluster_id:02d}" if self.face.cluster_id is not None else "未知人物"


class ExportRows(Record):
    faces: list[FaceExport]
    filenames: dict[str, str]


def export(out: Path, document: GroupDocument, rows: ExportRows) -> None:
    save_model(out / "character-groups.json", document)
    by_image: dict[str, set[str]] = {sha: set() for sha in rows.filenames}
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(("character", "sha16", "filename", "face_id", "sim", "margin", "decision"))
    for row in rows.faces:
        decision = row.decision
        by_image[row.face.image_sha16].add(row.role)
        writer.writerow((row.role, row.face.image_sha16, row.filename, row.face.face_id, decision.sim,
                         decision.margin, "assigned" if decision.character is not None else "abstained"))
    atomic_bytes(out / "character-groups-by-character.csv", buffer.getvalue().encode("utf-8"))
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(("sha16", "filename", "characters"))
    for sha in sorted(rows.filenames):
        writer.writerow((sha, rows.filenames[sha], "|".join(sorted(by_image[sha]))))
    atomic_bytes(out / "character-groups-by-image.csv", buffer.getvalue().encode("utf-8"))


def report(out: Path, document: GroupDocument, anchors: AnchorDocument) -> None:
    p = document.provenance
    lines = ["# 角色参考分组报告", "", "本结果为实验性视觉检索建议，不是身份认证或准确率证明。",
             f"图片 {p.images}；人脸 {p.faces}；放弃命名 {document.abstained.face_count} "
             f"({document.abstained.face_count / max(p.faces, 1):.2%})。",
             f"无已知角色图片 {p.unassigned_images}；含放弃人脸图片 {p.any_abstained_images}；"
             f"无脸图片 {p.zero_face_images}；多已知角色图片 {p.multi_character_images}。", "",
             "| 角色 | 图片 | 人脸 | 平均相似度 | 最小间隔 |", "|---|---:|---:|---:|---:|"]
    for row in document.characters:
        lines.append(f"| {row.character} | {row.image_count} | {row.face_count} | {row.mean_sim} | {row.min_margin} |")
    lines += ["", "## 阈值依据", f"本次 min_sim={document.thresholds.min_sim:.8f}；"
              f"min_margin={document.thresholds.min_margin:.8f}。",
              "默认值仅从参考集留一裁剪分布生成：错误角色质心相似度 P95；正稳定间隔 P10 与 0.005 取大。",
              "显式配置可覆盖默认值；查询集不参与阈值选择。间隔取质心间隔与单锚点竞争间隔的较小值。",
              f"参考样本数 {anchors.calibration.samples}；推荐默认值 {anchors.calibration.defaults.model_dump()}。"]
    for name, values in (("同角色余弦", anchors.calibration.genuine),
                         ("最强错误角色余弦", anchors.calibration.impostor),
                         ("稳定间隔", anchors.calibration.stable_margin)):
        if values:
            lines.append(f"{name} [P05,P10,P50,P90,P95]：{np.quantile(values, [.05,.1,.5,.9,.95]).tolist()}")
    lines += ["", "## 来源、许可证与成本", "角色目录名是用户提供的人工标签；待分组图的路径和文件名不进入决策。",
              f"有效来源计数：{p.source_counts}；人工参考版本 {p.reference_version}。",
              f"模型 {p.model.model}@{p.model.revision}；预处理 {p.preprocess}。",
              f"执行配置：{p.execution.model_dump_json()}。", f"来源与许可：{p.licenses}。",
              f"锚点构建 {anchors.wall_seconds:.3f} 秒；分组决策 {p.wall_seconds:.3f} 秒。"
              "命令总耗时（含导出）见 identity-timings.jsonl。", "",
              "## 局限", "文件夹标签可能错误；风格、头发、背景仍影响裁剪向量；同源近重复会影响留一分布。",
              "没有独立人工标注的困难负例，不能报告精确率/召回率，也不能把候选恢复量当作误杀数。",
              "小脸、侧脸或遮挡可能漏检；无脸不是角色不存在。精确同裁剪参考已排除，近重复未完全排除。",
              "数值证书不等于角色语义认证；图片权利未核实，不分发私人锚点。原图、既有评分与路由未修改。"]
    atomic_bytes(out / "identity-groups-report.md", ("\n".join(lines) + "\n").encode("utf-8"))
