from io import BytesIO

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Avg, Count
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import render
from django.urls import reverse

from academic.models import Assessment, AssessmentType, Stream
from fees.models import AcademicYear, Term
from students.models import Student
from accounts.staff_access import can_view_class


def _pdf_is_admin(user):
    if user.is_superuser or user.is_staff:
        return True

    profile = getattr(user, "profile", None)
    return getattr(profile, "role", "") == "ADMIN"


def _pdf_student_stream(student):
    value = getattr(student, "stream", None)
    if value is None:
        return ""
    return str(getattr(value, "name", value)).strip()


def _pdf_selection_context():
    active_students = Student.objects.filter(is_active=True)

    classes = sorted({
        str(value).strip()
        for value in active_students.values_list("class_name", flat=True)
        if value and str(value).strip()
    })

    streams = Stream.objects.filter(is_active=True).order_by("name")
    years = AcademicYear.objects.all().order_by("-id")
    terms = Term.objects.select_related("academic_year").all().order_by(
        "-academic_year_id", "order", "name"
    )
    assessment_types = AssessmentType.objects.filter(
        is_active=True
    ).order_by("order", "name")

    return {
        "classes": classes,
        "streams": streams,
        "years": years,
        "terms": terms,
        "assessment_types": assessment_types,
    }


@login_required
def performance_pdf_center(request):
    if request.method == "POST":
        return HttpResponseBadRequest(
            "Use the PDF download form's GET request."
        )

    context = _pdf_selection_context()
    context["is_admin"] = _pdf_is_admin(request.user)
    return render(
        request,
        "academic/performance_pdf_center.html",
        context,
    )


