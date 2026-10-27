from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
import json
from django.contrib.auth.decorators import login_required
from accounts.staff_access import role_permission_required
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponseForbidden

from students.models import Student
from .models import AcademicYear, Term, FeeRecord, FeePayment


# ============================================================
# CLASS OPTIONS
# ============================================================

CLASS_CHOICES = [
    ("PG", "Play Group"),
    ("PP1", "PP1"),
    ("PP2", "PP2"),
    ("G1", "Grade 1"),
    ("G2", "Grade 2"),
    ("G3", "Grade 3"),
    ("G4", "Grade 4"),
    ("G5", "Grade 5"),
    ("G6", "Grade 6"),
    ("G7", "Grade 7"),
    ("G8", "Grade 8"),
    ("G9", "Grade 9"),
    ("G10", "Grade 10"),
    ("G11", "Grade 11"),
    ("G12", "Grade 12"),
]


TERM_CHOICES = [
    ("1", "Term 1"),
    ("2", "Term 2"),
    ("3", "Term 3"),
]


# ============================================================
# FEES DASHBOARD
# ============================================================

@login_required
@role_permission_required("view_feerecord", "fees")
def fees_dashboard(request):

    fee_records = (
        FeeRecord.objects
        .select_related(
            "student",
            "academic_year",
            "term"
        )
        .prefetch_related("payments")
        .order_by("-id")
    )

    students_count = Student.objects.count()

    total_opening = sum(
        record.opening_balance or 0
        for record in fee_records
    )

    total_charged = sum(
        record.amount_charged or 0
        for record in fee_records
    )

    total_paid = sum(
        record.amount_paid or 0
        for record in fee_records
    )

    total_balance = sum(
        record.balance or 0
        for record in fee_records
    )

    recent_payments = (
        FeePayment.objects
        .select_related(
            "fee_record",
            "fee_record__student"
        )
        .order_by("-id")[:20]
    )

    recent_fee_records = fee_records[:20]

    return render(
        request,
        "fees/dashboard.html",
        {
            "students_count": students_count,
            "total_opening": total_opening,
            "total_charged": total_charged,
            "total_paid": total_paid,
            "total_balance": total_balance,
            "recent_payments": recent_payments,
            "fee_records": recent_fee_records,
        }
    )


# ============================================================
# ============================================================
# RECEIPT LIST / SEARCH BY ADMISSION OR RECEIPT NUMBER
# ============================================================

@login_required
@role_permission_required("view_feepayment", "fees")
def receipt_list(request):
    admission_no = request.GET.get("admission_no", "").strip()
    receipt_number = request.GET.get("receipt_number", "").strip()

    student = None
    payments = FeePayment.objects.none()

    if admission_no:
        student = Student.objects.filter(admission_no__iexact=admission_no).first()
        if student:
            payments = FeePayment.objects.filter(fee_record__student=student).select_related("fee_record", "fee_record__student", "fee_record__academic_year", "fee_record__term").order_by("-id")
    elif receipt_number:
        payments = FeePayment.objects.filter(receipt_number__iexact=receipt_number).select_related("fee_record", "fee_record__student", "fee_record__academic_year", "fee_record__term").order_by("-id")
        payment = payments.first()
        if payment:
            student = payment.fee_record.student

    payment_list = list(payments)
    total_paid = sum((p.amount or 0) for p in payment_list)

    return render(request, "fees/receipt_list.html", {
        "admission_no": admission_no,
        "receipt_number": receipt_number,
        "student": student,
        "payments": payment_list,
        "payment_count": len(payment_list),
        "total_paid": total_paid,
    })

# ============================================================
# PAYMENT LIST BY CLASS / ACADEMIC YEAR / TERM
# ============================================================

@login_required
@role_permission_required("add_feepayment", "fees")
def fee_payments_page(request):
    from decimal import Decimal, InvalidOperation
    from django.contrib import messages
    from django.db.models import Q
    from django.shortcuts import render, redirect, get_object_or_404
    from django.utils import timezone

    from students.models import Student
    from .models import FeeRecord, FeePayment, AcademicYear, Term

    search = request.GET.get("search", "").strip()
    student_id = request.GET.get("student", "").strip()
    record_id = request.GET.get("record", "").strip()

    students = Student.objects.filter(is_active=True)

    if search:
        students = students.filter(
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(admission_no__icontains=search)
        )

    students = students.order_by("first_name", "last_name")[:30]

    selected_student = None
    records = FeeRecord.objects.none()
    selected_record = None

    if student_id:
        selected_student = get_object_or_404(
            Student,
            id=student_id,
            is_active=True
        )

        records = (
            FeeRecord.objects
            .filter(student=selected_student)
            .select_related("academic_year", "term")
            .order_by(
                "-academic_year__year",
                "-term__order",
                "-id"
            )
        )

    if record_id and selected_student:
        selected_record = get_object_or_404(
            FeeRecord,
            id=record_id,
            student=selected_student
        )

    if request.method == "POST":
        action = request.POST.get("action", "")

        if action == "save_payment":

            posted_student_id = request.POST.get("student_id")
            posted_record_id = request.POST.get("record_id")

            fee_record = get_object_or_404(
                FeeRecord.objects.select_related(
                    "student",
                    "academic_year",
                    "term"
                ),
                id=posted_record_id,
                student_id=posted_student_id
            )

            if fee_record.term and fee_record.term.is_closed:
                messages.error(
                    request,
                    "This term is closed. New payments cannot be posted to it."
                )
                return redirect(
                    f"/fees/payments/?student={fee_record.student_id}"
                    f"&record={fee_record.id}"
                )

            amount_text = request.POST.get("amount", "").strip()
            payment_date = request.POST.get("payment_date") or timezone.localdate()
            payment_method = request.POST.get("payment_method", "").strip()
            reference = request.POST.get("reference", "").strip()

            try:
                amount = Decimal(amount_text)
            except (InvalidOperation, TypeError):
                messages.error(request, "Enter a valid payment amount.")
                return redirect(
                    f"/fees/payments/?student={fee_record.student_id}"
                    f"&record={fee_record.id}"
                )

            if amount <= 0:
                messages.error(request, "Payment amount must be greater than zero.")
                return redirect(
                    f"/fees/payments/?student={fee_record.student_id}"
                    f"&record={fee_record.id}"
                )

            if not payment_method:
                payment_method = "Cash"

            payment = FeePayment.objects.create(
                fee_record=fee_record,
                amount=amount,
                payment_date=payment_date,
                payment_method=payment_method,
                reference=reference,
            )

            messages.success(
                request,
                f"Payment of KSh {amount:,.2f} recorded successfully. "
                f"Receipt {payment.receipt_number}."
            )

            return redirect(
                f"/fees/payments/?student={fee_record.student_id}"
                f"&record={fee_record.id}&saved={payment.id}"
            )

    saved_payment = None
    saved_id = request.GET.get("saved")

    if saved_id:
        try:
            saved_payment = (
                FeePayment.objects
                .select_related(
                    "fee_record",
                    "fee_record__student",
                    "fee_record__academic_year",
                    "fee_record__term",
                )
                .get(
                    id=saved_id,
                    fee_record__student_id=student_id
                )
            )
        except FeePayment.DoesNotExist:
            saved_payment = None

    return render(
        request,
        "fees/fee_payments.html",
        {
            "search": search,
            "students": students,
            "selected_student": selected_student,
            "records": records,
            "selected_record": selected_record,
            "saved_payment": saved_payment,
            "today": timezone.localdate(),
        }
    )


