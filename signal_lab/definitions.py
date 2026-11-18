"""版本化的调查问题、人群与主题定义。

问卷或主题定义更新后，新分析采用新口径；旧定义只增不改、保留在目录中，
旧的 :class:`~signal_lab.report.AnalysisReport` 仍可按当时固定的版本复现。
"""

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class Population:
    """调查的目标人群（样本框），不同人群之间不能互相代表。"""

    population_id: str
    label: str
    description: str = ""


@dataclass(frozen=True)
class SurveyQuestion:
    """问卷中一个问题的某个版本。

    ``question_id`` 相同、``version`` 不同表示同一问题的口径更新。
    每个版本记录自己的问法、回答范围与生效日期；版本一经登记不可修改。
    """

    question_id: str
    version: int
    topic: str
    label: str
    wording: str
    response_scale: str
    valid_from: date
    valid_to: date | None = None
    population_ids: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self):
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("valid_to cannot precede valid_from")

    def active_on(self, day: date) -> bool:
        if day < self.valid_from:
            return False
        return self.valid_to is None or day <= self.valid_to


@dataclass(frozen=True)
class TopicDefinition:
    """媒体观察中某个主题编码的某个版本。

    主题口径更新（例如重新划分报道归类规则）时登记新版本，
    历史 :class:`~signal_lab.records.Observation` 仍属于其当时的版本。
    """

    topic: str
    version: int
    label: str
    coding_rules: str
    valid_from: date
    valid_to: date | None = None

    def __post_init__(self):
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("valid_to cannot precede valid_from")

    def active_on(self, day: date) -> bool:
        if day < self.valid_from:
            return False
        return self.valid_to is None or day <= self.valid_to


class DefinitionCatalog:
    """保存全部历史版本的定义目录（只增不改）。"""

    def __init__(
        self,
        questions: tuple[SurveyQuestion, ...] = (),
        populations: tuple[Population, ...] = (),
        topics: tuple[TopicDefinition, ...] = (),
    ):
        self._questions: dict[tuple[str, int], SurveyQuestion] = {}
        self._question_ids: dict[str, list[SurveyQuestion]] = {}
        for question in questions:
            self.add_question(question)
        self._populations = {p.population_id: p for p in populations}
        self._topics: dict[tuple[str, int], TopicDefinition] = {}
        self._topic_codes: dict[str, list[TopicDefinition]] = {}
        for topic in topics:
            self.add_topic(topic)

    def add_question(self, question: SurveyQuestion) -> None:
        key = (question.question_id, question.version)
        if key in self._questions:
            raise KeyError(f"question version already registered: {key}")
        self._questions[key] = question
        self._question_ids.setdefault(question.question_id, []).append(question)

    def add_population(self, population: Population) -> None:
        if population.population_id in self._populations:
            raise KeyError(
                f"population already registered: {population.population_id}"
            )
        self._populations[population.population_id] = population

    def add_topic(self, topic: TopicDefinition) -> None:
        key = (topic.topic, topic.version)
        if key in self._topics:
            raise KeyError(f"topic version already registered: {key}")
        self._topics[key] = topic
        self._topic_codes.setdefault(topic.topic, []).append(topic)

    def get_question(self, question_id: str, version: int) -> SurveyQuestion:
        return self._questions[(question_id, version)]

    def get_population(self, population_id: str) -> Population:
        return self._populations[population_id]

    def get_topic(self, topic: str, version: int) -> TopicDefinition:
        return self._topics[(topic, version)]

    def question_version_on(self, question_id: str, day: date) -> SurveyQuestion:
        """返回该问题在指定日期生效的版本；同日多个版本生效时取最新。"""
        candidates = [
            q
            for q in self._question_ids.get(question_id, ())
            if q.active_on(day)
        ]
        if not candidates:
            raise LookupError(
                f"no active version for question {question_id} on {day}"
            )
        return max(candidates, key=lambda q: q.version)

    def topic_version_on(self, topic: str, day: date) -> TopicDefinition:
        """返回该主题在指定日期生效的版本；同日多个版本生效时取最新。"""
        candidates = [
            t for t in self._topic_codes.get(topic, ()) if t.active_on(day)
        ]
        if not candidates:
            raise LookupError(f"no active version for topic {topic} on {day}")
        return max(candidates, key=lambda t: t.version)
