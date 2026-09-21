"""Normative Chinese copy DATA, not markup or a rendered client."""
from typing import Final

from .negotiation_consent import MODE_CONSEQUENCES, SCOPE_CONSEQUENCES, Contract

COPY: Final = {
    "ingest_prompt": "这批图片希望怎样整理？分析后会再次请你确认，不会自动移动原文件。",
    "coherent_clusters": "发现 {count} 个视觉较一致的分组，共 {images} 张图片。分组不等于同一角色，请先确认名称或拆分。",
    "measured_evidence": "测量依据：{method}；样本 {sample}/{population}；证据覆盖 {coverage}；置信说明：{confidence}。",
    "purity_missing": "没有独立人工标签，无法确认身份纯度；以下仅为视觉一致性或弱标签符合率。",
    "inheritance_warning": "继承目录只是弱先验，不代表角色已核实；会标记为“继承”，可整批撤销。",
    "auto_warning": "自动优先只建立满足门禁的虚拟映射；模型高分不等于身份正确，无参考建议仍需核实。",
    "model_tier": "模型建议（未核实）",
    "reference_tier": "已核实建议仅表示通过参考/记忆门禁，不表示人工确认或准确率认证。",
    "conflict": "模型建议与参考或人工证据冲突，已降级为待审，不会自动归入该角色。",
    "confirmation": "将新增或修改 {changed} 张图片的虚拟映射，{review} 张待审，{none} 张保留未解决；原文件不变。",
    "commit_action": "确认并建立虚拟映射",
    "dismiss": "暂不决定",
    "undo": "撤销本批映射",
    "g2_boundary": "本阶段仅记录同意，不建立虚拟映射；首轮执行尚未实现。",
}


class Choice(Contract):
    id: str
    label: str
    consequences: tuple[str, ...]
    available: bool = True


class Presentation(Contract):
    locale: str = "zh-CN"
    templates: dict[str, str] = COPY
    text: dict[str, str]
    modes: tuple[Choice, ...] = tuple(Choice(id=k, label=label, consequences=MODE_CONSEQUENCES[k])
        for k, label in (("human-first", "人审优先"), ("auto-first", "自动优先"), ("inherit-only", "仅继承目录")))
    scopes: tuple[Choice, ...] = tuple(Choice(id=k, label=label, consequences=SCOPE_CONSEQUENCES[k])
        for k, label in (("all", "全继承"), ("selected", "逐目录勾选"), ("none", "不继承")))
    default_mode: str = "human-first"
    default_scope: str = "none"
    affirmative_required: bool = True
    mapping_action_available: bool = False
    folder_text: dict[str, str]


def initial_prompt() -> Presentation:
    """Defaults are only intent, and never a post-analysis affirmative receipt."""
    return Presentation(text={"ingest_prompt": COPY["ingest_prompt"], "g2_boundary": COPY["g2_boundary"]},
                        folder_text={})