@login_required
@role_permission_required("view_feepayment", "fees")
def payment_list(request):

    academic_years = AcademicYear.objects.all().order_by("-year")
    terms = Term.objects.all().order_by("order")

    selected_class = request.GET.get("class_name", "").strip()
    selected_year = request.GET.get("academic_year", "").strip()
    selected_term = request.GET.get("term", "").strip()

    records = FeeRecord.objects.none()

    if selected_class and selected_year and selected_term:

        records = (
            FeeRecord.objects
            .filter(
                student__class_name=selected_class,
                academic_year_id=selected_year,
                term_id=selected_term
            )
            .select_related(
                "student",
                "academic_year",
                "term"
            )
            .prefetch_related("payments")
            .order_by("student__admission_no")
        )

    total_opening = sum(
        record.opening_balance or 0
        for record in records
    )

    total_charged = sum(
        record.amount_charged or 0
        for record in records
    )

    total_paid = sum(
        record.amount_paid or 0
        for record in records
    )

    total_balance = sum(
        record.balance or 0
        for record in records
    )

    return render(
        request,
        "fees/payment_list.html",
        {
            "academic_years": academic_years,
            "terms": terms,
            "records": records,
            "selected_class": selected_class,
            "selected_year": selected_year,
            "selected_term": selected_term,
            "total_opening": total_opening,
            "total_charged": total_charged,
            "total_paid": total_paid,
            "total_balance": total_balance,
            "class_choices": CLASS_CHOICES,
        }
    )

# PRINT INDIVIDUAL RECEIPT
# ============================================================

@login_required
@role_permission_required("view_feepayment", "fees")
def print_receipt(request, payment_id):

    payment = get_object_or_404(
        FeePayment.objects.select_related(
            "fee_record",
            "fee_record__student",
            "fee_record__academic_year",
            "fee_record__term",
        ),
        id=payment_id
    )

    fee_record = payment.fee_record
    student = fee_record.student

    return render(
        request,
        "fees/receipt.html",
        {
            "payment": payment,
            "fee_record": fee_record,
            "student": student,
        }
    )


# ============================================================
# PRINT LEARNER INVOICE
# ============================================================

@login_required
@role_permission_required("view_feerecord", "fees")
def print_invoice(request, student_id):

    student = get_object_or_404(
        Student,
        id=student_id
    )

    academic_year_id = request.GET.get(
        "academic_year"
    )

    term_id = request.GET.get(
        "term"
    )

    fee_records = (
        FeeRecord.objects
        .filter(
            student=student
        )
        .select_related(
            "academic_year",
            "term"
        )
        .prefetch_related("payments")
        .order_by(
            "-academic_year__year",
            "-term__order"
        )
    )

    if academic_year_id:
        fee_records = fee_records.filter(
            academic_year_id=academic_year_id
        )

    if term_id:
        fee_records = fee_records.filter(
            term_id=term_id
        )

    total_opening = sum(
        record.opening_balance or 0
        for record in fee_records
    )

    total_charged = sum(
        record.amount_charged or 0
        for record in fee_records
    )

    total_paid = sum(
        record.amount_paid or 0
        for record in fee_records
    )

    total_balance = sum(
        record.balance or 0
        for record in fee_records
    )

    return render(
        request,
        "fees/invoice.html",
        {
            "student": student,
            "fee_records": fee_records,
            "total_opening": total_opening,
            "total_charged": total_charged,
            "total_paid": total_paid,
            "total_balance": total_balance,
        }
    )


# ============================================================
# PRINT LEARNER STATEMENT
# ============================================================

@login_required
@role_permission_required("view_feerecord", "fees")
def print_statement(request, student_id):

    student = get_object_or_404(
        Student,
        id=student_id
    )

    fee_records = (
        FeeRecord.objects
        .filter(
            student=student
        )
        .select_related(
            "academic_year",
            "term"
        )
        .prefetch_related("payments")
        .order_by(
            "-academic_year__year",
            "-term__order"
        )
    )

    total_opening = sum(
        record.opening_balance or 0
        for record in fee_records
    )

    total_charged = sum(
        record.amount_charged or 0
        for record in fee_records
    )

    total_paid = sum(
        record.amount_paid or 0
        for record in fee_records
    )

    total_balance = sum(
        record.balance or 0
        for record in fee_records
    )

    payments = (
        FeePayment.objects
        .filter(
            fee_record__student=student
        )
        .select_related(
            "fee_record",
            "fee_record__academic_year",
            "fee_record__term",
        )
        .order_by(
            "-payment_date",
            "-id"
        )
    )

    return render(
        request,
        "fees/fee_statement.html",
        {
            "student": student,
            "fee_records": fee_records,
            "payments": payments,
            "total_opening": total_opening,
            "total_charged": total_charged,
            "total_paid": total_paid,
            "total_balance": total_balance,
        }
    )



# ============================================================
# FEE STRUCTURE SETTINGS
# ============================================================

