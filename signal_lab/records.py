from dataclasses import dataclass
from datetime import date
from enum import Enum


@dataclass(frozen=True)
class Source:
    source_id: str
    region: str
    language: str
    active: bool = True


@dataclass(frozen=True)
class Observation:
    """媒体报道观察。

    ``value`` 是该来源在 ``observed_on`` 当天关于某主题的报道数量，
    反映报道覆盖情况，不是公众意见，也不能作为公众意见的替代值。
    """

    observation_id: str
    source_id: str
    observed_on: date
    topic: str
    value: float
    region: str = "global"


class SurveyStatus(Enum):
    """调查记录的有效回答状态。"""

    # 有有效回答，可以计算比例/均值
    VALID = "valid"
    # 该群体本周期接受了调查但没有任何有效回答：只能记缺失，不能记零
    NO_VALID_RESPONSES = "no_valid_responses"
    # 仅用于联合观察层面：该周期根本没有这个人群的调查记录
    NO_RECORD = "no_record"


@dataclass(frozen=True)
class SurveyObservation:
    """一次调查访问中，某人群对某问题的观察结果。

    调查与媒体是两套独立样本：调查有自己的问题口径、目标人群和有效回答
    分母（``valid_responses``）。没有有效回答的群体必须以
    :data:`SurveyStatus.NO_VALID_RESPONSES` 加 ``value=None`` 表示缺失，
    不允许写成 0（零关注）。
    """

    observation_id: str
    question_id: str
    question_version: int
    population_id: str
    observed_on: date
    topic: str
    valid_responses: int
    value: float | None = None
    status: SurveyStatus = SurveyStatus.VALID
    region: str = "global"

    def __post_init__(self):
        if self.valid_responses < 0:
            raise ValueError("valid_responses cannot be negative")
        if self.status is SurveyStatus.NO_VALID_RESPONSES:
            if self.valid_responses != 0:
                raise ValueError(
                    "NO_VALID_RESPONSES requires valid_responses == 0"
                )
            if self.value is not None:
                raise ValueError(
                    "a group without valid responses is missing, never zero: "
                    "value must be None"
                )
        elif self.status is SurveyStatus.VALID:
            if self.value is None:
                raise ValueError("a valid survey observation requires a value")
            if self.valid_responses == 0:
                raise ValueError(
                    "zero valid responses cannot be recorded as a zero value; "
                    "use NO_VALID_RESPONSES with value=None"
                )
        else:
            raise ValueError(
                "NO_RECORD is only valid at the joint-observation level, "
                "not on a stored survey record"
            )
