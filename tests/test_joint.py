import unittest
from datetime import date

from signal_lab.definitions import (
    DefinitionCatalog,
    Population,
    SurveyQuestion,
    TopicDefinition,
)
from signal_lab.joint import (
    CAVEAT_TEXTS,
    Interpretation,
    MediaScope,
    build_joint_observation,
    digest_joints,
    plan_joint_observations,
)
from signal_lab.records import Observation, SurveyObservation, SurveyStatus


def build_catalog():
    population = Population("adults-cn", "中国成年居民", "18 岁及以上常住居民")
    question_v1 = SurveyQuestion(
        question_id="q-concern",
        version=1,
        topic="international-cooperation",
        label="最关心的议题",
        wording="未来一年您最关心的议题是？",
        response_scale="多选，选填三项",
        valid_from=date(2026, 1, 1),
        valid_to=date(2026, 11, 30),
        population_ids=("adults-cn",),
    )
    question_v2 = SurveyQuestion(
        question_id="q-concern",
        version=2,
        topic="international-cooperation",
        label="最关心的议题（量表版）",
        wording="请对下列议题的关心程度打分（1-5）",
        response_scale="1-5 李克特量表",
        valid_from=date(2026, 12, 1),
        population_ids=("adults-cn",),
    )
    topic_v1 = TopicDefinition(
        topic="international-cooperation",
        version=1,
        label="国际合作",
        coding_rules="提及外交、国际组织与双边合作的报道归入本主题",
        valid_from=date(2026, 1, 1),
    )
    return DefinitionCatalog(
        questions=(question_v1, question_v2),
        populations=(population,),
        topics=(topic_v1,),
    )


class SurveyObservationGuardTests(unittest.TestCase):
    def test_zero_valid_responses_cannot_be_recorded_as_zero(self):
        with self.assertRaises(ValueError):
            SurveyObservation(
                "s-bad", "q-concern", 1, "adults-cn",
                date(2026, 11, 1), "international-cooperation",
                valid_responses=0, value=0,
            )

    def test_no_valid_responses_is_missing_not_zero(self):
        row = SurveyObservation(
            "s-missing", "q-concern", 1, "adults-cn",
            date(2026, 11, 1), "international-cooperation",
            valid_responses=0, value=None,
            status=SurveyStatus.NO_VALID_RESPONSES,
        )
        self.assertIsNone(row.value)
        self.assertEqual(row.status, SurveyStatus.NO_VALID_RESPONSES)

    def test_no_record_status_is_not_allowed_on_stored_rows(self):
        with self.assertRaises(ValueError):
            SurveyObservation(
                "s-x", "q-concern", 1, "adults-cn",
                date(2026, 11, 1), "international-cooperation",
                valid_responses=0, value=None,
                status=SurveyStatus.NO_RECORD,
            )

    def test_valid_row_requires_value_and_denominator(self):
        with self.assertRaises(ValueError):
            SurveyObservation(
                "s-x", "q-concern", 1, "adults-cn",
                date(2026, 11, 1), "international-cooperation",
                valid_responses=10, value=None,
            )