@login_required
@role_permission_required("view_feestructure", "fees")
def fee_structure_settings(request):

    from django.contrib import messages
    from django.db import transaction
    from django.shortcuts import render, redirect, get_object_or_404
    from django.db.models import Sum
    from .models import FeeStructure, AcademicYear, Term
    from timetable.models import TimetableClass

    years = (
        AcademicYear.objects
        .filter(is_active=True)
        .order_by("-year")
    )

    classes = (
        TimetableClass.objects
        .filter(active=True)
        .exclude(name="")
        .values_list("name", flat=True)
        .distinct()
        .order_by("name")
    )

    selected_year = request.GET.get(
        "year",
        ""
    ).strip()

    selected_term = request.GET.get(
        "term",
        ""
    ).strip()

    selected_class = request.GET.get(
        "class",
        ""
    ).strip()

    # Default to the newest active academic year.
    if not selected_year and years.exists():
        selected_year = str(years.first().id)

    # Only show terms belonging to the selected academic year.
    terms = (
        Term.objects
        .filter(
            academic_year_id=selected_year
        )
        .order_by("order")
    )

    structures = (
        FeeStructure.objects
        .select_related(
            "academic_year",
            "term"
        )
        .all()
    )

    if selected_year:
        structures = structures.filter(
            academic_year_id=selected_year
        )

    if selected_term:
        structures = structures.filter(
            term_id=selected_term,
            term__academic_year_id=selected_year
        )

    if selected_class:
        structures = structures.filter(
            class_name=selected_class
        )

    structures = structures.order_by(
        "-academic_year__year",
        "term__order",
        "class_name",
        "fee_item",
    )

    # --------------------------------------------------------
    # ADD FEE ITEM
    # --------------------------------------------------------

    if request.method == "POST":

        action = request.POST.get(
            "action",
            ""
        )

        # ----------------------------------------------------
        # SAVE / OPEN TERM
        # ----------------------------------------------------

        if action == "save_term":

            year_id = request.POST.get("term_year")
            term_id = request.POST.get("term_setup")
            start_date = request.POST.get("start_date") or None
            end_date = request.POST.get("end_date") or None

            try:

                year = AcademicYear.objects.get(
                    id=year_id,
                    is_active=True
                )

                term = Term.objects.get(
                    id=term_id
                )

                # A term can only belong to one academic year.
                if (
                    term.academic_year_id is not None
                    and term.academic_year_id != year.id
                ):
                    raise ValueError(
                        "This term is already assigned to another academic year."
                    )

                if not start_date or not end_date:
                    raise ValueError(
                        "Please enter both the start date and end date."
                    )

                if start_date > end_date:
                    raise ValueError(
                        "Term start date cannot be after the end date."
                    )

                term.academic_year = year
                term.start_date = start_date
                term.end_date = end_date
                term.is_closed = False
                term.is_active = True
                term.closed_at = None

                term.save(
                    update_fields=[
                        "academic_year",
                        "start_date",
                        "end_date",
                        "is_closed",
                        "is_active",
                        "closed_at",
                    ]
                )

                messages.success(
                    request,
                    f"{year.year} {term.name} has been opened successfully."
                )

            except Exception as exc:

                messages.error(
                    request,
                    "Unable to save term: " + str(exc)
                )

            return redirect(
                "fees:fee_structure_settings"
            )

        # ----------------------------------------------------
        # CLOSE TERM AND CARRY BALANCES FORWARD
        # ----------------------------------------------------

        if action == "close_term":

            year_id = request.POST.get("close_year")
            term_id = request.POST.get("close_term")

            try:

                from django.db import transaction
                from django.utils import timezone
                from django.db.models import Sum
                from .models import FeeRecord, FeeStructure

                with transaction.atomic():

                    year = AcademicYear.objects.get(
                        id=year_id
                    )

                    term = (
                        Term.objects
                        .select_for_update()
                        .get(
                            id=term_id,
                            academic_year=year
                        )
                    )

                    if term.is_closed:
                        raise ValueError(
                            f"{term.name} is already closed."
                        )

                    if not term.start_date or not term.end_date:
                        raise ValueError(
                            "This term does not have complete dates configured."
                        )

                    # Find next term ONLY in this academic year.
                    next_term = (
                        Term.objects
                        .filter(
                            academic_year=year,
                            order__gt=term.order,
                        )
                        .order_by("order")
                        .first()
                    )

                    next_year = year

                    # Final term -> Term 1 of next academic year.
                    if next_term is None:

                        next_year = (
                            AcademicYear.objects
                            .filter(
                                year__gt=year.year,
                                is_active=True
                            )
                            .order_by("year")
                            .first()
                        )

                        if next_year is None:
                            raise ValueError(
                                "No next academic year is configured."
                            )

                        next_term = (
                            Term.objects
                            .filter(
                                academic_year=next_year,
                                order=1
                            )
                            .first()
                        )

                        if next_term is None:
                            raise ValueError(
                                f"Term 1 is not configured for {next_year.year}."
                            )

                    current_records = (
                        FeeRecord.objects
                        .filter(
                            academic_year=year,
                            term=term,
                            student__is_active=True,
                        )
                        .select_related("student")
                    )

                    carried = 0
                    created = 0
                    updated = 0

                    for current_record in current_records:

                        learner = current_record.student
                        balance = current_record.balance

                        next_record = (
                            FeeRecord.objects
                            .filter(
                                student=learner,
                                academic_year=next_year,
                                term=next_term,
                            )
                            .first()
                        )

                        next_structure_total = (
                            FeeStructure.objects
                            .filter(
                                academic_year=next_year,
                                term=next_term,
                                class_name=learner.class_name,
                                is_active=True,
                            )
                            .aggregate(
                                total=Sum("amount")
                            )["total"]
                        ) or 0

                        if next_record:

                            next_record.opening_balance = balance
                            next_record.amount_charged = (
                                next_structure_total
                            )

                            next_record.save(
                                update_fields=[
                                    "opening_balance",
                                    "amount_charged",
                                ]
                            )

                            updated += 1

                        else:

                            FeeRecord.objects.create(
                                student=learner,
                                academic_year=next_year,
                                term=next_term,
                                opening_balance=balance,
                                amount_charged=next_structure_total,
                                old_academic_year=str(
                                    next_year.year
                                ),
                                old_term=str(
                                    next_term.order
                                ),
                            )

                            created += 1

                        carried += 1

                    term.is_closed = True
                    term.closed_at = timezone.now()
                    term.is_active = False

                    term.save(
                        update_fields=[
                            "is_closed",
                            "closed_at",
                            "is_active",
                        ]
                    )

                messages.success(
                    request,
                    f"{year.year} {term.name} closed successfully. "
                    f"{carried} learner balance(s) carried to "
                    f"{next_year.year} {next_term.name}. "
                    f"{created} record(s) created and "
                    f"{updated} updated."
                )

            except Exception as exc:

                messages.error(
                    request,
                    "Unable to close term: " + str(exc)
                )

            return redirect(
                "fees:fee_structure_settings"
            )

        # ----------------------------------------------------
        # BULK ADD FEE STRUCTURE
        # ----------------------------------------------------

        if action == "bulk_add":

            year_id = request.POST.get("bulk_year")
            term_id = request.POST.get("bulk_term")

            try:

                from decimal import Decimal
                from django.db import transaction
                from students.models import Student
                from .models import FeeRecord

                year = AcademicYear.objects.get(
                    id=year_id,
                    is_active=True
                )

                term = Term.objects.get(
                    id=term_id,
                    academic_year=year
                )

                if term.is_closed:
                    raise ValueError(
                        f"{term.name} is already closed."
                    )

                # Fee item names submitted by the bulk form.
                fee_items = request.POST.getlist(
                    "bulk_fee_item"
                )

                saved = 0
                skipped = 0

                with transaction.atomic():

                    for index, fee_item in enumerate(fee_items):

                        fee_item = fee_item.strip()

                        class_name = request.POST.get(
                            f"bulk_class_{index}",
                            ""
                        ).strip()

                        amount_value = request.POST.get(
                            f"bulk_amount_{index}",
                            ""
                        ).strip()

                        if not class_name or not fee_item:
                            skipped += 1
                            continue

                        if not amount_value:
                            skipped += 1
                            continue

                        try:
                            amount = Decimal(amount_value)
                        except Exception:
                            skipped += 1
                            continue

                        if amount < 0:
                            skipped += 1
                            continue

                        if not TimetableClass.objects.filter(
                            active=True,
                            name=class_name
                        ).exists():
                            skipped += 1
                            continue

                        FeeStructure.objects.update_or_create(
                            academic_year=year,
                            term=term,
                            class_name=class_name,
                            fee_item=fee_item,
                            defaults={
                                "amount": amount,
                                "is_active": True,
                            }
                        )

                        # Synchronise the complete configured
                        # structure to active learners in this class.
                        total_structure = (
                            FeeStructure.objects
                            .filter(
                                academic_year=year,
                                term=term,
                                class_name=class_name,
                                is_active=True,
                            )
                            .aggregate(
                                total=Sum("amount")
                            )["total"]
                        ) or 0

                        learners = Student.objects.filter(
                            is_active=True,
                            class_name=class_name,
                        )

                        for learner in learners:

                            record = (
                                FeeRecord.objects
                                .filter(
                                    student=learner,
                                    academic_year=year,
                                    term=term,
                                )
                                .first()
                            )

                            if record:

                                record.amount_charged = (
                                    total_structure
                                )

                                record.save(
                                    update_fields=[
                                        "amount_charged"
                                    ]
                                )

                            else:

                                previous_record = (
                                    FeeRecord.objects
                                    .filter(
                                        student=learner,
                                        academic_year=year,
                                    )
                                    .exclude(term=term)
                                    .select_related("term")
                                    .order_by(
                                        "-term__order",
                                        "-id"
                                    )
                                    .first()
                                )

                                opening_balance = (
                                    previous_record.balance
                                    if previous_record
                                    else 0
                                )

                                FeeRecord.objects.create(
                                    student=learner,
                                    academic_year=year,
                                    term=term,
                                    opening_balance=opening_balance,
                                    amount_charged=total_structure,
                                    old_academic_year=str(
                                        year.year
                                    ),
                                    old_term=str(
                                        term.order
                                    ),
                                )

                        saved += 1

                messages.success(
                    request,
                    f"Bulk fee structure saved successfully. "
                    f"{saved} item(s) saved and "
                    f"{skipped} row(s) skipped."
                )

            except Exception as exc:

                messages.error(
                    request,
                    "Unable to save bulk fee structure: " + str(exc)
                )

            return redirect(
                "fees:fee_structure_settings"
            )

        if action == "add":

            year_id = request.POST.get(
                "academic_year"
            )

            term_id = request.POST.get(
                "term"
            )

            class_name = request.POST.get(
                "class_name",
                ""
            ).strip()

            fee_item = request.POST.get(
                "fee_item",
                ""
            ).strip()

            amount = request.POST.get(
                "amount",
                ""
            ).strip()

            if not year_id or not term_id:
                messages.error(
                    request,
                    "Please select the academic year and term."
                )

            elif not class_name:
                messages.error(
                    request,
                    "Please select a class."
                )

            elif not fee_item:
                messages.error(
                    request,
                    "Please enter the fee item."
                )

            elif not amount:
                messages.error(
                    request,
                    "Please enter the amount."
                )

            elif not TimetableClass.objects.filter(
                active=True,
                name=class_name
            ).exists():

                messages.error(
                    request,
                    "The selected class is not active in Admin configuration."
                )

            else:

                try:

                    year = AcademicYear.objects.get(
                        id=year_id,
                        is_active=True
                    )

                    term = Term.objects.get(
                        id=term_id,
                        academic_year=year,
                        is_active=True
                    )

                    if term.is_closed:
                        raise ValueError(
                            f"{term.name} is already closed."
                        )

                    FeeStructure.objects.create(
                        academic_year=year,
                        term=term,
                        class_name=class_name,
                        fee_item=fee_item,
                        amount=amount,
                        is_active=True,
                    )

                    # ------------------------------------------------
                    # APPLY FEE STRUCTURE IMMEDIATELY TO EXISTING LEARNERS
                    # CREATE MISSING RECORDS OR UPDATE EXISTING RECORDS
                    # ------------------------------------------------
                    from django.db.models import Sum
                    from students.models import Student
                    from .models import FeeRecord, FeeStructure

                    created_records = 0
                    updated_records = 0

                    total_structure = (
                        FeeStructure.objects
                        .filter(
                            academic_year=year,
                            term=term,
                            class_name=class_name,
                            is_active=True,
                        )
                        .aggregate(total=Sum("amount"))
                        ["total"]
                    ) or 0

                    learners = Student.objects.filter(
                        is_active=True,
                        class_name=class_name,
                    )

                    for learner in learners:

                        record = (
                            FeeRecord.objects
                            .filter(
                                student=learner,
                                academic_year=year,
                                term=term,
                            )
                            .first()
                        )

                        if record:
                            # Keep all payments intact. Only synchronize
                            # the amount charged with the current structure.
                            record.amount_charged = total_structure
                            record.save(
                                update_fields=["amount_charged"]
                            )
                            updated_records += 1

                        else:
                            # Determine opening balance from the previous
                            # term in the same academic year.
                            previous_record = (
                                FeeRecord.objects
                                .filter(
                                    student=learner,
                                    academic_year=year,
                                )
                                .exclude(term=term)
                                .select_related("term")
                                .order_by(
                                    "-term__order",
                                    "-id"
                                )
                                .first()
                            )

                            opening_balance = (
                                previous_record.balance
                                if previous_record
                                else 0
                            )

                            FeeRecord.objects.create(
                                student=learner,
                                academic_year=year,
                                term=term,
                                opening_balance=opening_balance,
                                amount_charged=total_structure,
                                old_academic_year=str(year.year),
                                old_term=str(term.order),
                            )

                            created_records += 1

                    messages.success(
                        request,
                        f"Fee structure item added successfully. "
                        f"{created_records} fee record(s) created and "
                        f"{updated_records} updated."
                    )

                except Exception as exc:

                    messages.error(
                        request,
                        "Unable to add fee item: " + str(exc)
                    )

            return redirect(
                "fees:fee_structure_settings"
            )

        # ----------------------------------------------------
        # TOGGLE ACTIVE STATUS
        # ----------------------------------------------------

        if action == "toggle":

            structure_id = request.POST.get(
                "structure_id"
            )

            structure = get_object_or_404(
                FeeStructure,
                id=structure_id
            )

            structure.is_active = not structure.is_active

            structure.save(
                update_fields=[
                    "is_active",
                    "updated_at",
                ]
            )

            messages.success(
                request,
                "Fee structure status updated."
            )

            return redirect(
                "fees:fee_structure_settings"
            )

        # ----------------------------------------------------
        # DELETE
        # ----------------------------------------------------

        if action == "delete":

            structure_id = request.POST.get(
                "structure_id"
            )

            structure = get_object_or_404(
                FeeStructure,
                id=structure_id
            )

            structure.delete()

            messages.success(
                request,
                "Fee structure item deleted."
            )

            return redirect(
                "fees:fee_structure_settings"
            )

        # ----------------------------------------------------
        # COPY STRUCTURE
        # ----------------------------------------------------

        if action == "copy":

            source_year_id = request.POST.get(
                "source_year"
            )

            source_term_id = request.POST.get(
                "source_term"
            )

            target_year_id = request.POST.get(
                "target_year"
            )

            target_term_id = request.POST.get(
                "target_term"
            )

            if (
                not source_year_id
                or not source_term_id
                or not target_year_id
                or not target_term_id
            ):

                messages.error(
                    request,
                    "Please select both source and destination."
                )

                return redirect(
                    "fees:fee_structure_settings"
                )

            if (
                source_year_id == target_year_id
                and source_term_id == target_term_id
            ):

                messages.error(
                    request,
                    "Source and destination cannot be the same."
                )

                return redirect(
                    "fees:fee_structure_settings"
                )

            try:

                source_items = FeeStructure.objects.filter(
                    academic_year_id=source_year_id,
                    term_id=source_term_id,
                )

                target_year = AcademicYear.objects.get(
                    id=target_year_id,
                    is_active=True
                )

                target_term = Term.objects.get(
                    id=target_term_id,
                    is_active=True
                )

                copied = 0

                with transaction.atomic():

                    for item in source_items:

                        FeeStructure.objects.create(
                            academic_year=target_year,
                            term=target_term,
                            class_name=item.class_name,
                            fee_item=item.fee_item,
                            amount=item.amount,
                            is_active=item.is_active,
                        )

                        copied += 1

                messages.success(
                    request,
                    f"{copied} fee structure item(s) copied successfully."
                )

            except Exception as exc:

                messages.error(
                    request,
                    "Copy failed: " + str(exc)
                )

            return redirect(
                "fees:fee_structure_settings"
            )

    totals = (
        structures
        .values(
            "academic_year__year",
            "term__name",
            "class_name"
        )
        .annotate(
            total=Sum("amount")
        )
        .order_by(
            "-academic_year__year",
            "term__order",
            "class_name"
        )
    )

    return render(
        request,
        "fees/fee_structure_settings.html",
        {
            "years": years,
            "terms": terms,
            "classes": classes,
            "selected_year": selected_year,
            "structures": structures,
            "totals": totals,
            "selected_year": selected_year,
            "selected_term": selected_term,
            "selected_class": selected_class,
        }
    )


