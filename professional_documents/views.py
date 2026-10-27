
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from fees.models import AcademicYear, Term
from timetable.models import TimetableSubject
from timetable.advanced_models import TimetableTeacherTeachingAssignment

from weekly_reports.views import (
    _is_admin,
    _is_staff,
    get_staff_teacher,
)


from .models import ProfessionalDocument


def _parse_class(value):
    parts = (value or "").split("||", 1)
    class_name = parts[0].strip()
    stream = parts[1].strip() if len(parts) > 1 else ""
    return class_name, stream


def _assigned_options(user):
    teacher = get_staff_teacher(user)

    if not teacher:
        return []

    assignments = (
        TimetableTeacherTeachingAssignment.objects
        .filter(
            teacher=teacher,
            is_active=True,
        )
        .select_related("subject")
        .order_by(
            "class_name",
            "stream",
            "subject__name",
        )
    )

    result = []
    seen = set()

    for assignment in assignments:

        class_name = (assignment.class_name or "").strip()
        stream = (assignment.stream or "").strip()

        if not class_name or not assignment.subject_id:
            continue

        key = (
            class_name.lower(),
            stream.lower(),
            assignment.subject_id,
        )

        if key in seen:
            continue

        seen.add(key)

        result.append({
            "value": (
                f"{class_name}||{stream}||"
                f"{assignment.subject_id}"
            ),
            "class_name": class_name,
            "stream": stream,
            "subject": assignment.subject,
            "subject_id": assignment.subject_id,
            "label": (
                f"{class_name} / {stream} — "
                f"{assignment.subject.name}"
                if stream
                else
                f"{class_name} — "
                f"{assignment.subject.name}"
            ),
        })

    return result


def _assignment_allowed(
    user,
    class_name,
    stream,
    subject_id,
):
    teacher = get_staff_teacher(user)

    if not teacher:
        return False

    qs = TimetableTeacherTeachingAssignment.objects.filter(
        teacher=teacher,
        class_name__iexact=class_name,
        subject_id=subject_id,
        is_active=True,
    )

    learner_stream = (stream or "").strip().lower()

    for assignment in qs:

        assigned_stream = (
            assignment.stream or ""
        ).strip().lower()

        if not assigned_stream:
            return True

        if assigned_stream == learner_stream:
            return True

    return False


def _admin_context():
    return {
        "academic_years": AcademicYear.objects.all().order_by("-year"),

        "terms": Term.objects.all().order_by("-id"),

        "subjects": TimetableSubject.objects.all().order_by("name"),
    }


@login_required
def portal(request):

    if _is_admin(request.user):
        return redirect(
            "professional_documents:admin_documents"
        )

    if _is_staff(request.user):
        return redirect(
            "professional_documents:staff_documents"
        )

    return HttpResponseForbidden(
        "Professional Documents access required."
    )


@login_required
def staff_documents(request):

    if not _is_staff(request.user):
        return HttpResponseForbidden(
            "Teaching staff access required."
        )

    documents = (
        ProfessionalDocument.objects
        .filter(teacher=request.user)
        .select_related(
            "academic_year",
            "term",
            "subject",
        )
    )

    document_type = request.GET.get(
        "type",
        "",
    ).strip()

    status = request.GET.get(
        "status",
        "",
    ).strip()

    if document_type:
        documents = documents.filter(
            document_type=document_type
        )

    if status:
        documents = documents.filter(
            status=status
        )

    return render(
        request,
        "professional_documents/staff_documents.html",
        {
            "documents": documents,
            "document_types": ProfessionalDocument.DOCUMENT_TYPES,
            "statuses": ProfessionalDocument.STATUS_CHOICES,
        },
    )


