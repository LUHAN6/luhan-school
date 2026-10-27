from datetime import date, timedelta

from accounts.models import SchoolBranding

from django.contrib import messages
from accounts.models import SchoolBranding

from django.contrib.auth.decorators import login_required
from accounts.models import SchoolBranding

from django.db.models import Q, Count
from accounts.models import SchoolBranding

from django.shortcuts import get_object_or_404, redirect, render

from students.models import Student
from hr_payroll.models import Employee

from .models import Category, Book, LibraryMember, BookIssue
from .forms import LibraryIssueCreateForm, LibraryIssueEditForm, BookIssueForm, BookForm, LibraryMemberLookupForm, LibraryMemberForm, CategoryForm, CategoryForm

# ============================================================
# MODEL FIELD HELPER
# ============================================================


def related_field(model, target_model):
    """
    Safely find a ForeignKey/OneToOne relation from model
    pointing to target_model.
    """
    try:
        for field in model._meta.get_fields():
            if getattr(field, "remote_field", None):
                related = getattr(field.remote_field, "model", None)
                if related == target_model:
                    return field.name
    except Exception:
        pass

    return None

def find_field(model, candidates):
    """
    Return the first field name from candidates that exists
    on the supplied Django model.
    """
    field_names = {
        field.name
        for field in model._meta.get_fields()
    }

    for candidate in candidates:
        if candidate in field_names:
            return candidate

    return None




# ============================================================
# ACCESS CONTROL
# ============================================================

def library_access_required(view_func):
    """
    Access control for the custom Library Management interface.

    Library is managed through /library/ and is deliberately
    independent of Django Admin.
    """

    def wrapper(request, *args, **kwargs):

        # Require a logged-in ERP user.
        if not request.user.is_authenticated:
            return redirect(
                "login"
            )
        # ----------------------------------------------------
        # ERP CUSTOM ROLE PERMISSION
        # ----------------------------------------------------
        # Module access is controlled by:
        # Admin Portal -> Custom Role -> Django Permission.
        #
        # Superuser and ERP ADMIN are allowed.
        # STAFF must have the exact Library module permission.
        # ----------------------------------------------------

        if request.user.is_superuser:
            return view_func(
                request,
                *args,
                **kwargs
            )

        profile = getattr(
            request.user,
            "profile",
            None
        )

        allowed = False

        if profile:

            role = str(
                getattr(
                    profile,
                    "role",
                    ""
                )
            ).upper()

            if role == "ADMIN":
                allowed = True

            else:

                custom_role = getattr(
                    profile,
                    "custom_role",
                    None
                )

                if (
                    custom_role
                    and custom_role.is_active
                    and custom_role.permissions.filter(
                        codename="view_librarymember",
                        content_type__app_label="library",
                    ).exists()
                ):
                    allowed = True

        # Never redirect Library users to the ERP root.
        # Return a clear HTTP response instead.
        if not allowed:

            from django.http import HttpResponse

            return HttpResponse(
                """
                <html>
                <head>
                    <title>Library Access</title>
                    <style>
                        body {
                            font-family: Arial, sans-serif;
                            background: #f4f7fb;
                            margin: 0;
                            padding: 60px;
                        }

                        .box {
                            max-width: 650px;
                            margin: auto;
                            background: white;
                            padding: 40px;
                            border-radius: 14px;
                            box-shadow: 0 10px 30px rgba(0,0,0,.08);
                            text-align: center;
                        }

                        h1 {
                            color: #123b82;
                        }

                        p {
                            color: #555;
                            line-height: 1.6;
                        }

                        a {
                            display: inline-block;
                            margin-top: 20px;
                            padding: 12px 22px;
                            background: #123b82;
                            color: white;
                            text-decoration: none;
                            border-radius: 8px;
                        }
                    </style>
                </head>

                <body>

                    <div class="box">

                        <h1>Library Management</h1>

                        <p>
                            Your account does not currently have
                            permission to access Library Management.
                        </p>

                        <a href="/admin-dashboard/">
                            Return to Dashboard
                        </a>

                    </div>

                </body>
                </html>
                """,
                status=403
            )

        return view_func(
            request,
            *args,
            **kwargs
        )

    wrapper.__name__ = view_func.__name__

    return wrapper