# ============================================================
# EDIT FEE STRUCTURE
# ============================================================


@login_required
@role_permission_required("view_feestructure", "fees")
def configured_fee_items(request):

    from django.shortcuts import render
    from django.db.models import Sum
    from .models import FeeStructure, AcademicYear, Term
    from timetable.models import TimetableClass

    years = (
        AcademicYear.objects
        .filter(is_active=True)
        .order_by("-year")
    )

    selected_year = request.GET.get(
        "year",
        ""
    ).strip()

    selected_term = request.GET.get(
        "term",
        ""
    ).strip()

    selected_class = request.GET.get(
        "class",
        ""
    ).strip()

    # Default to newest active academic year.
    if not selected_year and years.exists():
        selected_year = str(years.first().id)

    terms = (
        Term.objects
        .filter(
            academic_year_id=selected_year
        )
        .order_by("order")
    )

    classes = (
        TimetableClass.objects
        .filter(active=True)
        .exclude(name="")
        .values_list("name", flat=True)
        .distinct()
        .order_by("name")
    )

    structures = FeeStructure.objects.none()

    if selected_year and selected_term and selected_class:

        structures = (
            FeeStructure.objects
            .filter(
                academic_year_id=selected_year,
                term_id=selected_term,
                class_name=selected_class,
            )
            .select_related(
                "academic_year",
                "term",
            )
            .order_by(
                "fee_item"
            )
        )

    total_amount = (
        structures.aggregate(
            total=Sum("amount")
        )["total"]
        if structures.exists()
        else 0
    )

    context = {
        "years": years,
        "terms": terms,
        "classes": classes,
        "selected_year": selected_year,
        "selected_term": selected_term,
        "selected_class": selected_class,
        "structures": structures,
        "total_amount": total_amount,
        "loaded": bool(
            selected_year
            and selected_term
            and selected_class
        ),
    }

    return render(
        request,
        "fees/configured_fee_items.html",
        context
    )