@login_required
def admin_documents(request):

    if not _is_admin(request.user):
        return HttpResponseForbidden(
            "Administrator access required."
        )

    documents = (
        ProfessionalDocument.objects
        .select_related(
            "teacher",
            "academic_year",
            "term",
            "subject",
            "reviewed_by",
        )
    )

    document_type = request.GET.get(
        "type",
        "",
    ).strip()

    status = request.GET.get(
        "status",
        "",
    ).strip()

    class_name = request.GET.get(
        "class",
        "",
    ).strip()

    teacher = request.GET.get(
        "teacher",
        "",
    ).strip()

    if document_type:
        documents = documents.filter(
            document_type=document_type
        )

    if status:
        documents = documents.filter(
            status=status
        )

    if class_name:
        documents = documents.filter(
            class_name__iexact=class_name
        )

    if teacher:
        documents = documents.filter(
            teacher_id=teacher
        )

    teachers = (
        ProfessionalDocument.objects
        .values(
            "teacher_id",
            "teacher__username",
            "teacher__first_name",
            "teacher__last_name",
        )
        .distinct()
        .order_by(
            "teacher__first_name",
            "teacher__last_name",
        )
    )

    classes = (
        ProfessionalDocument.objects
        .values_list(
            "class_name",
            flat=True,
        )
        .distinct()
        .order_by("class_name")
    )

    return render(
        request,
        "professional_documents/admin_documents.html",
        {
            "documents": documents,
            "document_types": ProfessionalDocument.DOCUMENT_TYPES,
            "statuses": ProfessionalDocument.STATUS_CHOICES,
            "teachers": teachers,
            "classes": classes,
            "selected_type": document_type,
            "selected_status": status,
            "selected_class": class_name,
            "selected_teacher": teacher,
        },
    )