@library_access_required
def staff_members_print(request):

    from accounts.models import SchoolBranding

    q = request.GET.get("q", "").strip()

    staff = LibraryMember.objects.none()

    if q:

        staff = (
            LibraryMember.objects
            .filter(
                member_type="staff",
                employee__isnull=False,
            )
            .select_related("employee")
        )

        conditions = Q()

        for field in [
            "employee__first_name",
            "employee__last_name",
            "employee__employee_number",
            "phone",
            "email",
            "name",
        ]:
            conditions |= Q(**{
                f"{field}__icontains": q
            })

        staff = staff.filter(conditions)

        staff = staff.order_by(
            "employee__first_name",
            "employee__last_name",
        )

    branding = (
        SchoolBranding.objects
        .filter(is_active=True)
        .order_by("-pk")
        .first()
    )

    return render(
        request,
        "library/staff_members_print.html",
        {
            "staff": staff,
            "branding": branding,
            "q": q,
        }
    )

@library_access_required
def staff_members(request):

    q = request.GET.get("q", "").strip()

    staff = LibraryMember.objects.none()

    if q:

        staff = (
            LibraryMember.objects
            .filter(
                member_type="staff",
                employee__isnull=False,
            )
            .select_related("employee")
        )

        conditions = Q()

        for field in [
            "employee__first_name",
            "employee__last_name",
            "employee__employee_number",
            "phone",
            "email",
            "name",
        ]:
            conditions |= Q(**{
                f"{field}__icontains": q
            })

        staff = staff.filter(conditions)

        staff = staff.order_by(
            "employee__first_name",
            "employee__last_name",
        )

    return render(
        request,
        "library/staff_members.html",
        {
            "staff": staff,
            "q": q,
        }
    )

@library_access_required
def student_members_print(request):

    from accounts.models import SchoolBranding

    class_name = request.GET.get("class", "").strip()
    stream = request.GET.get("stream", "").strip()

    students = LibraryMember.objects.none()

    if class_name or stream:

        students = (
            LibraryMember.objects
            .filter(
                member_type="student",
                student__isnull=False,
            )
            .select_related("student")
        )

        if class_name:
            students = students.filter(
                student__class_name=class_name
            )

        if stream:
            students = students.filter(
                student__stream=stream
            )

        students = students.order_by(
            "student__class_name",
            "student__stream",
            "student__first_name",
            "student__last_name",
        )

    branding = (
        SchoolBranding.objects
        .filter(is_active=True)
        .order_by("-pk")
        .first()
    )

    return render(
        request,
        "library/student_members_print.html",
        {
            "students": students,
            "branding": branding,
            "class_name": class_name,
            "stream": stream,
        }
    )

@library_access_required
def student_members(request):

    class_name = request.GET.get("class", "").strip()
    stream = request.GET.get("stream", "").strip()

    students = LibraryMember.objects.none()

    filters_applied = bool(class_name or stream)

    if filters_applied:

        students = (
            LibraryMember.objects
            .filter(
                member_type="student",
                student__isnull=False,
            )
            .select_related("student")
        )

        if class_name:
            students = students.filter(
                student__class_name=class_name
            )

        if stream:
            students = students.filter(
                student__stream=stream
            )

        students = students.order_by(
            "student__class_name",
            "student__stream",
            "student__first_name",
            "student__last_name",
        )

    class_options = (
        LibraryMember.objects
        .filter(
            member_type="student",
            student__isnull=False,
        )
        .values_list(
            "student__class_name",
            flat=True,
        )
        .distinct()
        .order_by("student__class_name")
    )

    stream_options = (
        LibraryMember.objects
        .filter(
            member_type="student",
            student__isnull=False,
        )
        .exclude(
            student__stream=""
        )
        .values_list(
            "student__stream",
            flat=True,
        )
        .distinct()
        .order_by("student__stream")
    )

    return render(
        request,
        "library/student_members.html",
        {
            "students": students,
            "class_name": class_name,
            "stream": stream,
            "class_options": class_options,
            "stream_options": stream_options,
            "filters_applied": filters_applied,
        }
    )