@login_required
@role_permission_required("change_feestructure", "fees")
def edit_fee_structure(request, id):

    from django.contrib import messages
    from django.shortcuts import render, redirect, get_object_or_404
    from .models import FeeStructure, AcademicYear, Term
    from timetable.models import TimetableClass

    structure = get_object_or_404(
        FeeStructure,
        id=id
    )

    years = AcademicYear.objects.filter(
        is_active=True
    ).order_by("-year")

    terms = Term.objects.filter(
        is_active=True
    ).order_by("order")

    classes = (
        TimetableClass.objects
        .filter(active=True)
        .exclude(name="")
        .values_list("name", flat=True)
        .distinct()
        .order_by("name")
    )

    if request.method == "POST":

        year_id = request.POST.get(
            "academic_year"
        )

        term_id = request.POST.get(
            "term"
        )

        class_name = request.POST.get(
            "class_name",
            ""
        ).strip()

        fee_item = request.POST.get(
            "fee_item",
            ""
        ).strip()

        amount = request.POST.get(
            "amount",
            ""
        ).strip()

        if not year_id or not term_id or not class_name:
            messages.error(
                request,
                "Please complete all required fields."
            )

        elif not TimetableClass.objects.filter(
            active=True,
            name=class_name
        ).exists():

            messages.error(
                request,
                "The selected class is not active in Admin configuration."
            )

        else:

            try:

                structure.academic_year_id = year_id
                structure.term_id = term_id
                structure.class_name = class_name
                structure.fee_item = fee_item
                structure.amount = amount

                structure.save()

                messages.success(
                    request,
                    "Fee structure updated successfully."
                )

                return redirect(
                    "fees:fee_structure_settings"
                )

            except Exception as exc:

                messages.error(
                    request,
                    "Update failed: " + str(exc)
                )

    return render(
        request,
        "fees/edit_fee_structure.html",
        {
            "structure": structure,
            "years": years,
            "terms": terms,
            "classes": classes,
        }
    )



# ============================================================
# ONLINE PAYMENTS
# ============================================================

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from fees.models import OnlinePayment
from fees.services.mpesa import (
    MpesaError,
    initiate_stk_push,
)

from fees.services.online_payments import (
    mark_payment_verified,
    OnlinePaymentError,
    create_online_payment,
    get_available_payment_methods,
    get_payment_status,
)