@login_required
def performance_comparison_pdf(request):
    if request.method != "GET":
        return HttpResponseBadRequest("Use GET to generate this report.")

    params = request.GET
    scope = params.get("scope", "class").strip().lower()
    class_name = params.get("class_name", "").strip()
    stream_name = params.get("stream_name", "").strip()

    required_ids = (
        "current_year", "current_term", "current_type",
        "compare_year", "compare_term", "compare_type",
    )
    if any(not params.get(key, "").isdigit() for key in required_ids):
        return HttpResponseBadRequest(
            "Select both academic years, terms and assessment types."
        )

    if scope not in {"class", "school"}:
        return HttpResponseBadRequest("Invalid report scope.")

    is_admin = _pdf_is_admin(request.user)

    if scope == "school" and not is_admin:
        raise PermissionDenied(
            "Only administrators may generate whole-school reports."
        )

    if scope == "class":
        if not class_name:
            return HttpResponseBadRequest("Select a class.")

        if not is_admin and not stream_name:
            return HttpResponseBadRequest(
                "Staff must select a specific stream."
            )

        if not is_admin and not can_view_class(
            request.user, class_name, stream_name
        ):
            raise PermissionDenied(
                "You do not have access to this class and stream."
            )

    try:
        current_year = AcademicYear.objects.get(
            pk=int(params["current_year"])
        )
        current_term = Term.objects.get(
            pk=int(params["current_term"]),
            academic_year_id=current_year.pk,
        )
        current_type = AssessmentType.objects.get(
            pk=int(params["current_type"]), is_active=True
        )

        compare_year = AcademicYear.objects.get(
            pk=int(params["compare_year"])
        )
        compare_term = Term.objects.get(
            pk=int(params["compare_term"]),
            academic_year_id=compare_year.pk,
        )
        compare_type = AssessmentType.objects.get(
            pk=int(params["compare_type"]), is_active=True
        )
    except (AcademicYear.DoesNotExist, Term.DoesNotExist,
            AssessmentType.DoesNotExist, ValueError, TypeError):
        return HttpResponseBadRequest(
            "One or more selections are invalid. Check each year, term "
            "and active assessment type."
        )

    active_students = list(
        Student.objects.filter(is_active=True).order_by(
            "class_name", "id"
        )
    )

    if scope == "class":
        active_students = [
            student for student in active_students
            if str(getattr(student, "class_name", "") or "").strip()
            == class_name
        ]

        if stream_name and stream_name != "__ALL__":
            active_students = [
                student for student in active_students
                if _pdf_student_stream(student) == stream_name
            ]

    student_ids = [student.pk for student in active_students]

    def get_assessments(year, term, assessment_type):
        return Assessment.objects.filter(
            student_id__in=student_ids,
            academic_year_id=year.pk,
            term_id=term.pk,
            assessment_type_id=assessment_type.pk,
        ).select_related("subject", "student")

    current_assessments = get_assessments(
        current_year, current_term, current_type
    )
    comparison_assessments = get_assessments(
        compare_year, compare_term, compare_type
    )

    current_overall = current_assessments.aggregate(
        average=Avg("score"),
        learners=Count("student", distinct=True),
    )
    comparison_overall = comparison_assessments.aggregate(
        average=Avg("score"),
        learners=Count("student", distinct=True),
    )

    current_subjects = {
        row["subject_id"]: row
        for row in current_assessments.values(
            "subject_id", "subject__name"
        ).annotate(
            average=Avg("score"),
            learners=Count("student", distinct=True),
        )
    }

    comparison_subjects = {
        row["subject_id"]: row
        for row in comparison_assessments.values(
            "subject_id", "subject__name"
        ).annotate(
            average=Avg("score"),
            learners=Count("student", distinct=True),
        )
    }

    subject_ids = set(current_subjects) | set(comparison_subjects)
    subject_rows = []

    for subject_id in sorted(
        subject_ids,
        key=lambda sid: (
            current_subjects.get(sid, {}).get("subject__name")
            or comparison_subjects.get(sid, {}).get("subject__name")
            or ""
        ).lower(),
    ):
        current = current_subjects.get(subject_id, {})
        previous = comparison_subjects.get(subject_id, {})

        current_avg = current.get("average")
        compare_avg = previous.get("average")
        difference = (
            current_avg - compare_avg
            if current_avg is not None and compare_avg is not None
            else None
        )

        subject_name = (
            current.get("subject__name")
            or previous.get("subject__name")
            or "Subject"
        )

        subject_rows.append({
            "name": subject_name,
            "current": current_avg,
            "comparison": compare_avg,
            "difference": difference,
            "current_learners": current.get("learners", 0),
            "comparison_learners": previous.get("learners", 0),
        })

    current_avg = current_overall["average"]
    comparison_avg = comparison_overall["average"]
    overall_difference = (
        current_avg - comparison_avg
        if current_avg is not None and comparison_avg is not None
        else None
    )

    # Build the PDF with ReportLab. Narrow margins maximise usable space.
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        PageBreak, KeepTogether,
    )

    buffer = BytesIO()
    page_size = landscape(A4)

    doc = SimpleDocTemplate(
        buffer,
        pagesize=page_size,
        rightMargin=10 * mm,
        leftMargin=10 * mm,
        topMargin=12 * mm,
        bottomMargin=13 * mm,
        title="Academic Performance Comparison",
        author="School ERP",
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="ReportTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#183153"),
        spaceAfter=4 * mm,
    ))
    styles.add(ParagraphStyle(
        name="ReportSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#4B5563"),
        spaceAfter=5 * mm,
    ))
    styles.add(ParagraphStyle(
        name="SectionHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#183153"),
        spaceBefore=4 * mm,
        spaceAfter=2 * mm,
        keepWithNext=True,
    ))
    styles.add(ParagraphStyle(
        name="SmallCell",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8,
        leading=10,
        alignment=TA_LEFT,
    ))
    styles.add(ParagraphStyle(
        name="SmallCellRight",
        parent=styles["SmallCell"],
        alignment=TA_RIGHT,
    ))

    def fmt(value):
        return "—" if value is None else f"{value:.2f}%"

    def diff_fmt(value):
        if value is None:
            return "—"
        return f"{value:+.2f} pp"

    story = []
    story.append(Paragraph(
        "ACADEMIC PERFORMANCE COMPARISON", styles["ReportTitle"]
    ))

    scope_label = (
        "Whole School"
        if scope == "school"
        else f"{class_name} — "
             f"{'All Streams' if stream_name == '__ALL__' else stream_name or 'Unspecified Stream'}"
    )
    story.append(Paragraph(
        f"{scope_label} &nbsp; | &nbsp; Generated "
        f"{__import__('datetime').date.today().strftime('%d %B %Y')}",
        styles["ReportSubtitle"],
    ))

    current_label = (
        f"{current_year} / {current_term.name} / {current_type.name}"
    )
    comparison_label = (
        f"{compare_year} / {compare_term.name} / {compare_type.name}"
    )

    metadata = [
        [
            Paragraph("<b>Selected assessment</b>", styles["SmallCell"]),
            Paragraph("<b>Comparison assessment</b>", styles["SmallCell"]),
        ],
        [
            Paragraph(current_label, styles["SmallCell"]),
            Paragraph(comparison_label, styles["SmallCell"]),
        ],
    ]
    metadata_table = Table(
        metadata, colWidths=[doc.width / 2, doc.width / 2]
    )
    metadata_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EEF6")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCD5E0")),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CCD5E0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.extend([metadata_table, Spacer(1, 4 * mm)])

    story.append(Paragraph("Overall Performance", styles["SectionHeading"]))
    overall_data = [
        [
            Paragraph("<b>Measure</b>", styles["SmallCell"]),
            Paragraph("<b>Selected</b>", styles["SmallCell"]),
            Paragraph("<b>Comparison</b>", styles["SmallCell"]),
            Paragraph("<b>Difference</b>", styles["SmallCell"]),
        ],
        [
            Paragraph("Overall mean score", styles["SmallCell"]),
            Paragraph(fmt(current_avg), styles["SmallCellRight"]),
            Paragraph(fmt(comparison_avg), styles["SmallCellRight"]),
            Paragraph(diff_fmt(overall_difference), styles["SmallCellRight"]),
        ],
        [
            Paragraph("Learners with recorded marks", styles["SmallCell"]),
            Paragraph(str(current_overall["learners"] or 0), styles["SmallCellRight"]),
            Paragraph(str(comparison_overall["learners"] or 0), styles["SmallCellRight"]),
            Paragraph("—", styles["SmallCellRight"]),
        ],
    ]

    overall_table = Table(
        overall_data,
        colWidths=[
            doc.width * 0.40,
            doc.width * 0.20,
            doc.width * 0.20,
            doc.width * 0.20,
        ],
        repeatRows=1,
    )
    overall_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#183153")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
            colors.white, colors.HexColor("#F5F7FA")
        ]),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D5DCE5")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.extend([overall_table, Spacer(1, 3 * mm)])

    story.append(Paragraph(
        "Subject-by-Subject Comparison", styles["SectionHeading"]
    ))

    subject_data = [[
        Paragraph("<b>Learning Area</b>", styles["SmallCell"]),
        Paragraph("<b>Selected Mean</b>", styles["SmallCell"]),
        Paragraph("<b>Comparison Mean</b>", styles["SmallCell"]),
        Paragraph("<b>Difference</b>", styles["SmallCell"]),
        Paragraph("<b>Selected Learners</b>", styles["SmallCell"]),
        Paragraph("<b>Comparison Learners</b>", styles["SmallCell"]),
    ]]

    for row in subject_rows:
        subject_data.append([
            Paragraph(str(row["name"]).replace("&", "&amp;"), styles["SmallCell"]),
            Paragraph(fmt(row["current"]), styles["SmallCellRight"]),
            Paragraph(fmt(row["comparison"]), styles["SmallCellRight"]),
            Paragraph(diff_fmt(row["difference"]), styles["SmallCellRight"]),
            Paragraph(str(row["current_learners"]), styles["SmallCellRight"]),
            Paragraph(str(row["comparison_learners"]), styles["SmallCellRight"]),
        ])

    if not subject_rows:
        subject_data.append([
            Paragraph(
                "No assessment records match the selected filters.",
                styles["SmallCell"],
            ),
            "", "", "", "", "",
        ])

    subject_table = Table(
        subject_data,
        colWidths=[
            doc.width * 0.34,
            doc.width * 0.14,
            doc.width * 0.14,
            doc.width * 0.13,
            doc.width * 0.125,
            doc.width * 0.125,
        ],
        repeatRows=1,
        hAlign="LEFT",
    )
    subject_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#183153")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
            colors.white, colors.HexColor("#F5F7FA")
        ]),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D5DCE5")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(subject_table)

    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(
        "<b>Note:</b> Difference is the selected mean minus the comparison "
        "mean, expressed in percentage points (pp). A dash means the "
        "comparison is unavailable because no matching marks were recorded.",
        styles["SmallCell"],
    ))

    def draw_footer(canvas, document):
        canvas.saveState()
        width, _height = document.pagesize
        canvas.setStrokeColor(colors.HexColor("#D5DCE5"))
        canvas.setLineWidth(0.5)
        canvas.line(
            document.leftMargin, 9 * mm,
            width - document.rightMargin, 9 * mm
        )
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#596579"))
        canvas.drawString(
            document.leftMargin, 5 * mm,
            "Academic Performance Report"
        )
        canvas.drawRightString(
            width - document.rightMargin, 5 * mm,
            f"Page {document.page}"
        )
        canvas.restoreState()

    doc.build(
        story,
        onFirstPage=draw_footer,
        onLaterPages=draw_footer,
    )

    pdf = buffer.getvalue()
    buffer.close()

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = (
        'attachment; filename="academic_performance_comparison.pdf"'
    )
    return response