@library_access_required
def member_print(request):

    q = request.GET.get("q", "").strip()
    class_name = request.GET.get("class", "").strip()
    stream = request.GET.get("stream", "").strip()
    member_type = request.GET.get("member_type", "").strip()

    queryset = LibraryMember.objects.all()

    if q:
        queryset = queryset.filter(
            Q(name__icontains=q)
            | Q(admission_number__icontains=q)
            | Q(phone__icontains=q)
            | Q(email__icontains=q)
            | Q(student__first_name__icontains=q)
            | Q(student__middle_name__icontains=q)
            | Q(student__last_name__icontains=q)
            | Q(student__admission_no__icontains=q)
            | Q(employee__first_name__icontains=q)
            | Q(employee__last_name__icontains=q)
            | Q(employee__employee_number__icontains=q)
        )

    if class_name:
        queryset = queryset.filter(
            student__class_name=class_name
        )

    if stream:
        queryset = queryset.filter(
            student__stream=stream
        )

    if member_type:
        queryset = queryset.filter(
            member_type=member_type
        )

    queryset = queryset.select_related(
        "student",
        "employee",
    ).order_by("name")

    branding = (
        SchoolBranding.objects
        .filter(is_active=True)
        .order_by("-pk")
        .first()
    )

    if member_type == "staff":
        report_title = "LIBRARY STAFF MEMBERS"
    elif class_name and stream:
        report_title = f"LIBRARY MEMBERS — {class_name} — {stream}"
    elif class_name:
        report_title = f"LIBRARY MEMBERS — {class_name}"
    elif member_type == "student":
        report_title = "LIBRARY STUDENT MEMBERS"
    else:
        report_title = "LIBRARY MEMBERS REGISTER"

    return render(
        request,
        "library/member_print.html",
        {
            "members": queryset,
            "branding": branding,
            "report_title": report_title,
            "class_name": class_name,
            "stream": stream,
            "member_type": member_type,
            "q": q,
        }
    )

@library_access_required
def library_dashboard(request):

    books = Book.objects.all()
    categories = Category.objects.all()
    members = LibraryMember.objects.all()
    issues = BookIssue.objects.all()

    active_issue_field = find_field(
        BookIssue,
        ["returned", "is_returned", "return_date", "status"]
    )

    active_issues = 0
    overdue = 0

    today = date.today()

    for issue in issues:

        returned = False

        returned_field = find_field(
            BookIssue,
            ["returned", "is_returned"]
        )

        if returned_field:
            returned = bool(getattr(issue, returned_field, False))

        return_date_field = find_field(
            BookIssue,
            ["return_date", "returned_at", "date_returned"]
        )

        if return_date_field and getattr(issue, return_date_field, None):
            returned = True

        if not returned:
            active_issues += 1

        due_field = find_field(
            BookIssue,
            ["due_date", "return_due", "expected_return_date"]
        )

        if due_field:
            due = getattr(issue, due_field, None)

            if due and not returned and due < today:
                overdue += 1

    context = {
        "books_count": books.count(),
        "categories_count": categories.count(),
        "members_count": members.count(),
        "issues_count": issues.count(),
        "active_issues": active_issues,
        "overdue_count": overdue,
        "recent_books": books.order_by("-pk")[:8],
        "recent_issues": issues.order_by("-pk")[:8],
    }

    return render(
        request,
        "library/dashboard.html",
        context
    )


# ============================================================
# BOOKS
# ============================================================

@library_access_required
def books(request):

    q = request.GET.get("q", "").strip()
    category = request.GET.get("category", "").strip()

    # Do not display books until a search/filter is requested.
    queryset = Book.objects.none()

    if q or category:

        queryset = Book.objects.all()

        if q:
            queryset = queryset.filter(
                Q(title__icontains=q)
                | Q(author__icontains=q)
                | Q(isbn__icontains=q)
                | Q(publisher__icontains=q)
                | Q(shelf_number__icontains=q)
                | Q(description__icontains=q)
            )

        if category:
            queryset = queryset.filter(
                category_id=category
            )

        queryset = queryset.select_related(
            "category"
        ).order_by("title")

    return render(
        request,
        "library/books.html",
        {
            "books": queryset,
            "categories": Category.objects.all(),
            "q": q,
            "selected_category": category,
        }
    )

