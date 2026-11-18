"""调查与媒体的联合观察。

两类材料不是同一种样本：调查有自己的受访人群、问法和有效回答范围，
媒体观察受来源覆盖和报道时间影响。本模块把它们按月份并列放在一次
:class:`JointObservation` 中，并强制记录：

* 选用的调查问题版本与目标人群（含有效回答分母）；
* 媒体来源范围（来源 id 集合、地区、语言）；
* 两个集合各自缺了什么（:class:`SeriesGap`）；
* 结论只能是 *并列趋势*，并固定附带说明，不能支持关联或因果解释。

没有有效回答的群体不能记成零关注；媒体报道数量不能被当作公众意见的
替代值，也不允许填入调查数值位。
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from enum import Enum

from .definitions import DefinitionCatalog, SurveyQuestion, TopicDefinition
from .records import Observation, SurveyObservation, SurveyStatus


# 固定的读者提示，编码稳定，文案随项目统一维护。
CAVEAT_TEXTS = {
    "survey_missing": "调查侧为缺失：该群体本周期没有有效回答，缺失不等于零关注。",
    "survey_no_record": "调查侧为缺失：该周期没有这个人群的调查记录，不能推断为零关注。",
    "media_missing": "媒体侧为缺失：所选范围与周期内没有任何媒体观察记录，零与缺失无法区分。",
    "media_no_coverage": "媒体侧在范围内未观察到该主题的报道；报道数量受来源覆盖限制。",
    "parallel_only": "两侧仅为时间上并列的趋势，样本相互独立，不支持关联或因果结论。",
    "media_not_opinion": "媒体值是报道数量，反映报道覆盖，不是公众意见或其替代值。",
}


@dataclass(frozen=True)
class MediaScope:
    """一次联合观察所采用的媒体来源范围。"""

    source_ids: tuple[str, ...]
    region: str | None = None
    language: str | None = None

    def __post_init__(self):
        object.__setattr__(self, "source_ids", tuple(sorted(set(self.source_ids))))

    def contains(self, source_id: str) -> bool:
        return source_id in self.source_ids


@dataclass(frozen=True)
class SeriesGap:
    """某一侧集合缺失数据的说明。"""

    side: str  # "survey" 或 "media"
    code: str  # 机器可读的缺口编码
    detail: str


class Interpretation(Enum):
    """联合观察允许的结论口径。"""

    PARALLEL_TREND = "parallel_trend"


@dataclass(frozen=True)
class JointObservation:
    """一个月份上调查与媒体的一次并列观察。"""

    joint_id: str
    topic: str
    topic_version: int
    period: tuple[int, int]
    region: str

    # 调查口径（问题版本 + 人群），固定下来供复核
    question_id: str
    question_version: int
    population_id: str
    survey_value: float | None
    survey_valid_responses: int | None
    survey_status: SurveyStatus

    # 媒体口径与值（报道数量，非公众意见）
    media_scope: MediaScope
    media_value: float | None
    media_source_count: int

    gaps: tuple[SeriesGap, ...] = field(default_factory=tuple)
    interpretation: Interpretation = Interpretation.PARALLEL_TREND
    caveats: tuple[str, ...] = field(default_factory=tuple)

    def supports_association(self) -> bool:
        """联合观察永远不支持关联/因果结论。"""
        return False

    def has_survey_value(self) -> bool:
        return self.survey_value is not None

    def has_media_value(self) -> bool:
        return self.media_value is not None


def _in_period(day: date, period: tuple[int, int]) -> bool:
    return (day.year, day.month) == period


def _aggregate_media(
    media_rows,
    topic: str,
    period: tuple[int, int],
    scope: MediaScope,
):
    total = 0.0
    sources: set[str] = set()
    in_scope_observations = 0
    for row in media_rows:
        if not isinstance(row, Observation) or isinstance(row, SurveyObservation):
            raise TypeError(
                "media_rows must contain Observation records; "
                "survey records cannot be substituted for media counts"
            )
        if not _in_period(row.observed_on, period):
            continue
        if not scope.contains(row.source_id):
            continue
        if scope.region is not None and row.region != scope.region:
            continue
        in_scope_observations += 1
        if row.topic != topic:
            continue
        total += row.value
        sources.add(row.source_id)
    return total, sources, in_scope_observations


def build_joint_observation(
    joint_id: str,
    period: tuple[int, int],
    question: SurveyQuestion,
    population_id: str,
    topic_def: TopicDefinition,
    survey_rows,
    media_rows,
    media_scope: MediaScope,
    region: str = "global",
) -> JointObservation:
    """按固定口径构造一次联合观察。

    参数中的 ``question`` 与 ``topic_def`` 应由
    :class:`~signal_lab.definitions.DefinitionCatalog` 按分析周期解析，
    使旧报告可以按当时固定的版本重建。
    """
    if question.topic != topic_def.topic:
        raise ValueError(
            f"question topic {question.topic!r} does not match "
            f"topic definition {topic_def.topic!r}"
        )
    if population_id not in question.population_ids:
        raise ValueError(
            f"population {population_id!r} is not covered by question "
            f"{question.question_id} v{question.version}"
        )

    gaps: list[SeriesGap] = []
    caveats = ["parallel_only", "media_not_opinion"]

    # --- 调查侧：同一问题版本、同一人群、当月至多一条有效记录 ---
    matches = [
        row
        for row in survey_rows
        if isinstance(row, SurveyObservation)
        and _in_period(row.observed_on, period)
        and row.question_id == question.question_id
        and row.question_version == question.version
        and row.population_id == population_id
        and row.topic == topic_def.topic
        and row.region == region
    ]
    wrong_type = [
        row for row in survey_rows if isinstance(row, Observation)
        and not isinstance(row, SurveyObservation)
    ]
    if wrong_type:
        raise TypeError(
            "survey_rows must contain SurveyObservation records; "
            "media counts are not a substitute for public opinion"
        )
    if len(matches) > 1:
        raise ValueError(
            "multiple survey records for the same question/population/period"
        )

    if not matches:
        survey_value = None
        survey_denominator = None
        survey_status = SurveyStatus.NO_RECORD
        gaps.append(SeriesGap(
            "survey", "no_record",
            f"{period[0]}-{period[1]:02d} 没有人群 {population_id} 对问题 "
            f"{question.question_id} 的调查记录",
        ))
        caveats.append("survey_no_record")
    else:
        record = matches[0]
        survey_status = record.status
        survey_denominator = record.valid_responses
        if record.status is SurveyStatus.NO_VALID_RESPONSES:
            survey_value = None
            gaps.append(SeriesGap(
                "survey", "no_valid_responses",
                f"人群 {population_id} 本周期有效回答数为 0，记为缺失而非零关注",
            ))
            caveats.append("survey_missing")
        else:
            survey_value = record.value

    # --- 媒体侧：只在来源范围内汇总报道数量 ---
    media_value, media_sources, in_scope_count = _aggregate_media(
        media_rows, topic_def.topic, period, media_scope
    )
    if in_scope_count == 0:
        media_value = None
        gaps.append(SeriesGap(
            "media", "no_observation",
            "所选来源范围与周期内没有任何媒体观察记录",
        ))
        caveats.append("media_missing")
    elif not media_sources:
        # 范围内有观察但没有该主题：零与缺失无法从报道计数中区分
        media_value = None
        gaps.append(SeriesGap(
            "media", "no_coverage",
            "范围内有媒体观察但未覆盖该主题，零报道与缺失无法区分",
        ))
        caveats.append("media_no_coverage")

    return JointObservation(
        joint_id=joint_id,
        topic=topic_def.topic,
        topic_version=topic_def.version,
        period=period,
        region=region,
        question_id=question.question_id,
        question_version=question.version,
        population_id=population_id,
        survey_value=survey_value,
        survey_valid_responses=survey_denominator,
        survey_status=survey_status,
        media_scope=media_scope,
        media_value=media_value,
        media_source_count=len(media_sources),
        gaps=tuple(gaps),
        caveats=tuple(caveats),
    )


def plan_joint_observations(
    periods,
    question_id: str,
    population_id: str,
    topic: str,
    catalog: DefinitionCatalog,
    survey_rows,
    media_rows,
    media_scope: MediaScope,
    region: str = "global",
):
    """为多个月份批量构造联合观察。

    每个周期按当月生效的问题/主题版本取口径；问卷或主题定义更新后，
    新周期自动采用新版本，已生成的报告不受影响。
    """
    joints = []
    for index, period in enumerate(periods, start=1):
        anchor = date(period[0], period[1], 1)
        question = catalog.question_version_on(question_id, anchor)
        topic_def = catalog.topic_version_on(topic, anchor)
        joints.append(build_joint_observation(
            f"joint-{period[0]}-{period[1]:02d}-{index}",
            period, question, population_id, topic_def,
            survey_rows, media_rows, media_scope, region,
        ))
    return joints


def joint_payload(joint: JointObservation) -> dict:
    """联合观察的规范化 JSON 表示（用于输入摘要与复现比对）。"""
    return {
        "joint_id": joint.joint_id,
        "topic": joint.topic,
        "topic_version": joint.topic_version,
        "period": list(joint.period),
        "region": joint.region,
        "question_id": joint.question_id,
        "question_version": joint.question_version,
        "population_id": joint.population_id,
        "survey_value": joint.survey_value,
        "survey_valid_responses": joint.survey_valid_responses,
        "survey_status": joint.survey_status.value,
        "media_scope": {
            "source_ids": list(joint.media_scope.source_ids),
            "region": joint.media_scope.region,
            "language": joint.media_scope.language,
        },
        "media_value": joint.media_value,
        "media_source_count": joint.media_source_count,
        "gaps": [
            {"side": gap.side, "code": gap.code, "detail": gap.detail}
            for gap in joint.gaps
        ],
        "interpretation": joint.interpretation.value,
        "caveats": list(joint.caveats),
    }


def digest_joints(joints) -> str:
    payload = [joint_payload(joint) for joint in joints]
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
