from django import forms
from django.db.models import Q

from accounts.models import UserProfile
from accounts.views import (
    get_staff_subjects_for_class,
    get_staff_teacher,
    is_class_teacher_for,
)
from timetable.models import TimetableSubject
from timetable.advanced_models import TimetableTeacherTeachingAssignment
from students.models import Student

from .models import WeeklyAssessmentReport, WeeklyAssessmentWeek


def _profile(user):
    return UserProfile.objects.filter(user=user).first()


def _is_admin(user):
    profile = _profile(user)
    return user.is_superuser or (
        profile is not None and profile.role == "ADMIN"
    )


def _staff_can_edit_target(user, student, subject):
    if _is_admin(user):
        return True

    teacher = get_staff_teacher(user)

    if not teacher:
        return False

    try:
        if is_class_teacher_for(user, student.class_name):
            return True
    except Exception:
        pass

    try:
        subjects = get_staff_subjects_for_class(
            user,
            student.class_name,
        )

        return any(
            getattr(item, "pk", None) == subject.pk
            for item in subjects
        )
    except Exception:
        return False


class AssignmentSubjectSelect(forms.Select):
    def __init__(self, *args, assignment_map=None, **kwargs):
        self.assignment_map = assignment_map or {}
        super().__init__(*args, **kwargs)

    def create_option(
        self,
        name,
        value,
        label,
        selected,
        index,
        subindex=None,
        attrs=None,
    ):
        option = super().create_option(
            name,
            value,
            label,
            selected,
            index,
            subindex=subindex,
            attrs=attrs,
        )

        subject_id = str(value) if value else ""

        assignments = self.assignment_map.get(
            subject_id,
            [],
        )

        option["attrs"]["data-assignment"] = (
            "1" if assignments else "0"
        )

        option["attrs"]["data-assignment-classes"] = "|".join(
            item["class_name"]
            for item in assignments
        )

        option["attrs"]["data-assignment-streams"] = "|".join(
            item["stream"]
            for item in assignments
        )

        return option

