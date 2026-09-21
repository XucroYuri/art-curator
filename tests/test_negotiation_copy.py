"""FR-ALBUM-NEGOTIATE-004 copy contract: normative Chinese strings are data, bound values exact."""
from pathlib import Path

import pytest
from test_ingest import corpus as corpus
from test_negotiation_consent import prepared

from artcurator.config import Settings
from artcurator.negotiation_copy import COPY, initial_prompt
from artcurator.negotiation_report import NegotiationReport, report_digest

REQUIRED = {
    "ingest_prompt": "这批图片希望怎样整理？分析后会再次请你确认，不会自动移动原文件。",
    "coherent_clusters": "发现 {count} 个视觉较一致的分组，共 {images} 张图片。"
                         "分组不等于同一角色，请先确认名称或拆分。",
    "measured_evidence": "测量依据：{method}；样本 {sample}/{population}；"
                         "证据覆盖 {coverage}；置信说明：{confidence}。",
    "purity_missing": "没有独立人工标签，无法确认身份纯度；以下仅为视觉一致性或弱标签符合率。",
    "inheritance_warning": "继承目录只是弱先验，不代表角色已核实；会标记为“继承”，可整批撤销。",
    "auto_warning": "自动优先只建立满足门禁的虚拟映射；模型高分不等于身份正确，无参考建议仍需核实。",
    "model_tier": "模型建议（未核实）",
    "reference_tier": "已核实建议仅表示通过参考/记忆门禁，不表示人工确认或准确率认证。",
    "conflict": "模型建议与参考或人工证据冲突，已降级为待审，不会自动归入该角色。",
    "confirmation": "将新增或修改 {changed} 张图片的虚拟映射，{review} 张待审，"
                    "{none} 张保留未解决；原文件不变。",
    "commit_action": "确认并建立虚拟映射",
    "dismiss": "暂不决定",
    "undo": "撤销本批映射",
}


def test_copy_when_compared_to_the_spec_table_is_exact() -> None:
    # Given / When / Then: the spec literals are the contract, not prose.
    assert {key: COPY[key] for key in REQUIRED} == REQUIRED


def test_choices_when_rendered_bind_required_labels_and_defaults() -> None:
    # Given
    prompt = initial_prompt()
    # When / Then
    assert [(choice.id, choice.label) for choice in prompt.modes] == [
        ("human-first", "人审优先"), ("auto-first", "自动优先"), ("inherit-only", "仅继承目录")]
    assert [(choice.id, choice.label) for choice in prompt.scopes] == [
        ("all", "全继承"), ("selected", "逐目录勾选"), ("none", "不继承")]
    assert prompt.default_mode == "human-first" and prompt.default_scope == "none"
    # Consent is never pre-checked or pre-authorized by a default.
    assert prompt.affirmative_required is True and prompt.mapping_action_available is False


def test_choice_consequences_when_rendered_carry_the_spec_tokens() -> None:
    # Given
    prompt = initial_prompt()
    modes = {choice.id: choice for choice in prompt.modes}
    scopes = {choice.id: choice for choice in prompt.scopes}
    # When / Then
    assert "no-reference-free-WD-identity-assignment" in modes["auto-first"].consequences
    assert "audit-5%-review-none-lanes" in modes["auto-first"].consequences
    assert "later-recognition-requires-new-consent" in modes["inherit-only"].consequences
    assert "exclude-future-files" in scopes["selected"].consequences
    assert "zero-context-assisted-grouping" in scopes["none"].consequences


def test_report_text_when_rendered_has_no_unresolved_placeholders(corpus: Settings) -> None:
    # Given: the nominal measured report over the synthetic corpus.
    _, report = prepared(corpus)
    text = report.presentation.text
    # Then: every applicable literal is present or bound, and unavailable counts render 未知.
    assert set(text) == set(COPY) - {"measured_evidence"}
    assert "{" not in text["coherent_clusters"] and "{" not in text["confirmation"]
    assert text["confirmation"].count("未知") == 3
    for folder_text in report.presentation.folder_text.values():
        assert "{" not in folder_text and "测量依据：" in folder_text
    assert report.presentation.locale == "zh-CN"
    assert report.presentation.default_mode == "human-first"
    assert report.presentation.default_scope == "none"


def test_report_when_measured_copy_stays_bound_to_the_report_numbers(corpus: Settings) -> None:
    # Given
    _, report = prepared(corpus)
    # When
    cluster_text = report.presentation.text["coherent_clusters"]
    # Then: counts come from the measured report, not a template default.
    assert str(report.recommendations.eligible_clusters) in cluster_text
    for folder in report.folders:
        rendered = report.presentation.folder_text[folder.folder_id]
        assert f"{folder.coherence.method}" in rendered
        assert f"{folder.sample}/{folder.population}" in rendered


@pytest.fixture(scope="module")
def example_report() -> NegotiationReport:
    path = Path(__file__).parent / "fixtures/negotiation-report.example.json"
    return NegotiationReport.model_validate_json(path.read_bytes())


def test_example_fixture_when_validated_is_self_consistent(example_report: NegotiationReport) -> None:
    # Given / When / Then
    assert example_report.schema_version == "album-negotiation-v1"
    assert example_report.report_digest == report_digest(example_report)
    assert example_report.labels_digest
    assert example_report.presentation.text["ingest_prompt"] == REQUIRED["ingest_prompt"]
    assert all("{" not in value for value in example_report.presentation.text.values())
