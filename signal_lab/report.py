from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from .definitions import DefinitionCatalog
from .joint import (
    CAVEAT_TEXTS,
    JointObservation,
    build_joint_observation,
    digest_joints,
    joint_payload,
)
from .records import SurveyStatus


@dataclass(frozen=True)
class AnalysisReport:
    report_id: str
    title: str
    period_start: str
    period_end: str
    source_ids: tuple[str, ...]
    measures: dict[str, float]
    created_at: str


def create_report(report_id, title, period_start, period_end, source_ids, measures):
    return AnalysisReport(
        report_id=report_id, title=title, period_start=period_start, period_end=period_end,
        source_ids=tuple(sorted(set(source_ids))), measures=dict(measures),
        created_at=datetime.now(timezone.utc).isoformat(),
    )


@dataclass(frozen=True)
class ReproductionResult:
    """旧报告按当时输入与选择重新构造后的比对结果。"""

    matches: bool
    expected_digest: str
    rebuilt_digest: str
    mismatched_joint_ids: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class JointAnalysisReport:
    """联合观察报告：固定口径、缺口与输入摘要，可按当时选择复现。

    报告不复制原始问卷全文，而是固定每个问题/主题定义的版本号；复现时
    从 :class:`~signal_lab.definitions.DefinitionCatalog` 取回同一版本，
    定义目录只增不改，因此旧报告始终可复现。
    """

    report_id: str
    title: str
    period_start: tuple[int, int]
    period_end: tuple[int, int]
    # 每个问题在本报告中出现过的全部版本（跨月口径切换时会有多个）
    question_versions: dict[str, tuple[int, ...]]
    topic_versions: dict[str, int]
    population_ids: tuple[str, ...]
    joints: tuple[JointObservation, ...]
    input_digest: str
    created_at: str

    def supports_association(self) -> bool:
        return False

    def missing_overview(self) -> dict[str, list[str]]:
        """汇总两个集合分别缺了什么，供读者直接查看。"""
        overview = {"survey": [], "media": []}
        for joint in self.joints:
            for gap in joint.gaps:
                overview.setdefault(gap.side, []).append(
                    f"{joint.joint_id}: {gap.code} — {gap.detail}"
                )
        return overview


def create_joint_report(report_id, title, period_start, period_end, joints):
    """根据联合观察生成报告；所有口径版本从观察记录中固定下来。"""
    question_versions: dict[str, set[int]] = {}
    topic_versions: dict[str, int] = {}
    population: set[str] = set()
    for joint in joints:
        question_versions.setdefault(joint.question_id, set()).add(
            joint.question_version
        )
        topic_versions[joint.topic] = max(
            topic_versions.get(joint.topic, 0),
            joint.topic_version,
        )
        population.add(joint.population_id)
    return JointAnalysisReport(
        report_id=report_id,
        title=title,
        period_start=tuple(period_start),
        period_end=tuple(period_end),
        question_versions={
            key: tuple(sorted(values))
            for key, values in question_versions.items()
        },
        topic_versions=topic_versions,
        population_ids=tuple(sorted(population)),
        joints=tuple(joints),
        input_digest=digest_joints(joints),
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def reproduce_joint_report(
    report: JointAnalysisReport,
    catalog: DefinitionCatalog,
    survey_rows,
    media_rows,
) -> ReproductionResult:
    """按报告固定的版本与选择，用给定输入重新构造联合观察并比对摘要。

    复现步骤：
    1. 校验报告固定的问题/主题版本在目录中仍然存在（定义只增不改）；
    2. 按报告中每条联合观察的周期、人群、媒体范围重新构造；
    3. 比对规范化输入摘要，报告任何不一致的观察 id。
    """
    rebuilt: list[JointObservation] = []
    for joint in report.joints:
        question = catalog.get_question(
            joint.question_id, joint.question_version
        )
        topic_def = catalog.get_topic(joint.topic, joint.topic_version)
        if not question.active_on(date(joint.period[0], joint.period[1], 1)):
            raise LookupError(
                f"pinned question {joint.question_id} "
                f"v{joint.question_version} was not active in {joint.period}"
            )
        rebuilt.append(build_joint_observation(
            joint.joint_id,
            joint.period,
            question,
            joint.population_id,
            topic_def,
            survey_rows,
            media_rows,
            joint.media_scope,
            joint.region,
        ))

    rebuilt_digest = digest_joints(rebuilt)
    expected = {joint.joint_id: joint_payload(joint) for joint in report.joints}
    actual = {joint.joint_id: joint_payload(joint) for joint in rebuilt}
    mismatched = tuple(
        joint_id
        for joint_id in sorted(set(expected) | set(actual))
        if expected.get(joint_id) != actual.get(joint_id)
    )
    return ReproductionResult(
        matches=rebuilt_digest == report.input_digest and not mismatched,
        expected_digest=report.input_digest,
        rebuilt_digest=rebuilt_digest,
        mismatched_joint_ids=mismatched,
    )


def render_joint_report(report: JointAnalysisReport) -> str:
    """生成面向读者的文字报告，明确口径、缺口与并列趋势限制。"""
    lines = [
        f"# {report.title}（{report.report_id}）",
        f"周期：{report.period_start[0]}-{report.period_start[1]:02d} 至 "
        f"{report.period_end[0]}-{report.period_end[1]:02d}",
        "",
        "## 固定口径",
        f"- 调查问题版本：{report.question_versions}",
        f"- 主题定义版本：{report.topic_versions}",
        f"- 目标人群：{', '.join(report.population_ids)}",
        "- 结论口径：并列趋势（两侧样本相互独立，不支持关联或因果）",
        "",
        "## 各月联合观察",
    ]
    for joint in report.joints:
        lines.append(
            f"- {joint.joint_id} {joint.period[0]}-{joint.period[1]:02d} "
            f"主题 {joint.topic}（{joint.region}）"
        )
        lines.append(
            f"  - 调查：问题 {joint.question_id} v{joint.question_version} / "
            f"人群 {joint.population_id} / 状态 {joint.survey_status.value} / "
            f"有效回答 {joint.survey_valid_responses} / 值 {joint.survey_value}"
        )
        lines.append(
            f"  - 媒体：来源 {list(joint.media_scope.source_ids)} / "
            f"覆盖来源数 {joint.media_source_count} / 报道量 {joint.media_value}"
        )
        if joint.gaps:
            for gap in joint.gaps:
                lines.append(f"  - 缺口（{gap.side}）：{gap.detail}")
        for code in joint.caveats:
            lines.append(f"  - 提示：{CAVEAT_TEXTS[code]}")
        if joint.survey_status is SurveyStatus.NO_VALID_RESPONSES:
            lines.append("  - 守卫：无有效回答记为缺失，未记为零关注。")
    lines.extend(["", "## 缺口总览"])
    overview = report.missing_overview()
    for side in ("survey", "media"):
        entries = overview.get(side) or []
        label = "调查侧" if side == "survey" else "媒体侧"
        if entries:
            lines.append(f"- {label}：")
            lines.extend(f"  - {entry}" for entry in entries)
        else:
            lines.append(f"- {label}：本周期无缺口")
    lines.append("")
    lines.append(
        "说明：媒体报道数量反映报道覆盖，不是公众意见的替代值；"
        "时间相近不代表同一群体的态度变化。"
    )
    return "\n".join(lines)
