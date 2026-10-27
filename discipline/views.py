from django.contrib import messages
from django.views.decorators.http import require_POST
from parents.models import Parent
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import PermissionDenied
from django.db.models import Q, Count
from django.shortcuts import get_object_or_404, redirect, render
from django.http import FileResponse
from pathlib import Path
from django.utils import timezone
from .models import *
from .forms import *

def can_manage(user):
    return user.is_authenticated and (user.is_superuser or user.is_staff or user.groups.filter(name__in=["Discipline Admin","Principal","Disciplinary Officer"]).exists())

def _audit(request, case, action, details=""):
    DisciplineAuditLog.objects.create(case=case, actor=request.user, action=action, details=details)

def _parent_can_access(user, case):
    if not case.student_id:
        return False
    return Parent.objects.filter(user=user, children__id=case.student_id).exists()

def _linked_student(user):
    """
    Return the Student explicitly linked to this login, if one exists.
    Never infer a student's identity from a username or display name.
    """
    try:
        profile = user.profile
        return profile.student
    except (AttributeError, TypeError):
        return None


def _parent_can_access(user, case):
    if not case.student_id:
        return False
    return Parent.objects.filter(
        user=user,
        children__id=case.student_id,
    ).exists()


def _case_access(request, case):
    user = request.user
    linked_student = _linked_student(user)

    if (
        can_manage(user)
        or case.reporter_id == user.id
        or case.assigned_officer_id == user.id
        or _parent_can_access(user, case)
        or (
            linked_student is not None
            and case.student_id == linked_student.pk
        )
    ):
        return

    raise PermissionDenied


def _visible_cases(user):
    qs = DisciplineCase.objects.all()

    # Preserve existing manager access and existing permission behavior.
    if can_manage(user):
        return qs

    conditions = Q(reporter=user) | Q(assigned_officer=user)

    parent_student_ids = Parent.objects.filter(
        user=user
    ).values_list("children__id", flat=True)
    conditions |= Q(student_id__in=parent_student_ids)

    linked_student = _linked_student(user)
    if linked_student is not None:
        conditions |= Q(student_id=linked_student.pk)

    return qs.filter(conditions).distinct()


@login_required
def dashboard(request):
    user = request.user
    cases = _visible_cases(user)
    is_manager = can_manage(user)

    try:
        role = user.profile.role
    except (AttributeError, TypeError):
        role = ""

    # Use the configured ERP portal role for the dashboard presentation.
    # Existing manager permissions remain controlled by can_manage().
    if user.is_superuser or role == "ADMIN":
        role_key = "admin"
        role_label = "Administration"
        page_title = "Discipline Administration"
        page_description = (
            "Review discipline activity, oversee case progress, "
            "and access management tools."
        )
    elif role == "STUDENT":
        role_key = "student"
        role_label = "Student"
        page_title = "My Discipline Portal"
        page_description = (
            "View cases linked to your student account and follow up "
            "on matters you are authorised to access."
        )
    elif role == "PARENT":
        role_key = "parent"
        role_label = "Parent / Guardian"
        page_title = "Parent Discipline Portal"
        page_description = (
            "Follow up on discipline matters involving your linked children."
        )
    else:
        role_key = "staff"
        role_label = "Staff"
        page_title = "Staff Discipline Portal"
        page_description = (
            "Report incidents and follow up on cases available to your account."
        )

    stats = {
        "total": cases.count(),
        "open": cases.exclude(status="closed").count(),
        "urgent": cases.filter(urgent=True).exclude(status="closed").count(),
        "pending": cases.filter(
            status__in=["submitted", "under_review", "awaiting_decision"]
        ).count(),
    }

    latest = cases.select_related(
        "category", "student", "reporter", "assigned_officer"
    ).order_by("-created_at")[:8]

    return render(request, "discipline/dashboard.html", {
        "stats": stats,
        "cases": latest,
        "is_manager": is_manager,
        "portal_role": role_key,
        "portal_role_label": role_label,
        "page_title": page_title,
        "page_description": page_description,
        "can_report_incident": True,
    })


