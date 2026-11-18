import unittest
from datetime import date

from signal_lab.definitions import (
    DefinitionCatalog,
    Population,
    SurveyQuestion,
    TopicDefinition,
)
from signal_lab.joint import MediaScope, plan_joint_observations
from signal_lab.records import Observation, SurveyObservation, SurveyStatus
from signal_lab.report import (
    create_joint_report,
    render_joint_report,
    reproduce_joint_report,
)


def build_catalog():
    return DefinitionCatalog(
        questions=(
            SurveyQuestion(
                question_id="q-concern", version=1,
                topic="international-cooperation",
                label="最关心的议题", wording="未来一年您最关心的议题是？",
                response_scale="多选，选填三项",
                valid_from=date(2026, 1, 1), valid_to=date(2026, 11, 30),
                population_ids=("adults-cn",),
            ),
            SurveyQuestion(
                question_id="q-concern", version=2,
                topic="international-cooperation",
                label="最关心的议题（量表版）",
                wording="请对下列议题的关心程度打分（1-5）",
                response_scale="1-5 李克特量表",
                valid_from=date(2026, 12, 1),
                population_ids=("adults-cn",),
            ),
        ),
        populations=(Population("adults-cn", "中国成年居民"),),
        topics=(
            TopicDefinition(
                topic="international-cooperation", version=1,
                label="国际合作", coding_rules="外交/国际组织/双边合作",
                valid_from=date(2026, 1, 1),
            ),
        ),
    )


def build_inputs():
    survey = [
        SurveyObservation(
            "s-1", "q-concern", 1, "adults-cn",
            date(2026, 11, 1), "international-cooperation",
            valid_responses=800, value=0.42,
        ),
        SurveyObservation(
            "s-2", "q-concern", 2, "adults-cn",
            date(2026, 12, 1), "international-cooperation",
            valid_responses=0, value=None,
            status=SurveyStatus.NO_VALID_RESPONSES,
        ),
    ]
    media = [
        Observation("o-1", "global-desk", date(2026, 11, 2),
                    "international-cooperation", 4),
        Observation("o-2", "regional-review", date(2026, 12, 3),
                    "international-cooperation", 2),
    ]
    scope = MediaScope(("global-desk", "regional-review"))
    return survey, media, scope


class JointReportTests(unittest.TestCase):
    def setUp(self):
        self.catalog = build_catalog()
        self.survey, self.media, self.scope = build_inputs()
        self.joints = plan_joint_observations(
            [(2026, 11), (2026, 12)], "q-concern", "adults-cn",
            "international-cooperation", self.catalog,
            self.survey, self.media, self.scope,
        )
        self.report = create_joint_report(
            "r-1", "调查与媒体议题对照", (2026, 11), (2026, 12), self.joints
        )

    def test_report_pins_versions_and_population(self):
        self.assertEqual(
            self.report.question_versions, {"q-concern": (1, 2)}
        )
        # 问题版本按观察逐条固定：11 月仍是 v1
        self.assertEqual(
            [j.question_version for j in self.report.joints], [1, 2]
        )
        self.assertEqual(
            self.report.topic_versions, {"international-cooperation": 1}
        )
        self.assertEqual(self.report.population_ids, ("adults-cn",))
        self.assertFalse(self.report.supports_association())

    def test_report_reproduces_with_same_inputs(self):
        result = reproduce_joint_report(
            self.report, self.catalog, self.survey, self.media
        )
        self.assertTrue(result.matches)
        self.assertEqual(result.expected_digest, result.rebuilt_digest)
        self.assertEqual(result.mismatched_joint_ids, ())

    def test_report_flags_changed_media_input(self):
        altered_media = self.media + [
            Observation("o-3", "global-desk", date(2026, 11, 20),
                        "international-cooperation", 10),
        ]
        result = reproduce_joint_report(
            self.report, self.catalog, self.survey, altered_media
        )
        self.assertFalse(result.matches)
        self.assertIn(
            "joint-2026-11-1", result.mismatched_joint_ids
        )

    def test_report_flags_changed_survey_input(self):
        altered_survey = [
            row for row in self.survey if row.observation_id != "s-1"
        ]
        result = reproduce_joint_report(
            self.report, self.catalog, altered_survey, self.media
        )
        self.assertFalse(result.matches)

    def test_missing_overview_separates_the_two_collections(self):
        overview = self.report.missing_overview()
        self.assertTrue(
            any("no_valid_responses" in entry for entry in overview["survey"])
        )
        self.assertEqual(overview["media"], [])

    def test_rendered_report_states_caveats_and_guardrails(self):
        text = render_joint_report(self.report)
        self.assertIn("并列趋势", text)
        self.assertIn("不支持关联或因果", text)
        self.assertIn("不是公众意见的替代值", text)
        self.assertIn("无有效回答记为缺失，未记为零关注", text)
        self.assertIn("q-concern", text)
        self.assertIn("adults-cn", text)
        self.assertIn("global-desk", text)
        self.assertIn("缺口总览", text)

    def test_old_report_still_reproduces_after_new_definition_added(self):
        # 模拟后续登记新主题版本，旧报告固定的 v1 必须仍可复现
        self.catalog.add_topic(TopicDefinition(
            topic="international-cooperation", version=2,
            label="国际合作（细化）",
            coding_rules="细分多边/双边合作报道",
            valid_from=date(2027, 1, 1),
        ))
        result = reproduce_joint_report(
            self.report, self.catalog, self.survey, self.media
        )
        self.assertTrue(result.matches)

    def test_pinned_version_missing_from_catalog_raises(self):
        narrow_catalog = DefinitionCatalog(
            questions=(
                self.catalog.get_question("q-concern", 1),
                self.catalog.get_question("q-concern", 2),
            ),
            populations=(self.catalog.get_population("adults-cn"),),
            topics=(),  # 主题定义缺失
        )
        with self.assertRaises(KeyError):
            reproduce_joint_report(
                self.report, narrow_catalog, self.survey, self.media
            )


if __name__ == "__main__":
    unittest.main()