def _get_portal_payer_role(request):
    """
    Determine whether the logged-in account is an Admin,
    Parent, or Student.
    """

    profile = getattr(request.user, "profile", None)

    if not profile:
        return None

    if profile.role in {"ADMIN", "PARENT", "STUDENT"}:
        return profile.role

    return None


def _get_allowed_student(request, student_id):
    """
    Restrict payment access to students the current account is authorized to pay for.
    """

    profile = getattr(request.user, "profile", None)

    if not profile:
        return None

    # Student can only pay their own fees.
    if profile.role == "STUDENT":
        if profile.student_id != student_id:
            return None
        return profile.student

    # Parent can only pay fees for their linked children.
    if profile.role == "PARENT":
        from parents.models import Parent

        parent = Parent.objects.filter(
            user=request.user
        ).first()

        if not parent:
            return None

        return parent.children.filter(
            id=student_id
        ).first()

    # Admin can access any student.
    if profile.role == "ADMIN":
        from students.models import Student

        return Student.objects.filter(
            id=student_id
        ).first()

    return None


@require_http_methods(["GET", "POST"])
@login_required
def online_payment_page(request):
    """
    Start an online fee payment.

    Expected GET parameters:
        student_id
        fee_record_id
    """

    payer_role = _get_portal_payer_role(request)

    if payer_role not in {"ADMIN", "PARENT", "STUDENT"}:
        messages.error(
            request,
            "Your account is not authorized to make online payments.",
        )
        return redirect("accounts:login")

    student_id = request.GET.get("student_id") or request.POST.get(
        "student_id"
    )

    fee_record_id = request.GET.get(
        "fee_record_id"
    ) or request.POST.get(
        "fee_record_id"
    )

    if not student_id or not fee_record_id:
        messages.error(
            request,
            "Please select a student and fee record.",
        )
        return redirect("accounts:student_fees")

    # Safely validate the supplied student ID.
    try:
        student_pk = int(str(student_id).strip())
    except (TypeError, ValueError):
        messages.error(
            request,
            "Invalid student selected for payment.",
        )
        return redirect("accounts:parent_dashboard")

    student = _get_allowed_student(
        request,
        student_pk,
    )

    if not student:
        messages.error(
            request,
            "You are not authorized to pay fees for this student.",
        )
        if payer_role == "PARENT":
            return redirect("accounts:parent_dashboard")
        return redirect("accounts:student_fees")

    from fees.models import FeeRecord

    fee_record = get_object_or_404(
        FeeRecord.objects.select_related(
            "student",
            "academic_year",
            "term",
        ),
        id=fee_record_id,
        student=student,
    )

    methods = get_available_payment_methods(
        payer_role
    )

    if request.method == "POST":

        amount = request.POST.get(
            "amount",
            "",
        ).strip()

        method_code = request.POST.get(
            "payment_method",
            "",
        ).strip()

        phone_number = request.POST.get(
            "phone_number",
            "",
        ).strip()

        try:
            online_payment = create_online_payment(
                payer=request.user,
                payer_role=payer_role,
                student=student,
                fee_record_id=fee_record.id,
                amount=amount,
                payment_method_code=method_code,
                phone_number=phone_number,
            )

            # ------------------------------------------------
            # M-PESA STK PUSH
            # ------------------------------------------------

            if online_payment.payment_method == "MPESA":

                try:

                    stk_response = initiate_stk_push(
                        phone_number=online_payment.phone_number,
                        amount=online_payment.amount,
                        account_reference=(
                            online_payment.account_reference
                            or f"FEES-{online_payment.id}"
                        ),
                    )

                    online_payment.merchant_request_id = (
                        stk_response.get(
                            "MerchantRequestID",
                            "",
                        )
                    )

                    online_payment.checkout_request_id = (
                        stk_response.get(
                            "CheckoutRequestID",
                            "",
                        )
                    )

                    online_payment.provider_response_code = (
                        stk_response.get(
                            "ResponseCode",
                            "",
                        )
                    )

                    online_payment.provider_response_description = (
                        stk_response.get(
                            "ResponseDescription",
                            "",
                        )
                    )

                    online_payment.provider_raw_response = (
                        stk_response
                    )

                    if stk_response.get("ResponseCode") == "0":

                        online_payment.status = "PROCESSING"

                        online_payment.verification_message = (
                            "M-Pesa payment prompt sent to the "
                            "customer's phone. Awaiting payment."
                        )

                    else:

                        online_payment.status = "FAILED"

                        online_payment.verification_message = (
                            stk_response.get(
                                "ResponseDescription",
                                "M-Pesa STK request failed.",
                            )
                        )

                    online_payment.save(
                        update_fields=[
                            "merchant_request_id",
                            "checkout_request_id",
                            "provider_response_code",
                            "provider_response_description",
                            "provider_raw_response",
                            "status",
                            "verification_message",
                            "updated_at",
                        ]
                    )

                except MpesaError as exc:

                    online_payment.status = "FAILED"

                    online_payment.verification_message = str(exc)

                    online_payment.save(
                        update_fields=[
                            "status",
                            "verification_message",
                            "updated_at",
                        ]
                    )

            messages.success(
                request,
                "Payment request created. Continue with the payment method shown.",
            )

            return redirect(
                "fees:online_payment_status",
                payment_id=online_payment.id,
            )

        except OnlinePaymentError as exc:
            messages.error(
                request,
                str(exc),
            )

    branding = None

    try:
        from accounts.models import SchoolBranding

        branding = SchoolBranding.objects.filter(
            is_active=True
        ).first()
    except Exception:
        pass

    return render(
        request,
        "fees/online_payment.html",
        {
            "student": student,
            "fee_record": fee_record,
            "methods": methods,
            "payer_role": payer_role,
            "branding": branding,
        },
    )


@login_required
def online_payment_status(request, payment_id):
    """
    Display the current status of an online transaction.
    """

    payer_role = _get_portal_payer_role(request)

    if payer_role not in {"ADMIN", "PARENT", "STUDENT"}:
        messages.error(
            request,
            "Your account is not authorized to view this payment.",
        )
        return redirect("accounts:login")

    try:
        online_payment = get_payment_status(
            payment_id,
            payer=request.user,
        )
    except OnlinePaymentError:
        messages.error(
            request,
            "Payment transaction not found.",
        )
        return redirect("accounts:student_fees")

    branding = None

    try:
        from accounts.models import SchoolBranding

        branding = SchoolBranding.objects.filter(
            is_active=True
        ).first()
    except Exception:
        pass

    return render(
        request,
        "fees/online_payment_status.html",
        {
            "online_payment": online_payment,
            "branding": branding,
        },
    )


# ============================================================
# M-PESA DARAJA CALLBACK
# ============================================================