class WeeklyAssessmentReportForm(forms.ModelForm):

    week = forms.ModelChoiceField(
        queryset=WeeklyAssessmentWeek.objects.none(),
        required=False,
        empty_label="Select assessment week",
        label="Assessment Week",
        widget=forms.Select(
            attrs={
                "class": "form-control",
            }
        ),
    )

    class Meta:
        model = WeeklyAssessmentReport

        fields = [
            "student",
            "subject",
            "week",
            "week_start",
            "week_end",
            "week_number",
            "score",
            "max_score",
            "teacher_report",
            "is_published",
        ]

        widgets = {
            "student": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),
            "subject": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),
            "week_start": forms.DateInput(
                attrs={
                    "type": "date",
                    "class": "form-control",
                }
            ),
            "week_end": forms.DateInput(
                attrs={
                    "type": "date",
                    "class": "form-control",
                }
            ),
            "week_number": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": "1",
                    "max": "53",
                }
            ),
            "score": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.01",
                    "min": "0",
                }
            ),
            "max_score": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.01",
                    "min": "0.01",
                }
            ),
            "teacher_report": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 5,
                    "placeholder": (
                        "Write the learner's weekly assessment report..."
                    ),
                }
            ),
            "is_published": forms.CheckboxInput(
                attrs={
                    "class": "form-check-input",
                }
            ),
        }

        labels = {
            "student": "Learner",
            "subject": "Learning Area / Subject",
            "week_start": "Date From",
            "week_end": "Date To",
            "week_number": "Week Number",
            "score": "Score",
            "max_score": "Maximum Score",
            "teacher_report": "Weekly Report / Teacher Comment",
            "is_published": "Publish to Parent and Student",
        }

    def __init__(self, user, *args, **kwargs):
        self.user = user

        super().__init__(*args, **kwargs)

        # Admin can work with all assessment weeks.
        # Staff can only use weeks that are still open.
        if _is_admin(user):
            self.fields["week"].queryset = (
                WeeklyAssessmentWeek.objects
                .select_related("academic_year", "term")
                .order_by("-week_start", "-week_number")
            )
        else:
            self.fields["week"].queryset = (
                WeeklyAssessmentWeek.objects
                .filter(is_locked=False)
                .select_related("academic_year", "term")
                .order_by("-week_start", "-week_number")
            )

        if self.instance and self.instance.pk:
            if self.instance.week_id:
                self.initial["week"] = self.instance.week_id

        # Staff must use the Admin-created week.
        # Hide the manually editable date/week fields for staff.
        if not _is_admin(user):
            for name in (
                "week_start",
                "week_end",
                "week_number",
            ):
                if name in self.fields:
                    self.fields[name].required = False
                    self.fields[name].widget = forms.HiddenInput()

        self.fields["student"].queryset = (
            self._student_queryset()
        )

        subject_queryset = self._subject_queryset()

        self.fields["subject"].queryset = subject_queryset

        # Staff subject-assignment metadata used by the
        # Staff form to filter subjects by learner class/stream.
        if not _is_admin(user):

            assignment_map = {}

            teacher = get_staff_teacher(user)

            if teacher:

                assignments = (
                    TimetableTeacherTeachingAssignment.objects
                    .filter(
                        teacher=teacher,
                        is_active=True,
                    )
                    .select_related("subject")
                )

                for assignment in assignments:

                    if not assignment.subject_id:
                        continue

                    assignment_map.setdefault(
                        str(assignment.subject_id),
                        [],
                    ).append({
                        "class_name": (
                            assignment.class_name or ""
                        ).strip(),
                        "stream": (
                            assignment.stream or ""
                        ).strip(),
                    })

                # Class teachers may use all subjects for
                # learners in their assigned class.
                students = self._student_queryset()

                class_names = (
                    students
                    .values_list(
                        "class_name",
                        flat=True,
                    )
                    .distinct()
                )

                class_teacher_classes = []

                for class_name in class_names:

                    if not class_name:
                        continue

                    try:
                        if is_class_teacher_for(
                            user,
                            class_name,
                        ):
                            class_teacher_classes.append(
                                class_name
                            )
                    except Exception:
                        continue

                if class_teacher_classes:

                    for subject in subject_queryset:

                        entries = assignment_map.setdefault(
                            str(subject.pk),
                            [],
                        )

                        for class_name in class_teacher_classes:

                            entries.append({
                                "class_name": (
                                    class_name or ""
                                ).strip(),
                                "stream": "",
                            })

            self.fields["subject"].widget = (
                AssignmentSubjectSelect(
                    assignment_map=assignment_map
                )
            )

    def _student_queryset(self):

        if _is_admin(self.user):

            return Student.objects.filter(
                is_active=True
            ).order_by(
                "class_name",
                "stream",
                "last_name",
                "first_name",
            )


        teacher = get_staff_teacher(self.user)

        if not teacher:
            return Student.objects.none()


        # -------------------------------------------------
        # Build the Staff learner list directly from the
        # teacher's active teaching assignments.
        # -------------------------------------------------

        assignments = TimetableTeacherTeachingAssignment.objects.filter(
            teacher=teacher,
            is_active=True,
        )


        allowed_class_streams = set()
        class_teacher_classes = set()


        for assignment in assignments:

            class_name = (
                assignment.class_name or ""
            ).strip()

            stream = (
                assignment.stream or ""
            ).strip()


            if not class_name:
                continue


            allowed_class_streams.add(
                (
                    class_name.lower(),
                    stream.lower(),
                )
            )


        # -------------------------------------------------
        # Also allow all learners in classes where this
        # teacher is the designated class teacher.
        # -------------------------------------------------

        all_students = Student.objects.filter(
            is_active=True
        ).order_by(
            "class_name",
            "stream",
            "last_name",
            "first_name",
        )


        allowed_ids = []


        for student in all_students:

            student_class = (
                student.class_name or ""
            ).strip()

            student_stream = (
                student.stream or ""
            ).strip()


            # Class teacher access
            try:

                if is_class_teacher_for(
                    self.user,
                    student_class,
                ):

                    allowed_ids.append(
                        student.pk
                    )

                    continue

            except Exception:
                pass


            # Subject teacher access
            key = (
                student_class.lower(),
                student_stream.lower(),
            )


            if key in allowed_class_streams:

                allowed_ids.append(
                    student.pk
                )


        return Student.objects.filter(
            pk__in=allowed_ids
        ).order_by(
            "class_name",
            "stream",
            "last_name",
            "first_name",
        )

    def _subject_queryset(self):

        # Administrator can use every subject.
        if _is_admin(self.user):

            return TimetableSubject.objects.all().order_by(
                "name"
            )


        teacher = get_staff_teacher(self.user)

        if not teacher:
            return TimetableSubject.objects.none()


        # -------------------------------------------------
        # Subjects directly assigned to this teacher.
        # -------------------------------------------------

        assignments = TimetableTeacherTeachingAssignment.objects.filter(
            teacher=teacher,
            is_active=True,
        ).select_related("subject")


        subject_ids = set()


        for assignment in assignments:

            if assignment.subject_id:
                subject_ids.add(
                    assignment.subject_id
                )


        # -------------------------------------------------
        # A class teacher may write/view ALL subjects for
        # learners in their assigned class.
        #
        # The class-teacher check is handled against the
        # learner during validation. For the form's subject
        # dropdown, include all active subjects when the
        # teacher has at least one class-teacher assignment.
        # -------------------------------------------------

        students = self._student_queryset()

        for class_name in (
            students
            .values_list(
                "class_name",
                flat=True,
            )
            .distinct()
        ):

            if not class_name:
                continue

            try:

                if is_class_teacher_for(
                    self.user,
                    class_name,
                ):

                    subject_ids.update(
                        TimetableSubject.objects.values_list(
                            "pk",
                            flat=True,
                        )
                    )

                    break

            except Exception:
                continue


        return TimetableSubject.objects.filter(
            pk__in=subject_ids
        ).order_by(
            "name"
        )

    def clean(self):
        cleaned = super().clean()

        student = cleaned.get("student")
        subject = cleaned.get("subject")
        selected_week = cleaned.get("week")

        # Staff must select an Admin-created week.
        if not _is_admin(self.user):

            if not selected_week:
                self.add_error(
                    "week",
                    "Please select an assessment week created by the Administrator.",
                )

            elif selected_week.is_locked:
                self.add_error(
                    "week",
                    "This assessment week is locked by the Administrator.",
                )

        # If a week is selected, automatically inherit
        # its dates and week number.
        if selected_week:
            cleaned["week_start"] = selected_week.week_start
            cleaned["week_end"] = selected_week.week_end
            cleaned["week_number"] = selected_week.week_number

        week_start = cleaned.get("week_start")
        week_end = cleaned.get("week_end")
        week_number = cleaned.get("week_number")
        score = cleaned.get("score")
        max_score = cleaned.get("max_score")

        if week_start and week_end:
            if week_end < week_start:
                self.add_error(
                    "week_end",
                    "Date To cannot be before Date From.",
                )

        if week_number is None and week_start:
            cleaned["week_number"] = (
                week_start.isocalendar().week
            )

        if week_number is not None:
            if not 1 <= week_number <= 53:
                self.add_error(
                    "week_number",
                    "Week number must be between 1 and 53.",
                )

        if max_score is not None and max_score <= 0:
            self.add_error(
                "max_score",
                "Maximum score must be greater than zero.",
            )

        if score is not None and score < 0:
            self.add_error(
                "score",
                "Score cannot be negative.",
            )

        if (
            score is not None
            and max_score is not None
            and score > max_score
        ):
            self.add_error(
                "score",
                "Score cannot be greater than maximum score.",
            )

        if student and subject:
            if not _staff_can_edit_target(
                self.user,
                student,
                subject,
            ):
                raise forms.ValidationError(
                    "You are not permitted to write this learning area's report for this learner."
                )

        return cleaned