def book_add(request):

    if request.method == "POST":
        form = BookForm(request.POST, request.FILES)

        if form.is_valid():
            form.save()
            messages.success(request, "Book added successfully.")
            return redirect("library_books")

    else:
        form = BookForm()

    return render(
        request,
        "library/form.html",
        {
            "form": form,
            "title": "Add Book",
            "back_url": "library_books",
        }
    )


@library_access_required
def book_edit(request, pk):

    book = get_object_or_404(Book, pk=pk)

    if request.method == "POST":
        form = BookForm(
            request.POST,
            request.FILES,
            instance=book
        )

        if form.is_valid():
            form.save()
            messages.success(request, "Book updated successfully.")
            return redirect("library_books")

    else:
        form = BookForm(instance=book)

    return render(
        request,
        "library/form.html",
        {
            "form": form,
            "title": "Edit Book",
            "back_url": "library_books",
        }
    )


@library_access_required
def book_delete(request, pk):

    book = get_object_or_404(Book, pk=pk)

    if request.method == "POST":
        book.delete()
        messages.success(request, "Book deleted successfully.")
        return redirect("library_books")

    return render(
        request,
        "library/confirm_delete.html",
        {
            "object": book,
            "title": "Delete Book",
            "back_url": "library_books",
        }
    )


# ============================================================
# CATEGORIES
# ============================================================

@library_access_required
def categories(request):

    return render(
        request,
        "library/categories.html",
        {
            "categories": Category.objects.all().order_by("pk")
        }
    )


@library_access_required
def category_add(request):

    if request.method == "POST":
        form = CategoryForm(request.POST)

        if form.is_valid():
            form.save()
            messages.success(request, "Category added successfully.")
            return redirect("library_categories")

    else:
        form = CategoryForm()

    return render(
        request,
        "library/form.html",
        {
            "form": form,
            "title": "Add Category",
            "back_url": "library_categories",
        }
    )


@library_access_required
def category_edit(request, pk):

    obj = get_object_or_404(Category, pk=pk)

    if request.method == "POST":
        form = CategoryForm(request.POST, instance=obj)

        if form.is_valid():
            form.save()
            messages.success(request, "Category updated successfully.")
            return redirect("library_categories")

    else:
        form = CategoryForm(instance=obj)

    return render(
        request,
        "library/form.html",
        {
            "form": form,
            "title": "Edit Category",
            "back_url": "library_categories",
        }
    )


@library_access_required
def category_delete(request, pk):

    obj = get_object_or_404(Category, pk=pk)

    if request.method == "POST":
        obj.delete()
        messages.success(request, "Category deleted successfully.")
        return redirect("library_categories")

    return render(
        request,
        "library/confirm_delete.html",
        {
            "object": obj,
            "title": "Delete Category",
            "back_url": "library_categories",
        }
    )


# ============================================================
# MEMBERS
# ============================================================

@library_access_required
def members(request):

    q = request.GET.get("q", "").strip()
    class_name = request.GET.get("class", "").strip()
    stream = request.GET.get("stream", "").strip()
    member_type = request.GET.get("member_type", "").strip()

    queryset = LibraryMember.objects.none()

    filters_applied = bool(
        q or class_name or stream or member_type
    )

    if filters_applied:

        queryset = LibraryMember.objects.all()

        if q:
            queryset = queryset.filter(
                Q(name__icontains=q)
                | Q(admission_number__icontains=q)
                | Q(phone__icontains=q)
                | Q(email__icontains=q)
                | Q(student__first_name__icontains=q)
                | Q(student__middle_name__icontains=q)
                | Q(student__last_name__icontains=q)
                | Q(student__admission_no__icontains=q)
                | Q(employee__first_name__icontains=q)
                | Q(employee__last_name__icontains=q)
                | Q(employee__employee_number__icontains=q)
            )

        if class_name:
            queryset = queryset.filter(
                student__class_name=class_name
            )

        if stream:
            queryset = queryset.filter(
                student__stream=stream
            )

        if member_type:
            queryset = queryset.filter(
                member_type=member_type
            )

        queryset = queryset.select_related(
            "student",
            "employee",
        ).order_by("name")

    class_options = (
        LibraryMember.objects
        .filter(
            member_type="student",
            student__isnull=False
        )
        .values_list(
            "student__class_name",
            flat=True
        )
        .distinct()
        .order_by("student__class_name")
    )

    stream_options = (
        LibraryMember.objects
        .filter(
            member_type="student",
            student__isnull=False
        )
        .exclude(
            student__stream=""
        )
        .values_list(
            "student__stream",
            flat=True
        )
        .distinct()
        .order_by("student__stream")
    )

    return render(
        request,
        "library/members.html",
        {
            "members": queryset,
            "q": q,
            "class_name": class_name,
            "stream": stream,
            "member_type": member_type,
            "class_options": class_options,
            "stream_options": stream_options,
            "filters_applied": filters_applied,
        }
    )