@csrf_exempt
@require_http_methods(["POST"])
def mpesa_callback(request):
    """
    Receive and verify the Daraja STK callback.

    A successful callback is posted through mark_payment_verified(),
    which creates the official FeePayment and receipt exactly once.
    """

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse(
            {
                "ResultCode": 1,
                "ResultDesc": "Invalid JSON payload."
            },
            status=400,
        )

    callback = payload.get("Body", {}).get("stkCallback", {})

    checkout_request_id = (
        callback.get("CheckoutRequestID", "") or ""
    ).strip()

    merchant_request_id = (
        callback.get("MerchantRequestID", "") or ""
    ).strip()

    result_code = callback.get("ResultCode")

    result_description = (
        callback.get("ResultDesc", "") or ""
    ).strip()

    if not checkout_request_id:
        return JsonResponse(
            {
                "ResultCode": 1,
                "ResultDesc": "CheckoutRequestID is missing."
            },
            status=400,
        )

    online_payment = (
        OnlinePayment.objects
        .select_related(
            "fee_record",
            "fee_record__student",
            "fee_record__term",
        )
        .filter(
            checkout_request_id=checkout_request_id
        )
        .first()
    )

    if not online_payment:
        return JsonResponse(
            {
                "ResultCode": 0,
                "ResultDesc": "Callback received."
            }
        )

    # Always retain the complete provider callback.
    online_payment.merchant_request_id = merchant_request_id
    online_payment.provider_response_code = str(
        result_code if result_code is not None else ""
    )
    online_payment.provider_response_description = result_description
    online_payment.provider_raw_response = payload

    # ------------------------------------------------------------
    # FAILED / CANCELLED / DECLINED PAYMENT
    # ------------------------------------------------------------
    if result_code != 0:
        online_payment.status = "FAILED"
        online_payment.verification_message = (
            result_description
            or "M-Pesa payment was not completed."
        )

        online_payment.save(
            update_fields=[
                "merchant_request_id",
                "provider_response_code",
                "provider_response_description",
                "provider_raw_response",
                "status",
                "verification_message",
                "updated_at",
            ]
        )

        return JsonResponse(
            {
                "ResultCode": 0,
                "ResultDesc": "Callback received."
            }
        )

    # ------------------------------------------------------------
    # SUCCESS CALLBACK METADATA
    # ------------------------------------------------------------
    metadata = (
        callback
        .get("CallbackMetadata", {})
        .get("Item", [])
    )

    values = {}

    for item in metadata:
        name = item.get("Name")
        if name:
            values[name] = item.get("Value")

    provider_receipt = str(
        values.get("MpesaReceiptNumber", "") or ""
    ).strip()

    phone_number = str(
        values.get("PhoneNumber", "") or ""
    ).strip()

    provider_amount = values.get("Amount")

    # ------------------------------------------------------------
    # RECEIPT MUST EXIST
    # ------------------------------------------------------------
    if not provider_receipt:
        online_payment.status = "FAILED"
        online_payment.verification_message = (
            "Successful M-Pesa callback did not contain "
            "an M-Pesa receipt number."
        )

        online_payment.save(
            update_fields=[
                "merchant_request_id",
                "provider_response_code",
                "provider_response_description",
                "provider_raw_response",
                "status",
                "verification_message",
                "updated_at",
            ]
        )

        return JsonResponse(
            {
                "ResultCode": 0,
                "ResultDesc": "Callback received."
            }
        )

    # ------------------------------------------------------------
    # AMOUNT MUST EXIST
    # ------------------------------------------------------------
    if provider_amount is None:
        online_payment.status = "FAILED"
        online_payment.verification_message = (
            "Successful M-Pesa callback did not contain "
            "a payment amount."
        )

        online_payment.save(
            update_fields=[
                "merchant_request_id",
                "provider_response_code",
                "provider_response_description",
                "provider_raw_response",
                "status",
                "verification_message",
                "updated_at",
            ]
        )

        return JsonResponse(
            {
                "ResultCode": 0,
                "ResultDesc": "Callback received."
            }
        )

    # ------------------------------------------------------------
    # VERIFY AMOUNT
    # ------------------------------------------------------------
    from decimal import Decimal, InvalidOperation

    try:
        expected_amount = Decimal(
            str(online_payment.amount)
        )
        received_amount = Decimal(
            str(provider_amount)
        )
    except (InvalidOperation, ValueError, TypeError):
        online_payment.status = "FAILED"
        online_payment.verification_message = (
            "Invalid payment amount returned by M-Pesa."
        )

        online_payment.save(
            update_fields=[
                "merchant_request_id",
                "provider_response_code",
                "provider_response_description",
                "provider_raw_response",
                "status",
                "verification_message",
                "updated_at",
            ]
        )

        return JsonResponse(
            {
                "ResultCode": 0,
                "ResultDesc": "Callback received."
            }
        )

    if received_amount != expected_amount:
        online_payment.status = "FAILED"
        online_payment.provider_receipt = provider_receipt
        online_payment.transaction_reference = provider_receipt
        online_payment.phone_number = (
            online_payment.phone_number or phone_number
        )
        online_payment.verification_message = (
            f"M-Pesa amount mismatch. "
            f"Expected KSh {expected_amount:.2f}; "
            f"received KSh {received_amount:.2f}."
        )

        online_payment.save(
            update_fields=[
                "merchant_request_id",
                "provider_response_code",
                "provider_response_description",
                "provider_raw_response",
                "provider_receipt",
                "transaction_reference",
                "phone_number",
                "status",
                "verification_message",
                "updated_at",
            ]
        )

        return JsonResponse(
            {
                "ResultCode": 0,
                "ResultDesc": "Callback received."
            }
        )

    # ------------------------------------------------------------
    # STORE PROVIDER IDENTIFIERS
    # ------------------------------------------------------------
    online_payment.provider_receipt = provider_receipt
    online_payment.transaction_reference = provider_receipt
    online_payment.phone_number = (
        online_payment.phone_number or phone_number
    )

    # ------------------------------------------------------------
    # OFFICIAL FEE POSTING
    # ------------------------------------------------------------
    try:
        with transaction.atomic():

            mark_payment_verified(
                online_payment,
                provider_receipt=provider_receipt,
                transaction_reference=provider_receipt,
                provider_response_code=str(result_code),
                provider_response_description=result_description,
                provider_raw_response=payload,
            )

            online_payment.refresh_from_db()

            # ----------------------------------------------------
            # TILL AUTOMATIC VERIFICATION
            # ----------------------------------------------------
            # A Till STK payment uses the same OnlinePayment
            # record as normal M-Pesa Online. After the existing
            # verification succeeds, synchronize the Till intent.
            # This does NOT change the normal M-Pesa Online flow.
            try:
                from .models import TillPaymentIntent

                till_intent = (
                    TillPaymentIntent.objects
                    .filter(
                        online_payment=online_payment
                    )
                    .first()
                )

                if till_intent:
                    till_intent.status = "VERIFIED"
                    till_intent.transaction_id = (
                        provider_receipt
                    )
                    till_intent.transaction_time = str(
                        values.get(
                            "TransactionDate",
                            ""
                        ) or ""
                    )
                    till_intent.verified_at = timezone.now()
                    till_intent.notes = (
                        "Till payment automatically verified "
                        "from successful M-Pesa STK callback."
                    )
                    till_intent.save(
                        update_fields=[
                            "status",
                            "transaction_id",
                            "transaction_time",
                            "verified_at",
                            "notes",
                        ]
                    )

            except Exception:
                # Do not interfere with the successful
                # OnlinePayment verification if Till synchronization
                # encounters a temporary error.
                pass

            online_payment.merchant_request_id = (
                merchant_request_id
            )
            online_payment.provider_response_code = str(
                result_code
            )
            online_payment.provider_response_description = (
                result_description
            )
            online_payment.provider_raw_response = payload
            online_payment.provider_receipt = provider_receipt
            online_payment.transaction_reference = provider_receipt
            online_payment.phone_number = (
                online_payment.phone_number or phone_number
            )
            online_payment.verification_message = (
                "M-Pesa payment verified successfully. "
                "Official fee payment created."
            )

            online_payment.save(
                update_fields=[
                    "merchant_request_id",
                    "provider_response_code",
                    "provider_response_description",
                    "provider_raw_response",
                    "provider_receipt",
                    "transaction_reference",
                    "phone_number",
                    "verification_message",
                    "updated_at",
                ]
            )

    except OnlinePaymentError as exc:
        online_payment.status = "FAILED"
        online_payment.verification_message = str(exc)

        online_payment.save(
            update_fields=[
                "merchant_request_id",
                "provider_response_code",
                "provider_response_description",
                "provider_raw_response",
                "provider_receipt",
                "transaction_reference",
                "phone_number",
                "status",
                "verification_message",
                "updated_at",
            ]
        )

        return JsonResponse(
            {
                "ResultCode": 0,
                "ResultDesc": "Callback received."
            }
        )

    except Exception:
        # Preserve the successful provider callback.
        # Do not falsely mark a real M-Pesa payment as FAILED
        # because of a temporary ERP/database error.
        online_payment.status = "PROCESSING"
        online_payment.verification_message = (
            "M-Pesa callback received but ERP posting "
            "requires further processing."
        )

        online_payment.save(
            update_fields=[
                "merchant_request_id",
                "provider_response_code",
                "provider_response_description",
                "provider_raw_response",
                "provider_receipt",
                "transaction_reference",
                "phone_number",
                "status",
                "verification_message",
                "updated_at",
            ]
        )

        return JsonResponse(
            {
                "ResultCode": 0,
                "ResultDesc": "Callback received."
            }
        )

    return JsonResponse(
        {
            "ResultCode": 0,
            "ResultDesc": "Callback received."
        }
    )



