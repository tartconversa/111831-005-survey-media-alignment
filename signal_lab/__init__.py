"""面向研究复核的数据观察与分析。"""

from .analysis import compare_periods
from .definitions import DefinitionCatalog, Population, SurveyQuestion, TopicDefinition
from .joint import (
    CAVEAT_TEXTS,
    Interpretation,
    JointObservation,
    MediaScope,
    SeriesGap,
    build_joint_observation,
    digest_joints,
    plan_joint_observations,
)
from .records import Observation, Source, SurveyObservation, SurveyStatus
from .report import (
    AnalysisReport,
    JointAnalysisReport,
    ReproductionResult,
    create_joint_report,
    create_report,
    render_joint_report,
    reproduce_joint_report,
)

__all__ = [
    "Observation",
    "Source",
    "SurveyObservation",
    "SurveyStatus",
    "SurveyQuestion",
    "Population",
    "TopicDefinition",
    "DefinitionCatalog",
    "MediaScope",
    "SeriesGap",
    "Interpretation",
    "JointObservation",
    "build_joint_observation",
    "plan_joint_observations",
    "digest_joints",
    "CAVEAT_TEXTS",
    "AnalysisReport",
    "JointAnalysisReport",
    "ReproductionResult",
    "create_report",
    "create_joint_report",
    "reproduce_joint_report",
    "render_joint_report",
    "compare_periods",
]