@library_access_required
def member_add(request):

    lookup_form = LibraryMemberLookupForm(
        request.POST or None
    )

    found = False
    member_type = ""
    identifier = ""
    person = None
    existing_member = None
    details = {}

    if request.method == "POST":

        action = request.POST.get("action", "").strip()

        member_type = request.POST.get(
            "member_type",
            ""
        ).strip()

        identifier = request.POST.get(
            "identifier",
            ""
        ).strip()

        if action == "lookup":

            lookup_form = LibraryMemberLookupForm(
                request.POST
            )

            if lookup_form.is_valid():

                member_type = lookup_form.cleaned_data[
                    "member_type"
                ]

                identifier = lookup_form.cleaned_data[
                    "identifier"
                ]

                if member_type == "student":

                    person = Student.objects.filter(
                        admission_no__iexact=identifier,
                        is_active=True
                    ).first()

                    if person:

                        existing_member = LibraryMember.objects.filter(
                            student=person
                        ).first()

                        details = {
                            "type": "Student",
                            "number": person.admission_no,
                            "name": person.get_full_name(),
                            "gender": person.gender,
                            "class_name": person.class_name,
                            "stream": person.stream,
                            "phone": person.parent_phone,
                        }

                        found = True

                    else:

                        messages.error(
                            request,
                            f"No active student found with admission number '{identifier}'."
                        )

                elif member_type == "staff":

                    person = Employee.objects.filter(
                        employee_number__iexact=identifier
                    ).first()

                    if person:

                        existing_member = LibraryMember.objects.filter(
                            employee=person
                        ).first()

                        full_name = " ".join(
                            part
                            for part in [
                                person.first_name,
                                person.middle_name,
                                person.last_name,
                            ]
                            if part
                        )

                        details = {
                            "type": "Staff",
                            "number": person.employee_number,
                            "name": full_name,
                            "gender": person.gender or "",
                            "class_name": "",
                            "stream": "",
                            "phone": getattr(
                                person,
                                "phone",
                                ""
                            ) or getattr(
                                person,
                                "phone_number",
                                ""
                            ),
                        }

                        found = True

                    else:

                        messages.error(
                            request,
                            f"No employee found with employee number '{identifier}'."
                        )

        elif action == "add":

            member_type = request.POST.get(
                "member_type",
                ""
            ).strip()

            identifier = request.POST.get(
                "identifier",
                ""
            ).strip()

            if member_type == "student":

                person = Student.objects.filter(
                    admission_no__iexact=identifier,
                    is_active=True
                ).first()

                if not person:

                    messages.error(
                        request,
                        "Student could not be found."
                    )

                else:

                    existing_member = LibraryMember.objects.filter(
                        student=person
                    ).first()

                    if existing_member:

                        messages.warning(
                            request,
                            f"{person.get_full_name()} is already a Library Member."
                        )

                    else:

                        LibraryMember.objects.create(
                            name=person.get_full_name(),
                            admission_number=person.admission_no,
                            member_type="student",
                            student=person,
                            phone=person.parent_phone or "",
                            email="",
                            active=True,
                        )

                        messages.success(
                            request,
                            f"{person.get_full_name()} has been added to Library Members."
                        )

                        return redirect(
                            "library_members"
                        )

            elif member_type == "staff":

                person = Employee.objects.filter(
                    employee_number__iexact=identifier
                ).first()

                if not person:

                    messages.error(
                        request,
                        "Employee could not be found."
                    )

                else:

                    existing_member = LibraryMember.objects.filter(
                        employee=person
                    ).first()

                    if existing_member:

                        messages.warning(
                            request,
                            f"{person.first_name} {person.last_name} is already a Library Member."
                        )

                    else:

                        full_name = " ".join(
                            part
                            for part in [
                                person.first_name,
                                person.middle_name,
                                person.last_name,
                            ]
                            if part
                        )

                        phone = getattr(
                            person,
                            "phone",
                            ""
                        ) or getattr(
                            person,
                            "phone_number",
                            ""
                        )

                        email = getattr(
                            person,
                            "email",
                            ""
                        ) or ""

                        LibraryMember.objects.create(
                            name=full_name,
                            admission_number=person.employee_number,
                            member_type="staff",
                            employee=person,
                            phone=phone,
                            email=email,
                            active=True,
                        )

                        messages.success(
                            request,
                            f"{full_name} has been added to Library Members."
                        )

                        return redirect(
                            "library_members"
                        )

    return render(
        request,
        "library/member_add.html",
        {
            "lookup_form": lookup_form,
            "found": found,
            "member_type": member_type,
            "identifier": identifier,
            "person": person,
            "existing_member": existing_member,
            "details": details,
            "title": "Add Library Member",
            "back_url": "library_members",
        }
    )