@login_required
def case_list(request):
    qs = _visible_cases(request.user).select_related("category","reporter","assigned_officer","student")
    q = request.GET.get("q","").strip()
    status = request.GET.get("status","")
    if q:
        qs = qs.filter(Q(case_number__icontains=q)|Q(student_name__icontains=q)|Q(student_admission_no__icontains=q)|Q(description__icontains=q))
    if status: qs = qs.filter(status=status)
    return render(request,"discipline/case_list.html",{"cases":qs,"q":q,"status":status,"statuses":DisciplineCase.STATUS_CHOICES})

@login_required
def case_create(request):
    if request.method == "POST":
        form = CaseReportForm(request.POST, request.FILES)
        if form.is_valid():
            case = form.save(commit=False)
            case.reporter = request.user
            case.status = "submitted"
            case.save()
            DisciplineIncidentReport.objects.create(
                case=case,
                submitted_by=request.user,
                factual_account=case.description,
                immediate_safety_concern=case.urgent,
                attachments=form.cleaned_data.get("attachments"),
            )
            _audit(request,case,"case_submitted","Initial incident report submitted.")
            messages.success(request, f"Incident report submitted. Reference: {case.case_number}")
            return redirect("discipline:case_detail", pk=case.pk)
    else: form = CaseReportForm()
    return render(request,"discipline/form.html",{"form":form,"title":"Report a disciplinary incident"})

@login_required
def case_detail(request, pk):
    case = get_object_or_404(DisciplineCase.objects.select_related("category", "reporter", "assigned_officer", "student"), pk=pk)
    _case_access(request, case)
    is_manager = can_manage(request.user)

    # Internal deliberations and operational records are manager-only. A linked
    # parent or other permitted viewer sees only their own non-confidential statement.
    if is_manager:
        statements = case.statements.select_related("author").all()
        meetings = case.meetings.all()
        actions = case.actions.select_related("assigned_to").all()
        decisions = case.decisions.select_related("approved_by").all()
        improvement_plans = case.improvement_plans.all()
        appeals = case.appeals.all()
    else:
        statements = case.statements.filter(author=request.user, confidential=False)
        meetings = []
        actions = []
        decisions = []
        improvement_plans = []
        appeals = []

    reports = case.reports.all() if is_manager else []
    return render(request, "discipline/case_detail.html", {
        "case": case,
        "is_manager": is_manager,
        "statements": statements,
        "meetings": meetings,
        "actions": actions,
        "decisions": decisions,
        "improvement_plans": improvement_plans,
        "appeals": appeals,
        "reports": reports,
    })

@login_required
@user_passes_test(can_manage)
def case_update(request, pk):
    case = get_object_or_404(DisciplineCase,pk=pk)
    if request.method == "POST":
        form = CaseReportForm(request.POST,instance=case)
        if form.is_valid():
            obj=form.save()
            _audit(request,obj,"case_updated","Case details updated.")
            messages.success(request,"Case updated.")
            return redirect("discipline:case_detail",pk=obj.pk)
    else: form=CaseReportForm(instance=case)
    return render(request,"discipline/form.html",{"form":form,"title":f"Update {case.case_number}"})

@require_POST
@login_required
@user_passes_test(can_manage)
def case_status(request, pk, status):
    case=get_object_or_404(DisciplineCase,pk=pk)
    allowed=dict(DisciplineCase.STATUS_CHOICES)
    if status not in allowed: raise PermissionDenied
    case.status = status
    if status == "closed":
        case.closed_at = timezone.now()
    else:
        # A case cannot retain a closed timestamp after it is moved back
        # into an active workflow state.
        case.closed_at = None
    case.save()
    _audit(request,case,"status_changed",f"Status changed to {allowed[status]}.")
    messages.success(request,f"Case status changed to {allowed[status]}.")
    return redirect("discipline:case_detail",pk=case.pk)