@login_required
def document_create(request):

    if not _is_staff(request.user) and not _is_admin(request.user):
        return HttpResponseForbidden(
            "Professional Documents access required."
        )

    assignments = (
        _assigned_options(request.user)
        if _is_staff(request.user)
        else []
    )

    if request.method == "POST":

        document_type = request.POST.get(
            "document_type",
            "",
        ).strip()

        year_id = request.POST.get(
            "academic_year",
            "",
        )

        term_id = request.POST.get(
            "term",
            "",
        )

        class_value = request.POST.get(
            "class_assignment",
            "",
        )

        lesson_date = request.POST.get(
            "lesson_date",
            "",
        )

        start_time = request.POST.get(
            "start_time",
            "",
        )

        end_time = request.POST.get(
            "end_time",
            "",
        )

        from_date = request.POST.get(
            "from_date",
            "",
        )

        to_date = request.POST.get(
            "to_date",
            "",
        )

        title = request.POST.get(
            "title",
            "",
        ).strip()

        content = request.POST.get(
            "content",
            "",
        ).strip()

        uploaded_file = request.FILES.get(
            "uploaded_file"
        )

        year = get_object_or_404(
            AcademicYear,
            pk=year_id,
        )

        term = get_object_or_404(
            Term,
            pk=term_id,
        )

        parts = (class_value or "").split("||")

        if len(parts) != 3:
            messages.error(
                request,
                "Select your assigned class and subject.",
            )
            return redirect(
                "professional_documents:create"
            )

        class_name = parts[0].strip()
        stream = parts[1].strip()

        try:
            subject_id = int(parts[2])
        except ValueError:
            messages.error(
                request,
                "Invalid subject selection.",
            )
            return redirect(
                "professional_documents:create"
            )

        subject = get_object_or_404(
            TimetableSubject,
            pk=subject_id,
        )

        if _is_staff(request.user):

            if not _assignment_allowed(
                request.user,
                class_name,
                stream,
                subject.pk,
            ):
                return HttpResponseForbidden(
                    "You are not assigned to this "
                    "class and subject."
                )

            teacher = request.user

        else:

            teacher_id = request.POST.get(
                "teacher",
                "",
            )

            if teacher_id:
                from django.contrib.auth import get_user_model
                User = get_user_model()
                teacher = get_object_or_404(
                    User,
                    pk=teacher_id,
                )
            else:
                teacher = request.user

        if document_type not in dict(
            ProfessionalDocument.DOCUMENT_TYPES
        ):
            messages.error(
                request,
                "Select a valid document type.",
            )
            return redirect(
                "professional_documents:create"
            )

        if document_type == ProfessionalDocument.TYPE_SCHEME:

            if not uploaded_file:
                messages.error(
                    request,
                    "Schemes of Work must be uploaded "
                    "as PDF or Word.",
                )
                return redirect(
                    "professional_documents:create"
                )

            extension = (
                uploaded_file.name
                .rsplit(".", 1)[-1]
                .lower()
            )

            if extension not in [
                "pdf",
                "doc",
                "docx",
            ]:
                messages.error(
                    request,
                    "Schemes accept PDF, DOC or DOCX only.",
                )
                return redirect(
                    "professional_documents:create"
                )

            content = ""

        elif document_type == ProfessionalDocument.TYPE_RECORD:

            uploaded_file = None

            if not content:
                messages.error(
                    request,
                    "Enter the work covered.",
                )
                return redirect(
                    "professional_documents:create"
                )

        elif document_type == ProfessionalDocument.TYPE_LESSON:

            if not content and not uploaded_file:
                messages.error(
                    request,
                    "Type the lesson plan or upload "
                    "a PDF/Word lesson plan.",
                )
                return redirect(
                    "professional_documents:create"
                )

            if uploaded_file:

                extension = (
                    uploaded_file.name
                    .rsplit(".", 1)[-1]
                    .lower()
                )

                if extension not in [
                    "pdf",
                    "doc",
                    "docx",
                ]:
                    messages.error(
                        request,
                        "Lesson plans accept PDF, DOC "
                        "or DOCX only.",
                    )
                    return redirect(
                        "professional_documents:create"
                    )

        document = ProfessionalDocument.objects.create(
            academic_year=year,
            term=term,
            document_type=document_type,
            teacher=teacher,
            class_name=class_name,
            stream=stream,
            subject=subject,
            lesson_date=lesson_date or None,
            start_time=start_time or None,
            end_time=end_time or None,
            from_date=from_date or None,
            to_date=to_date or None,
            title=title,
            content=content,
            uploaded_file=uploaded_file,
            status=ProfessionalDocument.STATUS_DRAFT,
        )

        messages.success(
            request,
            "Professional document saved as draft.",
        )

        return redirect(
            "professional_documents:detail",
            pk=document.pk,
        )

    context = {
        "assignments": assignments,
        **_admin_context(),
        "document_types": ProfessionalDocument.DOCUMENT_TYPES,
    }

    return render(
        request,
        "professional_documents/document_form.html",
        context,
    )


@login_required
def document_detail(request, pk):

    document = get_object_or_404(
        ProfessionalDocument.objects.select_related(
            "academic_year",
            "term",
            "subject",
            "teacher",
            "reviewed_by",
        ),
        pk=pk,
    )

    if not _is_admin(request.user):

        if not (
            _is_staff(request.user)
            and document.teacher_id == request.user.id
        ):
            return HttpResponseForbidden(
                "You cannot view this document."
            )

    return render(
        request,
        "professional_documents/document_detail.html",
        {
            "document": document,
            "is_admin": _is_admin(request.user),
        },
    )