def member_edit(request, pk):

    obj = get_object_or_404(LibraryMember, pk=pk)

    if request.method == "POST":
        form = LibraryMemberForm(
            request.POST,
            request.FILES,
            instance=obj
        )

        if form.is_valid():
            form.save()
            messages.success(request, "Member updated successfully.")
            return redirect("library_members")

    else:
        form = LibraryMemberForm(instance=obj)

    return render(
        request,
        "library/form.html",
        {
            "form": form,
            "title": "Edit Library Member",
            "back_url": "library_members",
        }
    )


@library_access_required
def member_delete(request, pk):

    obj = get_object_or_404(LibraryMember, pk=pk)

    if request.method == "POST":
        obj.delete()
        messages.success(request, "Library member deleted successfully.")
        return redirect("library_members")

    return render(
        request,
        "library/confirm_delete.html",
        {
            "object": obj,
            "title": "Delete Library Member",
            "back_url": "library_members",
        }
    )


# ============================================================
# ISSUES
# ============================================================

@library_access_required
@library_access_required
def issues(request):

    from django.contrib import messages
    from django.db.models import Q
    from django.utils import timezone

    from .forms import LibraryIssueCreateForm

    # -----------------------------------------------------
    # ISSUE BOOK
    # -----------------------------------------------------

    if request.method == "POST" and request.POST.get("action") == "issue":

        form = LibraryIssueCreateForm(request.POST)

        if form.is_valid():

            issue = form.save()

            messages.success(
                request,
                f"Book '{issue.book.title}' issued successfully."
            )

            return redirect("library_issues")

    else:

        form = LibraryIssueCreateForm(
            initial={
                "issue_date": timezone.now().date()
            }
        )

    # -----------------------------------------------------
    # SEARCH / FILTER ISSUE RECORDS
    # -----------------------------------------------------

    isbn = request.GET.get("isbn", "").strip()
    issue_search = request.GET.get("issue_search", "").strip()
    selected_id = request.GET.get("selected", "").strip()

    issue_records = (
        BookIssue.objects
        .select_related(
            "book",
            "member",
            "member__student",
            "member__employee",
        )
        .order_by("-issue_date", "-id")
    )

    if isbn:
        issue_records = issue_records.filter(
            book__isbn__icontains=isbn
        )

    if issue_search:

        issue_records = issue_records.filter(
            Q(book__title__icontains=issue_search)
            | Q(book__isbn__icontains=issue_search)
            | Q(member__name__icontains=issue_search)
            | Q(member__admission_number__icontains=issue_search)
            | Q(member__student__first_name__icontains=issue_search)
            | Q(member__student__middle_name__icontains=issue_search)
            | Q(member__student__last_name__icontains=issue_search)
            | Q(member__student__admission_no__icontains=issue_search)
            | Q(member__employee__first_name__icontains=issue_search)
            | Q(member__employee__middle_name__icontains=issue_search)
            | Q(member__employee__last_name__icontains=issue_search)
            | Q(member__employee__employee_number__icontains=issue_search)
        ).distinct()

    # -----------------------------------------------------
    # SELECTED ISSUE
    # -----------------------------------------------------

    selected_issue = None

    if selected_id:

        try:

            selected_issue = issue_records.filter(
                pk=int(selected_id)
            ).first()

        except (TypeError, ValueError):

            selected_issue = None

    # -----------------------------------------------------
    # BOOKS FOR ISSUE FORM
    # -----------------------------------------------------

    books = (
        Book.objects
        .filter(available_copies__gt=0)
        .order_by("title")
    )

    # -----------------------------------------------------
    # ACTIVE LIBRARY MEMBERS
    # -----------------------------------------------------

    members = (
        LibraryMember.objects
        .filter(active=True)
        .select_related(
            "student",
            "employee",
        )
        .order_by("name")
    )

    # -----------------------------------------------------
    # ISSUE STATISTICS
    # -----------------------------------------------------

    active_issues = BookIssue.objects.filter(
        status__in=["issued", "overdue"],
        return_date__isnull=True,
    ).count()

    returned_issues = BookIssue.objects.filter(
        status="returned",
    ).count()

    # -----------------------------------------------------
    # SELECTED ISSUE DISPLAY DATA
    # -----------------------------------------------------

    selected_data = None

    if selected_issue:

        member = selected_issue.member
        student = getattr(member, "student", None)
        employee = getattr(member, "employee", None)

        member_name = member.name
        admission_number = member.admission_number
        employee_number = ""

        if student:

            parts = [
                getattr(student, "first_name", ""),
                getattr(student, "middle_name", ""),
                getattr(student, "last_name", ""),
            ]

            member_name = " ".join(
                part for part in parts if part
            )

            admission_number = (
                getattr(student, "admission_no", "")
                or admission_number
            )

        elif employee:

            parts = [
                getattr(employee, "first_name", ""),
                getattr(employee, "middle_name", ""),
                getattr(employee, "last_name", ""),
            ]

            member_name = " ".join(
                part for part in parts if part
            )

            employee_number = (
                getattr(employee, "employee_number", "")
                or ""
            )

        selected_data = {
            "member_name": member_name,
            "member_type": member.get_member_type_display(),
            "admission_number": admission_number,
            "employee_number": employee_number,
        }

    # -----------------------------------------------------
    # PAGE
    # -----------------------------------------------------

    return render(
        request,
        "library/issues.html",
        {
            "form": form,
            "books": books,
            "members": members,
            "issues": issue_records,
            "selected_issue": selected_issue,
            "selected_data": selected_data,
            "isbn": isbn,
            "issue_search": issue_search,
            "selected_id": selected_id,
            "active_issues": active_issues,
            "returned_issues": returned_issues,
            "title": "Issue & Return Books",
            "back_url": "library_dashboard",
        }
    )