@login_required
@user_passes_test(can_manage)
def add_statement(request, pk):
    case=get_object_or_404(DisciplineCase,pk=pk)
    if request.method=="POST":
        form=StatementForm(request.POST)
        if form.is_valid():
            obj=form.save(commit=False); obj.case=case; obj.author=request.user; obj.save()
            _audit(request,case,"statement_added",obj.get_statement_type_display())
            messages.success(request,"Statement saved.")
            return redirect("discipline:case_detail",pk=pk)
    else: form=StatementForm()
    return render(request,"discipline/form.html",{"form":form,"title":f"Add statement — {case.case_number}"})

@login_required
@user_passes_test(can_manage)
def add_meeting(request, pk):
    case=get_object_or_404(DisciplineCase,pk=pk)
    if request.method=="POST":
        form=MeetingForm(request.POST)
        if form.is_valid():
            obj=form.save(commit=False); obj.case=case; obj.created_by=request.user; obj.save()
            _audit(request,case,"meeting_scheduled",obj.title)
            messages.success(request,"Meeting scheduled.")
            return redirect("discipline:case_detail",pk=pk)
    else: form=MeetingForm()
    return render(request,"discipline/form.html",{"form":form,"title":f"Schedule meeting — {case.case_number}"})

@login_required
@user_passes_test(can_manage)
def add_decision(request, pk):
    case=get_object_or_404(DisciplineCase,pk=pk)
    if request.method=="POST":
        form=DecisionForm(request.POST)
        if form.is_valid():
            obj=form.save(commit=False); obj.case=case; obj.approved_by=request.user; obj.save()
            case.findings=case.findings or obj.reasons
            case.decision_reason=obj.reasons; case.decision_maker=request.user; case.decision_date=timezone.localdate()
            case.status="action_in_progress"; case.save()
            _audit(request,case,"decision_recorded",obj.get_outcome_display())
            messages.success(request,"Decision recorded and case moved to action in progress.")
            return redirect("discipline:case_detail",pk=pk)
    else: form=DecisionForm()
    return render(request,"discipline/form.html",{"form":form,"title":f"Record decision — {case.case_number}"})

@login_required
@user_passes_test(can_manage)
def add_action(request, pk):
    case=get_object_or_404(DisciplineCase,pk=pk)
    if request.method=="POST":
        form=ActionForm(request.POST)
        if form.is_valid():
            obj=form.save(commit=False); obj.case=case; obj.save()
            _audit(request,case,"action_added",obj.title)
            messages.success(request,"Action added.")
            return redirect("discipline:case_detail",pk=pk)
    else: form=ActionForm()
    return render(request,"discipline/form.html",{"form":form,"title":f"Add action — {case.case_number}"})

@login_required
@user_passes_test(can_manage)
def add_improvement_plan(request, pk):
    case=get_object_or_404(DisciplineCase,pk=pk)
    if request.method=="POST":
        form=ImprovementPlanForm(request.POST)
        if form.is_valid():
            obj=form.save(commit=False); obj.case=case; obj.save()
            _audit(request,case,"improvement_plan_added",obj.title)
            messages.success(request,"Improvement plan saved.")
            return redirect("discipline:case_detail",pk=pk)
    else: form=ImprovementPlanForm()
    return render(request,"discipline/form.html",{"form":form,"title":f"Improvement plan — {case.case_number}"})

@login_required
def my_cases(request):
    # Until ERP identity mapping is linked, parent/student identity cannot be inferred safely.
    # This route intentionally shows only records explicitly tied to the logged-in reporter/assignee.
    qs=_visible_cases(request.user)
    return render(request,"discipline/case_list.html",{"cases":qs,"q":"","status":"","statuses":DisciplineCase.STATUS_CHOICES,"portal_mode":"personal"})

@login_required
def submit_response(request, pk):
    case=get_object_or_404(DisciplineCase,pk=pk)
    # Access is restricted to the case reporter/assignee or managers until child/user mapping is integrated.
    _case_access(request,case)
    # Do not trust a role sent by the browser. Student accounts are not mapped
    # to Student records in this ERP, so only a verified linked parent may
    # submit a parent response; other permitted users are recorded as staff.
    response_role = "parent" if _parent_can_access(request.user, case) else "staff"
    if request.method == "POST":
        response = request.POST.get("response", "").strip()
        if response:
            author_name = request.user.get_full_name() or request.user.get_username()
            DisciplineStatement.objects.create(
                case=case,
                author=request.user,
                author_name=author_name,
                statement_type=response_role,
                body=response,
            )
            _audit(request, case, "response_submitted", f"{response_role} response submitted.")
            messages.success(request, "Your response has been recorded.")
            return redirect("discipline:case_detail", pk=pk)
    return render(request, "discipline/response_form.html", {
        "case": case,
        "response_role_label": "Parent / Guardian" if response_role == "parent" else "Staff",
    })