@login_required
def document_edit(request, pk):

    document = get_object_or_404(
        ProfessionalDocument,
        pk=pk,
    )

    if not _is_staff(request.user):
        return HttpResponseForbidden(
            "Teaching staff access required."
        )

    if document.teacher_id != request.user.id:
        return HttpResponseForbidden(
            "You cannot edit this document."
        )

    if not document.is_editable_by_teacher:
        return HttpResponseForbidden(
            "This document can no longer be edited."
        )

    if request.method == "POST":

        content = request.POST.get(
            "content",
            "",
        ).strip()

        title = request.POST.get(
            "title",
            "",
        ).strip()

        uploaded_file = request.FILES.get(
            "uploaded_file"
        )

        if document.document_type == ProfessionalDocument.TYPE_RECORD:

            if not content:
                messages.error(
                    request,
                    "Enter the work covered.",
                )
                return redirect(
                    "professional_documents:edit",
                    pk=pk,
                )

            document.content = content

        elif document.document_type == ProfessionalDocument.TYPE_SCHEME:

            if uploaded_file:
                extension = (
                    uploaded_file.name
                    .rsplit(".", 1)[-1]
                    .lower()
                )

                if extension not in [
                    "pdf",
                    "doc",
                    "docx",
                ]:
                    messages.error(
                        request,
                        "Upload PDF, DOC or DOCX only.",
                    )
                    return redirect(
                        "professional_documents:edit",
                        pk=pk,
                    )

                document.uploaded_file = uploaded_file

        else:

            if uploaded_file:
                extension = (
                    uploaded_file.name
                    .rsplit(".", 1)[-1]
                    .lower()
                )

                if extension not in [
                    "pdf",
                    "doc",
                    "docx",
                ]:
                    messages.error(
                        request,
                        "Upload PDF, DOC or DOCX only.",
                    )
                    return redirect(
                        "professional_documents:edit",
                        pk=pk,
                    )

                document.uploaded_file = uploaded_file

            document.content = content

        document.title = title
        document.status = ProfessionalDocument.STATUS_DRAFT
        document.save()

        messages.success(
            request,
            "Document updated.",
        )

        return redirect(
            "professional_documents:detail",
            pk=pk,
        )

    return render(
        request,
        "professional_documents/document_edit.html",
        {
            "document": document,
        },
    )


@login_required
def document_submit(request, pk):

    document = get_object_or_404(
        ProfessionalDocument,
        pk=pk,
    )

    if not _is_staff(request.user):
        return HttpResponseForbidden(
            "Teaching staff access required."
        )

    if document.teacher_id != request.user.id:
        return HttpResponseForbidden(
            "You cannot submit this document."
        )

    if document.status not in [
        ProfessionalDocument.STATUS_DRAFT,
        ProfessionalDocument.STATUS_FLAGGED,
    ]:
        return HttpResponseForbidden(
            "This document cannot be submitted."
        )

    document.status = ProfessionalDocument.STATUS_SUBMITTED
    document.submitted_at = timezone.now()
    document.save(
        update_fields=[
            "status",
            "submitted_at",
            "updated_at",
        ]
    )

    messages.success(
        request,
        "Document submitted to Admin for review.",
    )

    return redirect(
        "professional_documents:detail",
        pk=pk,
    )


@login_required
def document_review(request, pk):

    if not _is_admin(request.user):
        return HttpResponseForbidden(
            "Administrator access required."
        )

    document = get_object_or_404(
        ProfessionalDocument,
        pk=pk,
    )

    if request.method != "POST":
        return redirect(
            "professional_documents:detail",
            pk=pk,
        )

    action = request.POST.get(
        "action",
        "",
    )

    remarks = request.POST.get(
        "admin_remarks",
        "",
    ).strip()

    if action == "approve":

        document.status = (
            ProfessionalDocument.STATUS_APPROVED
        )

    elif action == "flag":

        document.status = (
            ProfessionalDocument.STATUS_FLAGGED
        )

    else:

        messages.error(
            request,
            "Invalid review action.",
        )

        return redirect(
            "professional_documents:detail",
            pk=pk,
        )

    document.admin_remarks = remarks
    document.reviewed_by = request.user
    document.reviewed_at = timezone.now()

    document.save()

    messages.success(
        request,
        "Document review saved.",
    )

    return redirect(
        "professional_documents:detail",
        pk=pk,
    )