@library_access_required
def issue_add(request):

    from django.contrib import messages
    from django.db import transaction
    from django.shortcuts import redirect, render
    from django.utils import timezone

    from .forms import LibraryIssueCreateForm

    if request.method == "POST":

        form = LibraryIssueCreateForm(request.POST)

        if form.is_valid():

            with transaction.atomic():

                book = (
                    Book.objects
                    .select_for_update()
                    .get(pk=form.cleaned_data["book"].pk)
                )

                if book.available_copies <= 0:

                    form.add_error(
                        "book",
                        "This book has no available copies."
                    )

                else:

                    issue = form.save(commit=False)
                    issue.book = book
                    issue.save()

                    book.available_copies -= 1
                    book.status = (
                        "available"
                        if book.available_copies > 0
                        else "unavailable"
                    )

                    book.save(
                        update_fields=[
                            "available_copies",
                            "status",
                        ]
                    )

                    messages.success(
                        request,
                        f"'{book.title}' issued successfully."
                    )

                    return redirect("library_issue_add")

    else:

        form = LibraryIssueCreateForm(
            initial={
                "issue_date": timezone.now().date()
            }
        )

    return render(
        request,
        "library/issue_add.html",
        {
            "form": form,
            "title": "Issue Book",
            "back_url": "library_issues",
        }
    )

@library_access_required
def issue_edit(request, pk):

    issue = get_object_or_404(BookIssue, pk=pk)

    if request.method == "POST":

        form = BookIssueForm(
            request.POST,
            request.FILES,
            instance=issue
        )

        if form.is_valid():
            form.save()
            messages.success(
                request,
                "Issue record updated successfully."
            )
            return redirect("library_issues")

    else:
        form = BookIssueForm(instance=issue)

    return render(
        request,
        "library/form.html",
        {
            "form": form,
            "title": "Edit Issue",
            "back_url": "library_issues",
        }
    )