def _unified_fee_data(year_id=None,term_id=None,annual=False):
    from django.db.models import Sum
    from .models import AcademicYear,Term,FeeStructure
    from transport.models import TransportFeeStructure
    year=AcademicYear.objects.filter(pk=year_id).first() if year_id else AcademicYear.objects.filter(is_active=True).order_by("-year").first()
    if not year:return None,[],[]
    terms=Term.objects.all().order_by("order")
    if term_id and not annual:terms=terms.filter(pk=term_id)
    school=list(FeeStructure.objects.filter(academic_year=year,is_active=True,term__in=terms).values("class_name").annotate(total=Sum("amount")).order_by("class_name"))
    transport=list(TransportFeeStructure.objects.filter(academic_year=year,is_active=True,term__in=terms).values("class_name","route__name","from_stop__name","to_stop__name").annotate(total=Sum("amount")).order_by("class_name","route__name","from_stop__stop_order"))
    return year,school,transport
@login_required
def unified_fee_structure(request):
    from .models import AcademicYear,Term
    annual=request.GET.get("annual")=="1";year,school,transport=_unified_fee_data(request.GET.get("year"),request.GET.get("term"),annual)
    return render(request,"fees/unified_fee_structure.html",{"year":year,"school_rows":school,"transport_rows":transport,"years":AcademicYear.objects.order_by("-year"),"terms":Term.objects.order_by("order"),"annual":annual,"selected_year":request.GET.get("year") or (year.id if year else ""),"selected_term":request.GET.get("term","")})
@login_required
def unified_fee_structure_excel(request):
    from django.http import HttpResponse
    from openpyxl import Workbook
    annual=request.GET.get("annual")=="1";year,school,transport=_unified_fee_data(request.GET.get("year"),request.GET.get("term"),annual)
    if not year:return HttpResponse("No academic year configured.",status=404)
    wb=Workbook();ws=wb.active;ws.title="School Fees";ws.append(["Academic Year","Class","School Fees Total"])
    for r in school:ws.append([year.year,r["class_name"],float(r["total"] or 0)])
    wt=wb.create_sheet("Transport Fees");wt.append(["Academic Year","Class","Route","From","To","Transport Total"])
    for r in transport:wt.append([year.year,r["class_name"] or "All classes",r["route__name"],r["from_stop__name"],r["to_stop__name"],float(r["total"] or 0)])
    out=HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");out["Content-Disposition"]=f'attachment; filename="fee_structure_{year.year}_{"annual" if annual else "termly"}.xlsx"';wb.save(out);return out
@login_required
def unified_fee_structure_pdf(request):
    from django.http import HttpResponse
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle
    annual=request.GET.get("annual")=="1";year,school,transport=_unified_fee_data(request.GET.get("year"),request.GET.get("term"),annual)
    if not year:return HttpResponse("No academic year configured.",status=404)
    out=HttpResponse(content_type="application/pdf");out["Content-Disposition"]=f'attachment; filename="fee_structure_{year.year}_{"annual" if annual else "termly"}.pdf"';doc=SimpleDocTemplate(out,pagesize=A4);st=getSampleStyleSheet()
    story=[Paragraph(f"School Fee Structure - {year.year}",st["Title"]),Paragraph("Annual" if annual else "Termly",st["Heading2"]),Spacer(1,12),Paragraph("School Fees",st["Heading2"])]
    d=[["Class","School Fees"]]+[[r["class_name"],f'{r["total"] or 0:,.2f}'] for r in school];t=Table(d,repeatRows=1);t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#102d63")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),.4,colors.grey)]));story+=[t,Spacer(1,12),Paragraph("Transport Fees",st["Heading2"])]
    d=[["Class","Route","From","To","Transport"]]+[[r["class_name"] or "All classes",r["route__name"],r["from_stop__name"],r["to_stop__name"],f'{r["total"] or 0:,.2f}'] for r in transport];t=Table(d,repeatRows=1);t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#102d63")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),.4,colors.grey)]));story.append(t);doc.build(story);return out
