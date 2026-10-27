from decimal import Decimal
from datetime import date
import calendar

from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import render
from django.http import JsonResponse

from fees.models import FeePayment, Term
from inventory.models import PurchaseLine
from transport.models import FuelRecord
from hr_payroll.models import PayrollRecord


def _filters(request):
    month = request.GET.get("month", "")
    year = request.GET.get("year", "")
    term_id = request.GET.get("term", "")

    try:
        month = int(month) if month else None
        if month and not 1 <= month <= 12:
            month = None
    except (ValueError, TypeError):
        month = None

    try:
        year = int(year) if year else None
    except (ValueError, TypeError):
        year = None

    try:
        term_id = int(term_id) if term_id else None
    except (ValueError, TypeError):
        term_id = None

    term = Term.objects.select_related("academic_year").filter(pk=term_id).first() if term_id else None
    return month, year, term


def _date_filter(queryset, field, month, year):
    if year:
        queryset = queryset.filter(**{f"{field}__year": year})
    if month:
        queryset = queryset.filter(**{f"{field}__month": month})
    return queryset


def _term_date_filter(queryset, field, term):
    if term:
        queryset = queryset.filter(
            **{
                f"{field}__gte": term.start_date,
                f"{field}__lte": term.end_date,
            }
        )
    return queryset


def _money(value):
    return value if value is not None else Decimal("0.00")


def _inventory_total(lines):
    total = Decimal("0.00")

    for line in lines:
        quantity = line.quantity or Decimal("0.00")
        unit_cost = line.unit_cost or Decimal("0.00")
        total += quantity * unit_cost

    return total


def _finance_chart_data(income_qs, inventory_qs, transport_qs, payroll_qs, chart_year):
    labels = [calendar.month_abbr[m] for m in range(1, 13)]
    income = [Decimal("0.00") for _ in range(12)]
    inventory = [Decimal("0.00") for _ in range(12)]
    transport = [Decimal("0.00") for _ in range(12)]
    salaries = [Decimal("0.00") for _ in range(12)]

    for row in income_qs:
        if row.payment_date and row.payment_date.year == chart_year:
            income[row.payment_date.month - 1] += row.amount or Decimal("0.00")

    for row in inventory_qs:
        d = row.purchase.purchase_date
        if d and d.year == chart_year:
            qty = row.quantity or Decimal("0.00")
            cost = row.unit_cost or Decimal("0.00")
            inventory[d.month - 1] += qty * cost

    for row in transport_qs:
        if row.date and row.date.year == chart_year:
            transport[row.date.month - 1] += row.cost or Decimal("0.00")

    for row in payroll_qs:
        d = row.payroll_period.start_date
        if d and d.year == chart_year:
            salaries[d.month - 1] += row.gross_salary or Decimal("0.00")

    expenses = [salaries[i] + inventory[i] + transport[i] for i in range(12)]
    net = [income[i] - expenses[i] for i in range(12)]

    return {
        "labels": labels,
        "income": [float(x) for x in income],
        "expenses": [float(x) for x in expenses],
        "net": [float(x) for x in net],
        "salaries": [float(x) for x in salaries],
        "inventory": [float(x) for x in inventory],
        "transport": [float(x) for x in transport],
    }
def _base_data(request):
    month, year, term = _filters(request)

    income_qs = _date_filter(
        FeePayment.objects.select_related(
            "fee_record",
            "fee_record__student",
        ),
        "payment_date",
        month,
        year,
    )

    inventory_qs = _date_filter(
        PurchaseLine.objects.select_related(
            "purchase",
            "purchase__supplier",
            "item",
        ),
        "purchase__purchase_date",
        month,
        year,
    )

    transport_qs = _date_filter(
        FuelRecord.objects.select_related("vehicle"),
        "date",
        month,
        year,
    )

    payroll_qs = _date_filter(
        PayrollRecord.objects.select_related(
            "employee",
            "payroll_period",
        ).filter(
            payroll_period__status__in=[
                "APPROVED",
                "PAID",
                "CLOSED",
            ]
        ),
        "payroll_period__start_date",
        month,
        year,
    )

    income = _money(
        income_qs.aggregate(total=Sum("amount"))["total"]
    )

    inventory = _inventory_total(inventory_qs)

    transport = _money(
        transport_qs.aggregate(total=Sum("cost"))["total"]
    )

    salaries = _money(
        payroll_qs.aggregate(total=Sum("gross_salary"))["total"]
    )

    expenses = salaries + inventory + transport
    net = income - expenses

    chart_year = year or (term.start_date.year if term else date.today().year)
    chart_data = _finance_chart_data(income_qs, inventory_qs, transport_qs, payroll_qs, chart_year)

    return {
        "income_qs": income_qs,
        "inventory_qs": inventory_qs,
        "transport_qs": transport_qs,
        "payroll_qs": payroll_qs,
        "income": income,
        "inventory": inventory,
        "transport": transport,
        "salaries": salaries,
        "expenses": expenses,
        "net": net,
        "chart_data": chart_data,
        "selected_month": month or "",
        "selected_year": year or "",
        "selected_term": term.id if term else "",
        "terms": Term.objects.select_related("academic_year").order_by("-academic_year_id", "order"),
    }


@login_required
def overview(request):
    data = _base_data(request)

    recent_income = data["income_qs"].order_by(
        "-payment_date",
        "-id",
    )[:10]

    recent_inventory = data["inventory_qs"].order_by(
        "-purchase__purchase_date",
        "-id",
    )[:10]

    recent_transport = data["transport_qs"].order_by(
        "-date",
        "-id",
    )[:10]

    recent_payroll = data["payroll_qs"].order_by(
        "-payroll_period__start_date",
        "-id",
    )[:10]

    data.update({
        "recent_income": recent_income,
        "recent_inventory": recent_inventory,
        "recent_transport": recent_transport,
        "recent_payroll": recent_payroll,
    })

    return render(
        request,
        "accounts/finance/overview.html",
        data,
    )


@login_required
def income(request):
    data = _base_data(request)

    payments = data["income_qs"].order_by(
        "-payment_date",
        "-id",
    )

    data["payments"] = payments

    return render(
        request,
        "accounts/finance/income.html",
        data,
    )


@login_required
def expenses(request):
    data = _base_data(request)

    inventory = data["inventory_qs"].order_by(
        "-purchase__purchase_date",
        "-id",
    )

    transport = data["transport_qs"].order_by(
        "-date",
        "-id",
    )

    payroll = data["payroll_qs"].order_by(
        "-payroll_period__start_date",
        "-id",
    )

    data.update({
        "inventory": inventory,
        "transport_records": transport,
        "payroll": payroll,
    })

    return render(
        request,
        "accounts/finance/expenses.html",
        data,
    )

@login_required
def live_data(request):
    data = _base_data(request)
    return JsonResponse({
        "income": float(data["income"]),
        "expenses": float(data["expenses"]),
        "net": float(data["net"]),
        "salaries": float(data["salaries"]),
        "inventory": float(data["inventory"]),
        "transport": float(data["transport"]),
        "chart_data": data["chart_data"],
    })