@library_access_required

@library_access_required
def returns(request):
    from django.db.models import Q
    from django.shortcuts import render

    query = request.GET.get("q", "").strip()

    # IMPORTANT:
    # Do NOT show issued books until the user searches.
    records = BookIssue.objects.none()

    if query:
        records = (
            BookIssue.objects
            .filter(
                return_date__isnull=True,
                status__in=["issued", "overdue"],
            )
            .filter(
                Q(book__isbn__icontains=query)
                | Q(book__title__icontains=query)
                | Q(member__admission_number__icontains=query)
                | Q(member__student__admission_no__icontains=query)
                | Q(member__employee__employee_number__icontains=query)
            )
            .select_related(
                "book",
                "member",
                "member__student",
                "member__employee",
            )
            .order_by("-issue_date", "-id")
            .distinct()
        )

    return render(
        request,
        "library/returns.html",
        {
            "records": records,
            "query": query,
            "searched": bool(query),
        },
    )
def issue_return(request, pk):

    from django.contrib import messages
    from django.db import transaction
    from django.shortcuts import get_object_or_404
    from django.utils import timezone

    if request.method != "POST":

        messages.warning(
            request,
            "Please use the Return button to return a book."
        )

        return redirect(
            f"/library/issues/?selected={pk}"
        )

    with transaction.atomic():

        issue = get_object_or_404(
            BookIssue.objects
            .select_for_update()
            .select_related("member"),
            pk=pk,
        )

        book = (
            Book.objects
            .select_for_update()
            .get(pk=issue.book_id)
        )

        if issue.status == "returned" or issue.return_date:

            messages.info(
                request,
                "This book has already been returned."
            )

        else:

            issue.return_date = timezone.now().date()
            issue.status = "returned"

            issue.save(
                update_fields=[
                    "return_date",
                    "status",
                ]
            )

            book.available_copies = min(
                book.total_copies,
                book.available_copies + 1,
            )

            book.status = (
                "available"
                if book.available_copies > 0
                else "unavailable"
            )

            book.save(
                update_fields=[
                    "available_copies",
                    "status",
                ]
            )

            messages.success(
                request,
                f"'{book.title}' returned successfully."
            )

    return redirect(
        f"/library/issues/?selected={pk}"
    )

def reports(request):

    issues = BookIssue.objects.all()

    today = date.today()
    active = []
    overdue = []

    returned_field = find_field(
        BookIssue,
        ["returned", "is_returned"]
    )

    return_date_field = find_field(
        BookIssue,
        ["return_date", "returned_date", "date_returned"]
    )

    due_field = find_field(
        BookIssue,
        ["due_date", "return_due", "expected_return_date"]
    )

    for issue in issues:

        returned = False

        if returned_field:
            returned = bool(
                getattr(issue, returned_field, False)
            )

        if return_date_field and getattr(
            issue,
            return_date_field,
            None
        ):
            returned = True

        if not returned:

            active.append(issue)

            if due_field:

                due = getattr(
                    issue,
                    due_field,
                    None
                )

                if due and due < today:
                    overdue.append(issue)

    return render(
        request,
        "library/reports.html",
        {
            "total_books": Book.objects.count(),
            "total_categories": Category.objects.count(),
            "total_members": LibraryMember.objects.count(),
            "total_issues": issues.count(),
            "active_issues": active,
            "overdue": overdue,
        }
    )































@library_access_required
def book_print_list(request):
    from django.shortcuts import render

    books = (
        Book.objects
        .select_related("category")
        .order_by("title", "author")
    )

    return render(
        request,
        "library/book_print_list.html",
        {
            "books": books,
        },
    )


@library_access_required
def book_all_list(request):
    from django.shortcuts import render
    from accounts.models import SchoolBranding

    books = (
        Book.objects
        .select_related("category")
        .order_by("title", "author")
    )

    school_branding = (
        SchoolBranding.objects
        .filter(is_active=True)
        .first()
    )

    return render(
        request,
        "library/book_all_list.html",
        {
            "books": books,
            "school_branding": school_branding,
        },
    )



