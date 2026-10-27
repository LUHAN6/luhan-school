from datetime import date
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase

from academic.models import Assessment, AssessmentType, Subject
from academic.performance_analytics import build_performance_analytics
from fees.models import AcademicYear, Term
from students.models import Student


class PerformanceAnalyticsTests(TestCase):
    """Regression tests for academic performance comparisons."""

    def setUp(self):
        self.user = User.objects.create_superuser(
            username="analytics_test_admin",
            email="analytics-test@example.invalid",
            password="test-only-password",
        )

        self.year = AcademicYear.objects.create(year=2041)
        self.other_year = AcademicYear.objects.create(year=2042)

        self.term_one = Term.objects.create(
            name="Term 1",
            order=1,
            academic_year=self.year,
        )
        self.term_two = Term.objects.create(
            name="Term 2",
            order=2,
            academic_year=self.year,
        )
        self.foreign_term = Term.objects.create(
            name="Term 1",
            order=1,
            academic_year=self.other_year,
        )

        self.quiz = AssessmentType.objects.create(
            name="Quiz",
            code="ANALYTICS_QUIZ",
            order=1,
        )
        self.exam = AssessmentType.objects.create(
            name="Examination",
            code="ANALYTICS_EXAM",
            order=2,
        )

        self.maths = Subject.objects.create(
            name="Mathematics",
            code="ANALYTICS_MATHS",
        )
        self.english = Subject.objects.create(
            name="English",
            code="ANALYTICS_ENGLISH",
        )

        self.learner_one = Student.objects.create(
            admission_no="ANALYTICS001",
            first_name="Test",
            last_name="Learner One",
            gender="Male",
            date_of_birth=date(2012, 1, 1),
            class_name="Grade 6",
            stream="East",
            parent_name="Test Parent",
            parent_phone="0700000001",
        )
        self.learner_two = Student.objects.create(
            admission_no="ANALYTICS002",
            first_name="Test",
            last_name="Learner Two",
            gender="Female",
            date_of_birth=date(2012, 2, 1),
            class_name="Grade 6",
            stream="East",
            parent_name="Test Parent",
            parent_phone="0700000002",
        )

        self._add_mark(
            self.learner_one, self.year, self.term_one,
            self.maths, self.quiz, 60,
        )
        self._add_mark(
            self.learner_one, self.year, self.term_two,
            self.maths, self.quiz, 80,
        )
        self._add_mark(
            self.learner_two, self.year, self.term_two,
            self.maths, self.quiz, 70,
        )
        self._add_mark(
            self.learner_one, self.year, self.term_two,
            self.maths, self.exam, 90,
        )

        # Deliberately inconsistent record: the academic year on the
        # mark is 2041, but the related term belongs to 2042.
        # Analytics must exclude it from year 2041 comparisons.
        self._add_mark(
            self.learner_one, self.year, self.foreign_term,
            self.maths, self.quiz, 100,
        )

    def _add_mark(
        self, student, year, term, subject, assessment_type, score
    ):
        return Assessment.objects.create(
            student=student,
            academic_year=year,
            term=term,
            subject=subject,
            assessment_type=assessment_type,
            score=score,
        )

    def _build(self, assessment_type=None):
        # Isolate analytics calculations from timetable/staff assignment
        # fixtures. These mocks do not alter the access-control code.
        with (
            patch(
                "academic.performance_analytics.can_view_class",
                return_value=True,
            ),
            patch(
                "academic.performance_analytics.get_staff_students",
                return_value=Student.objects.filter(
                    pk__in=[self.learner_one.pk, self.learner_two.pk]
                ),
            ),
            patch(
                "academic.performance_analytics.get_staff_subjects_for_class",
                return_value=Subject.objects.filter(is_active=True),
            ),
        ):
            return build_performance_analytics(
                user=self.user,
                selected_year=self.year,
                selected_term=self.term_two,
                selected_assessment_type=assessment_type,
                selected_class="Grade 6",
                selected_stream="East",
            )

    def test_term_comparison_excludes_marks_with_foreign_year_term(self):
        result = self._build(self.quiz)

        terms = result["term_comparison"]
        self.assertEqual(len(terms), 2)
        self.assertEqual(
            [item["average"] for item in terms],
            [60.0, 75.0],
        )
        self.assertEqual(
            [item["marks"] for item in terms],
            [1, 2],
        )

    def test_assessment_type_filter_is_consistent(self):
        result = self._build(self.quiz)

        subjects = result["subject_comparison"]
        self.assertEqual(len(subjects), 1)
        self.assertEqual(subjects[0]["name"], "Mathematics")
        self.assertEqual(subjects[0]["average"], 75.0)
        self.assertEqual(subjects[0]["marks"], 2)

        progress = {
            item["student"].admission_no: item
            for item in result["learner_progress"]
        }
        learner_one = progress["ANALYTICS001"]
        self.assertEqual(learner_one["current_average"], 80.0)
        self.assertEqual(learner_one["previous_average"], 60.0)
        self.assertEqual(learner_one["change"], 20.0)

        # A learner without a previous-term mark has no fabricated change.
        learner_two = progress["ANALYTICS002"]
        self.assertEqual(learner_two["current_average"], 70.0)
        self.assertIsNone(learner_two["previous_average"])
        self.assertIsNone(learner_two["change"])

    def test_assessment_comparison_reports_each_active_type(self):
        result = self._build(self.quiz)

        comparisons = {
            item["name"]: item
            for item in result["assessment_comparison"]
        }
        self.assertEqual(comparisons["Quiz"]["average"], 75.0)
        self.assertEqual(comparisons["Quiz"]["marks"], 2)
        self.assertEqual(comparisons["Examination"]["average"], 90.0)
        self.assertEqual(comparisons["Examination"]["marks"], 1)

    def test_coverage_is_calculated_and_labelled_as_an_estimate(self):
        result = self._build(self.quiz)
        coverage = result["assessment_coverage"]

        self.assertEqual(coverage["expected"], 2)
        self.assertEqual(coverage["recorded"], 2)
        self.assertEqual(coverage["percentage"], 100.0)
        self.assertIn("Estimated", coverage["basis"])
        self.assertIn("not a definitive", coverage["basis"])

    def test_inaccessible_class_returns_empty_analytics(self):
        with patch(
            "academic.performance_analytics.can_view_class",
            return_value=False,
        ):
            result = build_performance_analytics(
                user=self.user,
                selected_year=self.year,
                selected_term=self.term_two,
                selected_assessment_type=self.quiz,
                selected_class="Grade 6",
                selected_stream="East",
            )

        self.assertEqual(result["assessment_comparison"], [])
        self.assertEqual(result["term_comparison"], [])
        self.assertEqual(result["subject_comparison"], [])
        self.assertEqual(result["learner_progress"], [])
        self.assertEqual(result["assessment_coverage"]["expected"], 0)