class JointObservationTests(unittest.TestCase):
    def setUp(self):
        self.catalog = build_catalog()
        self.question = self.catalog.get_question("q-concern", 1)
        self.topic = self.catalog.get_topic("international-cooperation", 1)
        self.scope = MediaScope(("global-desk", "regional-review"), region="global")

    def test_joint_observation_pins_question_population_and_media_scope(self):
        survey = [
            SurveyObservation(
                "s-1", "q-concern", 1, "adults-cn",
                date(2026, 11, 1), "international-cooperation",
                valid_responses=800, value=0.42,
            )
        ]
        media = [
            Observation("o-1", "global-desk", date(2026, 11, 2),
                        "international-cooperation", 4),
            Observation("o-2", "regional-review", date(2026, 11, 3),
                        "international-cooperation", 2),
        ]
        joint = build_joint_observation(
            "j-1", (2026, 11), self.question, "adults-cn",
            self.topic, survey, media, self.scope,
        )
        self.assertEqual(joint.question_id, "q-concern")
        self.assertEqual(joint.question_version, 1)
        self.assertEqual(joint.population_id, "adults-cn")
        self.assertEqual(joint.media_scope.source_ids,
                         ("global-desk", "regional-review"))
        self.assertEqual(joint.survey_value, 0.42)
        self.assertEqual(joint.survey_valid_responses, 800)
        self.assertEqual(joint.media_value, 6)
        self.assertEqual(joint.media_source_count, 2)
        self.assertIs(joint.interpretation, Interpretation.PARALLEL_TREND)
        self.assertFalse(joint.supports_association())
        self.assertIn("parallel_only", joint.caveats)
        self.assertIn("media_not_opinion", joint.caveats)

    def test_no_valid_responses_group_is_missing_in_joint_view(self):
        survey = [
            SurveyObservation(
                "s-2", "q-concern", 1, "adults-cn",
                date(2026, 11, 1), "international-cooperation",
                valid_responses=0, value=None,
                status=SurveyStatus.NO_VALID_RESPONSES,
            )
        ]
        media = [
            Observation("o-1", "global-desk", date(2026, 11, 2),
                        "international-cooperation", 4),
        ]
        joint = build_joint_observation(
            "j-2", (2026, 11), self.question, "adults-cn",
            self.topic, survey, media, self.scope,
        )
        self.assertIsNone(joint.survey_value)
        self.assertEqual(joint.survey_status, SurveyStatus.NO_VALID_RESPONSES)
        self.assertFalse(joint.has_survey_value())
        survey_gaps = [g for g in joint.gaps if g.side == "survey"]
        self.assertEqual([g.code for g in survey_gaps], ["no_valid_responses"])
        self.assertIn("survey_missing", joint.caveats)
        # 媒体侧仍然独立成立
        self.assertEqual(joint.media_value, 4)

    def test_missing_survey_record_is_distinct_from_zero(self):
        media = [
            Observation("o-1", "global-desk", date(2026, 11, 2),
                        "international-cooperation", 4),
        ]
        joint = build_joint_observation(
            "j-3", (2026, 11), self.question, "adults-cn",
            self.topic, [], media, self.scope,
        )
        self.assertIsNone(joint.survey_value)
        self.assertEqual(joint.survey_status, SurveyStatus.NO_RECORD)
        self.assertEqual(
            [g.code for g in joint.gaps if g.side == "survey"], ["no_record"]
        )
        self.assertIn("survey_no_record", joint.caveats)

    def test_media_missing_when_no_observation_in_scope(self):
        survey = [
            SurveyObservation(
                "s-1", "q-concern", 1, "adults-cn",
                date(2026, 11, 1), "international-cooperation",
                valid_responses=800, value=0.42,
            )
        ]
        joint = build_joint_observation(
            "j-4", (2026, 11), self.question, "adults-cn",
            self.topic, survey, [], self.scope,
        )
        self.assertIsNone(joint.media_value)
        self.assertFalse(joint.has_media_value())
        self.assertEqual(
            [g.code for g in joint.gaps if g.side == "media"], ["no_observation"]
        )
        self.assertIn("media_missing", joint.caveats)

    def test_media_no_coverage_distinguished_from_no_observation(self):
        # 范围内有媒体观察，但都是其他主题：属于 no_coverage 而非 no_observation
        media = [
            Observation("o-9", "global-desk", date(2026, 11, 5),
                        "other-topic", 3),
        ]
        joint = build_joint_observation(
            "j-4b", (2026, 11), self.question, "adults-cn",
            self.topic, [], media, self.scope,
        )
        self.assertIsNone(joint.media_value)
        self.assertEqual(
            [g.code for g in joint.gaps if g.side == "media"], ["no_coverage"]
        )
        self.assertIn("media_no_coverage", joint.caveats)

    def test_media_rows_outside_scope_are_not_counted(self):
        media = [
            Observation("o-x", "outside-desk", date(2026, 11, 2),
                        "international-cooperation", 99),
        ]
        joint = build_joint_observation(
            "j-5", (2026, 11), self.question, "adults-cn",
            self.topic, [], media, self.scope,
        )
        self.assertIsNone(joint.media_value)

    def test_media_records_rejected_in_survey_slot(self):
        media = [
            Observation("o-1", "global-desk", date(2026, 11, 2),
                        "international-cooperation", 4),
        ]
        with self.assertRaises(TypeError):
            build_joint_observation(
                "j-6", (2026, 11), self.question, "adults-cn",
                self.topic, media, [], self.scope,
            )

    def test_survey_records_rejected_in_media_slot(self):
        survey = [
            SurveyObservation(
                "s-1", "q-concern", 1, "adults-cn",
                date(2026, 11, 1), "international-cooperation",
                valid_responses=800, value=0.42,
            )
        ]
        with self.assertRaises(TypeError):
            build_joint_observation(
                "j-7", (2026, 11), self.question, "adults-cn",
                self.topic, [], survey, self.scope,
            )

    def test_question_and_topic_must_align(self):
        other_topic = TopicDefinition(
            topic="other-topic", version=1, label="其他",
            coding_rules="-", valid_from=date(2026, 1, 1),
        )
        with self.assertRaises(ValueError):
            build_joint_observation(
                "j-8", (2026, 11), self.question, "adults-cn",
                other_topic, [], [], self.scope,
            )

    def test_population_must_be_covered_by_question(self):
        with self.assertRaises(ValueError):
            build_joint_observation(
                "j-9", (2026, 11), self.question, "unknown-pop",
                self.topic, [], [], self.scope,
            )

    def test_caveat_texts_cover_every_code(self):
        survey = [
            SurveyObservation(
                "s-1", "q-concern", 1, "adults-cn",
                date(2026, 11, 1), "international-cooperation",
                valid_responses=800, value=0.42,
            )
        ]
        media = [
            Observation("o-1", "global-desk", date(2026, 11, 2),
                        "international-cooperation", 4),
        ]
        joint = build_joint_observation(
            "j-10", (2026, 11), self.question, "adults-cn",
            self.topic, survey, media, self.scope,
        )
        for code in joint.caveats:
            self.assertIn(code, CAVEAT_TEXTS)