@login_required
def submit_appeal(request, pk):
    case = get_object_or_404(DisciplineCase, pk=pk)
    _case_access(request, case)
    if request.method == "POST":
        form = AppealForm(request.POST)
        if form.is_valid():
            appeal = form.save(commit=False)
            appeal.case = case
            appeal.requested_by_name = request.user.get_full_name() or request.user.get_username()
            # Derive the role from server-side relationships, never from posted form data.
            appeal.requester_role = "parent" if _parent_can_access(request.user, case) else "staff"
            appeal.save()
            previous_status = case.status
            case.status = "appeal"
            case.closed_at = None
            case.save(update_fields=["status", "closed_at", "updated_at"])
            _audit(
                request,
                case,
                "appeal_submitted",
                f"Appeal submitted by {appeal.requested_by_name}; prior status: {previous_status}.",
            )
            messages.success(request, "Appeal submitted for review.")
            return redirect("discipline:case_detail", pk=case.pk)
    else:
        form = AppealForm()
    return render(request, "discipline/form.html", {"form": form, "title": f"Submit appeal — {case.case_number}"})

@login_required
@user_passes_test(can_manage)
def review_appeal(request, pk, appeal_pk):
    case = get_object_or_404(DisciplineCase, pk=pk)
    appeal = get_object_or_404(DisciplineAppeal, pk=appeal_pk, case=case)
    if request.method == "POST":
        form = AppealReviewForm(request.POST, instance=appeal)
        if form.is_valid():
            reviewed = form.save(commit=False)
            reviewed.reviewed_by = request.user
            reviewed.reviewed_at = timezone.now()
            reviewed.save()
            _audit(request, case, "appeal_reviewed", f"Appeal {reviewed.pk} updated to {reviewed.get_status_display()}.")
            messages.success(request, "Appeal review saved.")
            return redirect("discipline:case_detail", pk=case.pk)
    else:
        form = AppealReviewForm(instance=appeal)
    return render(request, "discipline/form.html", {
        "form": form,
        "title": f"Review appeal — {case.case_number}",
    })


@login_required
@user_passes_test(can_manage)
def reports(request):
    qs=DisciplineCase.objects.all()
    categories=DisciplineCase.objects.values("category__name").annotate(total=Count("id")).order_by("-total")
    statuses=DisciplineCase.objects.values("status").annotate(total=Count("id")).order_by("-total")
    return render(request,"discipline/reports.html",{"total":qs.count(),"open":qs.exclude(status="closed").count(),"closed":qs.filter(status="closed").count(),"categories":categories,"statuses":statuses})

@login_required
@user_passes_test(can_manage)
def audit_log(request, pk):
    case=get_object_or_404(DisciplineCase,pk=pk)
    return render(request,"discipline/audit_log.html",{"case":case,"logs":case.audit_logs.select_related("actor")})


@login_required
@user_passes_test(can_manage)
def download_evidence(request, pk, report_pk):
    case = get_object_or_404(DisciplineCase, pk=pk)
    report = get_object_or_404(DisciplineIncidentReport, pk=report_pk, case=case)
    if not report.attachments:
        from django.http import Http404
        raise Http404("No evidence file is attached to this report.")

    try:
        file_handle = report.attachments.open("rb")
    except (FileNotFoundError, OSError):
        from django.http import Http404
        raise Http404("The evidence file is unavailable.")

    _audit(request, case, "evidence_downloaded", Path(report.attachments.name).name)
    return FileResponse(
        file_handle,
        as_attachment=True,
        filename=Path(report.attachments.name).name,
    )