class DefinitionVersioningTests(unittest.TestCase):
    def setUp(self):
        self.catalog = build_catalog()

    def test_version_resolution_changes_after_questionnaire_update(self):
        v1 = self.catalog.question_version_on("q-concern", date(2026, 11, 1))
        v2 = self.catalog.question_version_on("q-concern", date(2026, 12, 1))
        self.assertEqual(v1.version, 1)
        self.assertEqual(v2.version, 2)
        self.assertNotEqual(v1.wording, v2.wording)

    def test_registered_versions_are_immutable(self):
        with self.assertRaises(KeyError):
            self.catalog.add_question(self.catalog.get_question("q-concern", 1))

    def test_planning_uses_the_version_active_in_each_period(self):
        survey = [
            SurveyObservation(
                "s-1", "q-concern", 1, "adults-cn",
                date(2026, 11, 1), "international-cooperation",
                valid_responses=800, value=0.42,
            ),
            SurveyObservation(
                "s-2", "q-concern", 2, "adults-cn",
                date(2026, 12, 1), "international-cooperation",
                valid_responses=750, value=3.6,
            ),
        ]
        media = [
            Observation("o-1", "global-desk", date(2026, 11, 2),
                        "international-cooperation", 4),
            Observation("o-2", "global-desk", date(2026, 12, 2),
                        "international-cooperation", 7),
        ]
        scope = MediaScope(("global-desk",))
        joints = plan_joint_observations(
            [(2026, 11), (2026, 12)], "q-concern", "adults-cn",
            "international-cooperation", self.catalog, survey, media, scope,
        )
        self.assertEqual(
            [j.question_version for j in joints], [1, 2]
        )
        self.assertEqual([j.survey_value for j in joints], [0.42, 3.6])

    def test_identical_inputs_produce_identical_digest(self):
        survey = [
            SurveyObservation(
                "s-1", "q-concern", 1, "adults-cn",
                date(2026, 11, 1), "international-cooperation",
                valid_responses=800, value=0.42,
            )
        ]
        media = [
            Observation("o-1", "global-desk", date(2026, 11, 2),
                        "international-cooperation", 4),
        ]
        scope = MediaScope(("global-desk",))
        question = self.catalog.get_question("q-concern", 1)
        topic = self.catalog.get_topic("international-cooperation", 1)
        kwargs = dict(
            period=(2026, 11), question=question, population_id="adults-cn",
            topic_def=topic, survey_rows=survey, media_rows=media,
            media_scope=scope,
        )
        first = digest_joints([build_joint_observation("j", **kwargs)])
        second = digest_joints([build_joint_observation("j", **kwargs)])
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
