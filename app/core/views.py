from .forms import EmployeeEditForm
from datetime import date, timedelta
from decimal import Decimal
import calendar
import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.utils import timezone
from django.contrib.auth.models import Group
from .forms import (DailySalesForm, EmployeeEarningForm, EmployeeCreateForm, ManagerEmployeeEarningForm, ManagerOtherEmployeeEarningsForm)
from .models import ActivityLog, DailySales, EmployeeEarning, Employee
from django.core.paginator import Paginator


def user_has_role(user, role):
    return user.groups.filter(name=role).exists()


def get_role(user):
    if user.is_superuser:
        return "Owner"

    if user_has_role(user, "Owner"):
        return "Owner"

    if user_has_role(user, "Manager"):
        return "Manager"

    if user_has_role(user, "Employee"):
        return "Employee"

    return "Unassigned"


@login_required
def dashboard(request):
    return render(
        request,
        "core/dashboard.html",
        {
            "role": get_role(request.user),
        },
    )


@login_required
def enter_today(request):

    role = get_role(request.user)

    if role not in ["Employee", "Manager"]:
        return HttpResponseForbidden(
            "You do not have permission to enter daily data."
        )

    try:
        employee = request.user.employee_profile
    except Exception:
        messages.error(
            request,
            "No employee record is associated with this account."
        )
        return redirect("dashboard")

    if not employee.is_active:
        messages.error(
            request,
            "This employee account is inactive."
        )
        return redirect("dashboard")

    business_date = timezone.localdate()

    daily_sales = DailySales.objects.filter(
        business_date=business_date
    ).first()

    earning = (
        EmployeeEarning.objects.filter(
            daily_sales=daily_sales,
            employee=employee,
        ).first()
        if daily_sales
        else None
    )

    is_manager = role == "Manager"

    sales_locked = daily_sales is not None and not is_manager
    earnings_locked = earning is not None and not is_manager

    if request.method == "POST":

        sales_form = DailySalesForm(
            request.POST,
            instance=daily_sales,
            prefix="sales",
        )

        earning_form = EmployeeEarningForm(
            request.POST,
            instance=earning,
            prefix="earning",
        )

        sales_valid = True

        if not sales_locked:
            sales_valid = sales_form.is_valid()

        earnings_valid = True

        if not earnings_locked:
            earnings_valid = earning_form.is_valid()

        if sales_valid and earnings_valid:

            with transaction.atomic():

                if not sales_locked:

                    previous_cash = (
                        daily_sales.cash_sales
                        if daily_sales
                        else None
                    )

                    previous_card = (
                        daily_sales.credit_card_sales
                        if daily_sales
                        else None
                    )

                    sales = sales_form.save(commit=False)

                    if daily_sales is None:
                        sales.business_date = business_date
                        sales.entered_by = request.user
                        sales.save()

                        ActivityLog.objects.create(
                            actor=request.user,
                            action=ActivityLog.Action.CREATE,
                            object_type="DailySales",
                            object_id=str(sales.id),
                            description=(
                                f"Daily sales created for "
                                f"{business_date}."
                            ),
                            details={
                                "cash_sales": str(
                                    sales.cash_sales
                                ),
                                "credit_card_sales": str(
                                    sales.credit_card_sales
                                ),
                            },
                        )

                    else:
                        sales.last_modified_by = request.user
                        sales.save()

                        if (
                            previous_cash != sales.cash_sales
                            or previous_card
                            != sales.credit_card_sales
                        ):
                            ActivityLog.objects.create(
                                actor=request.user,
                                action=ActivityLog.Action.UPDATE,
                                object_type="DailySales",
                                object_id=str(sales.id),
                                description=(
                                    f"Daily sales corrected for "
                                    f"{business_date}."
                                ),
                                details={
                                    "previous_cash_sales":
                                        str(previous_cash),
                                    "new_cash_sales":
                                        str(sales.cash_sales),
                                    "previous_credit_card_sales":
                                        str(previous_card),
                                    "new_credit_card_sales":
                                        str(
                                            sales.credit_card_sales
                                        ),
                                },
                            )

                    daily_sales = sales

                else:
                    daily_sales = DailySales.objects.get(
                        business_date=business_date
                    )

                if not earnings_locked:

                    previous_values = None

                    if earning:
                        previous_values = {
                            "cash_pay": str(
                                earning.cash_pay
                            ),
                            "card_tips": str(
                                earning.card_tips
                            ),
                            "cash_tips": str(
                                earning.cash_tips
                            ),
                        }

                    employee_earning = (
                        earning_form.save(commit=False)
                    )

                    employee_earning.daily_sales = daily_sales
                    employee_earning.employee = employee

                    if earning is None:
                        employee_earning.entered_by = request.user
                    else:
                        employee_earning.last_modified_by = (
                            request.user
                        )

                    employee_earning.save()

                    if earning is None:

                        ActivityLog.objects.create(
                            actor=request.user,
                            action=ActivityLog.Action.CREATE,
                            object_type="EmployeeEarning",
                            object_id=str(
                                employee_earning.id
                            ),
                            description=(
                                f"Earnings submitted for "
                                f"{employee.employee_number} "
                                f"on {business_date}."
                            ),
                            details={
                                "employee":
                                    employee.employee_number,
                                "cash_pay":
                                    str(
                                        employee_earning.cash_pay
                                    ),
                                "card_tips":
                                    str(
                                        employee_earning.card_tips
                                    ),
                                "cash_tips":
                                    str(
                                        employee_earning.cash_tips
                                    ),
                            },
                        )

                    else:

                        ActivityLog.objects.create(
                            actor=request.user,
                            action=ActivityLog.Action.UPDATE,
                            object_type="EmployeeEarning",
                            object_id=str(
                                employee_earning.id
                            ),
                            description=(
                                f"Earnings corrected for "
                                f"{employee.employee_number} "
                                f"on {business_date}."
                            ),
                            details={
                                "previous": previous_values,
                                "new": {
                                    "cash_pay":
                                        str(
                                            employee_earning.cash_pay
                                        ),
                                    "card_tips":
                                        str(
                                            employee_earning.card_tips
                                        ),
                                    "cash_tips":
                                        str(
                                            employee_earning.cash_tips
                                        ),
                                },
                            },
                        )

            messages.success(
                request,
                "Today's data was saved successfully."
            )

            return redirect("enter_today")

    else:

        sales_form = DailySalesForm(
            instance=daily_sales,
            prefix="sales",
        )

        earning_form = EmployeeEarningForm(
            instance=earning,
            prefix="earning",
        )
    manager_employee_form = None

    if role == "Manager":
        manager_employee_form = ManagerOtherEmployeeEarningsForm(
            current_employee=employee
        )

    return render(
        request,
        "core/enter_today.html",
            {
            "employee": employee,
            "role": role,
            "business_date": business_date,
            "sales_form": sales_form,
            "earning_form": earning_form,
            "daily_sales": daily_sales,
            "earning": earning,
            "sales_locked": sales_locked,
            "earnings_locked": earnings_locked,
            "manager_employee_form": manager_employee_form,
        },
    )


@login_required
def reports(request, period="weekly"):

    role = get_role(request.user)

    if role not in ["Manager", "Owner"]:
        return HttpResponseForbidden(
            "You do not have permission to view reports."
        )

    valid_periods = {
        "daily",
        "weekly",
        "monthly",
        "ytd",
    }

    if period not in valid_periods:
        raise Http404("Report type not found.")

    today = timezone.localdate()

    requested_date = request.GET.get("date")

    if requested_date:
        try:
            anchor_date = date.fromisoformat(requested_date)
        except ValueError:
            anchor_date = today
    else:
        anchor_date = today

    if period == "daily":
        start_date = anchor_date
        end_date = anchor_date
        report_title = "Daily Report"

    elif period == "weekly":
        start_date = (
            anchor_date
            - timedelta(days=anchor_date.weekday())
        )

        end_date = start_date + timedelta(days=6)

        report_title = "Weekly Report"

    elif period == "monthly":
        start_date = anchor_date.replace(day=1)

        last_day = calendar.monthrange(
            anchor_date.year,
            anchor_date.month,
        )[1]

        end_date = anchor_date.replace(day=last_day)

        report_title = "Monthly Report"

    else:
        start_date = anchor_date.replace(
            month=1,
            day=1,
        )

        end_date = anchor_date

        report_title = "Year-to-Date Report"

    sales_records = (
        DailySales.objects
        .filter(
            business_date__range=(
                start_date,
                end_date,
            )
        )
        .prefetch_related(
            "employee_earnings__employee__user"
        )
        .order_by("-business_date")
    )

    zero = Decimal("0.00")

    summary = {
        "cash_sales": zero,
        "credit_card_sales": zero,
        "total_sales": zero,
        "employee_pay": zero,
        "card_tips": zero,
        "cash_tips": zero,
        "employee_earnings": zero,
        "expected_cash_deposit": zero,
        "gross_card_batch": zero,
        "net_daily_proceeds": zero,
    }

    daily_rows = []
    employee_totals = {}

    for sales in sales_records:

        earnings = list(
            sales.employee_earnings.all()
        )

        employee_pay = sum(
            (
                earning.cash_pay
                for earning in earnings
            ),
            zero,
        )

        card_tips = sum(
            (
                earning.card_tips
                for earning in earnings
            ),
            zero,
        )

        cash_tips = sum(
            (
                earning.cash_tips
                for earning in earnings
            ),
            zero,
        )

        total_sales = (
            sales.cash_sales
            + sales.credit_card_sales
        )

        employee_earnings = (
            employee_pay
            + card_tips
            + cash_tips
        )

        expected_cash_deposit = (
            sales.cash_sales
            - employee_pay
            - card_tips
        )

        gross_card_batch = (
            sales.credit_card_sales
            + card_tips
        )

        net_daily_proceeds = (
            sales.cash_sales
            + sales.credit_card_sales
            - employee_pay
        )

        daily_rows.append(
            {
                "business_date":
                    sales.business_date,
                "cash_sales":
                    sales.cash_sales,
                "credit_card_sales":
                    sales.credit_card_sales,
                "total_sales":
                    total_sales,
                "employee_pay":
                    employee_pay,
                "card_tips":
                    card_tips,
                "cash_tips":
                    cash_tips,
                "expected_cash_deposit":
                    expected_cash_deposit,
                "gross_card_batch":
                    gross_card_batch,
                "net_daily_proceeds":
                    net_daily_proceeds,
            }
        )

        summary["cash_sales"] += (
            sales.cash_sales
        )

        summary["credit_card_sales"] += (
            sales.credit_card_sales
        )

        summary["total_sales"] += (
            total_sales
        )

        summary["employee_pay"] += (
            employee_pay
        )

        summary["card_tips"] += (
            card_tips
        )

        summary["cash_tips"] += (
            cash_tips
        )

        summary["employee_earnings"] += (
            employee_earnings
        )

        summary["expected_cash_deposit"] += (
            expected_cash_deposit
        )

        summary["gross_card_batch"] += (
            gross_card_batch
        )

        summary["net_daily_proceeds"] += (
            net_daily_proceeds
        )

        for earning in earnings:

            employee = earning.employee

            if employee.id not in employee_totals:

                if employee.user:
                    employee_name = (
                        employee.user.get_full_name().strip()
                        or employee.user.username
                    )
                else:
                    employee_name = (
                        employee.employee_number
                    )

                employee_totals[employee.id] = {
                    "employee_number":
                        employee.employee_number,
                    "name":
                        employee_name,
                    "cash_pay":
                        zero,
                    "card_tips":
                        zero,
                    "cash_tips":
                        zero,
                    "total_earnings":
                        zero,
                }

            record = employee_totals[
                employee.id
            ]

            record["cash_pay"] += (
                earning.cash_pay
            )

            record["card_tips"] += (
                earning.card_tips
            )

            record["cash_tips"] += (
                earning.cash_tips
            )

            record["total_earnings"] += (
                earning.total_earnings
            )

    employee_rows = sorted(
        employee_totals.values(),
        key=lambda item: item["employee_number"],
    )

    return render(
        request,
        "core/reports.html",
        {
            "role": role,
            "period": period,
            "report_title": report_title,
            "anchor_date": anchor_date,
            "start_date": start_date,
            "end_date": end_date,
            "summary": summary,
            "daily_rows": daily_rows,
            "employee_rows": employee_rows,
        },
    )


@login_required
def employee_earnings_report(request, period="monthly"):
    """
    Self-service earnings report.

    The employee is determined exclusively from the authenticated
    Django user. No employee ID is accepted from the URL or form.
    """

    role = get_role(request.user)

    if role not in ["Employee", "Manager"]:
        return HttpResponseForbidden(
            "You do not have permission to view an employee earnings report."
        )

    try:
        employee = request.user.employee_profile
    except Exception:
        return HttpResponseForbidden(
            "No employee record is associated with this account."
        )

    valid_periods = {
        "weekly",
        "monthly",
        "ytd",
        "yearly",
        "custom",
    }

    if period not in valid_periods:
        raise Http404("Report type not found.")

    today = timezone.localdate()

    requested_date = request.GET.get("date")

    if requested_date:
        try:
            anchor_date = date.fromisoformat(requested_date)
        except ValueError:
            anchor_date = today
    else:
        anchor_date = today

    #
    # Determine report date range.
    #
    if period == "weekly":

        start_date = (
            anchor_date
            - timedelta(days=anchor_date.weekday())
        )

        end_date = start_date + timedelta(days=6)

        report_title = "Weekly Earnings Report"


    elif period == "monthly":

        start_date = anchor_date.replace(day=1)

        last_day = calendar.monthrange(
            anchor_date.year,
            anchor_date.month,
        )[1]

        end_date = anchor_date.replace(
            day=last_day
        )

        report_title = "Monthly Earnings Report"


    elif period == "ytd":

        start_date = today.replace(
            month=1,
            day=1,
        )

        end_date = today

        anchor_date = today

        report_title = "Year-to-Date Earnings Report"


    elif period == "yearly":

        start_date = anchor_date.replace(
            month=1,
            day=1,
        )

        end_date = anchor_date.replace(
            month=12,
            day=31,
        )

        report_title = (
            f"{anchor_date.year} Earnings Report"
        )


    else:

        requested_start = request.GET.get(
            "start"
        )

        requested_end = request.GET.get(
            "end"
        )

        try:
            start_date = (
                date.fromisoformat(requested_start)
                if requested_start
                else today.replace(day=1)
            )
        except ValueError:
            start_date = today.replace(day=1)

        try:
            end_date = (
                date.fromisoformat(requested_end)
                if requested_end
                else today
            )
        except ValueError:
            end_date = today

        if start_date > end_date:
            start_date, end_date = (
                end_date,
                start_date,
            )

        report_title = "Custom Earnings Report"


    #
    # Fetch ONLY the currently logged-in employee's records.
    #
    earnings = (
        EmployeeEarning.objects
        .filter(
            employee=employee,
            daily_sales__business_date__range=(
                start_date,
                end_date,
            ),
        )
        .select_related(
            "daily_sales",
        )
        .order_by(
            "daily_sales__business_date"
        )
    )


    zero = Decimal("0.00")

    cash_pay = sum(
        (
            entry.cash_pay
            for entry in earnings
        ),
        zero,
    )

    card_tips = sum(
        (
            entry.card_tips
            for entry in earnings
        ),
        zero,
    )

    cash_tips = sum(
        (
            entry.cash_tips
            for entry in earnings
        ),
        zero,
    )

    total_tips = (
        card_tips
        + cash_tips
    )

    total_earnings = (
        cash_pay
        + total_tips
    )


    rows = [
        {
            "business_date":
                entry.daily_sales.business_date,

            "cash_pay":
                entry.cash_pay,

            "card_tips":
                entry.card_tips,

            "cash_tips":
                entry.cash_tips,

            "total_tips":
                entry.card_tips
                + entry.cash_tips,

            "total_earnings":
                entry.total_earnings,
        }

        for entry in earnings
    ]


    if employee.user:
        employee_name = (
            employee.user.get_full_name().strip()
            or employee.user.username
        )
    else:
        employee_name = employee.employee_number


    return render(
        request,
        "core/employee_earnings_report.html",
        {
            "employee": employee,
            "employee_name": employee_name,

            "period": period,
            "report_title": report_title,

            "anchor_date": anchor_date,
            "start_date": start_date,
            "end_date": end_date,

            "cash_pay": cash_pay,
            "card_tips": card_tips,
            "cash_tips": cash_tips,
            "total_tips": total_tips,
            "total_earnings": total_earnings,

            "days_recorded": len(rows),
            "rows": rows,

            "generated_at": timezone.localtime(),
        },
    )

@login_required
def activity_log(request):

    role = get_role(request.user)

    if role != "Manager" and not request.user.is_superuser:
        return HttpResponseForbidden(
            "You do not have permission to view the activity log."
        )

    logs = (
        ActivityLog.objects
        .select_related("actor")
        .all()
    )

    #
    # Optional filters
    #
    selected_action = request.GET.get("action", "")
    selected_actor = request.GET.get("actor", "")

    if selected_action:
        logs = logs.filter(
            action=selected_action
        )

    if selected_actor:
        logs = logs.filter(
            actor__username=selected_actor
        )

    actor_options = (
        ActivityLog.objects
        .exclude(actor__isnull=True)
        .values_list(
            "actor__username",
            flat=True,
        )
        .distinct()
        .order_by("actor__username")
    )

    #
    # Convert JSON details into readable text.
    #
    log_rows = []

    for log in logs:
        log.details_pretty = json.dumps(
            log.details,
            indent=2,
            sort_keys=True,
        )

        log_rows.append(log)

    paginator = Paginator(
        log_rows,
        50,
    )

    page_number = request.GET.get("page")

    page_obj = paginator.get_page(
        page_number
    )

    return render(
        request,
        "core/activity_log.html",
        {
            "page_obj": page_obj,
            "action_options":
                ActivityLog.Action.choices,
            "actor_options":
                actor_options,
            "selected_action":
                selected_action,
            "selected_actor":
                selected_actor,
        },
    )

@login_required
def employees(request):

    role = get_role(request.user)

    if role not in ["Manager", "Owner"]:
        return HttpResponseForbidden(
            "You do not have permission to view employees."
        )

    can_manage = (
        role == "Manager"
        or request.user.is_superuser
    )

    employee_list = (
        Employee.objects
        .select_related("user")
        .order_by(
            "-is_active",
            "employee_number",
        )
    )

    create_form = EmployeeCreateForm()

    if request.method == "POST":

        if not can_manage:
            return HttpResponseForbidden(
                "You do not have permission to add employees."
            )

        create_form = EmployeeCreateForm(
            request.POST
        )

        if create_form.is_valid():

            with transaction.atomic():

                user = request.user.__class__.objects.create(
                    username=create_form.cleaned_data[
                        "username"
                    ],
                    first_name=create_form.cleaned_data[
                        "first_name"
                    ],
                    last_name=create_form.cleaned_data[
                        "last_name"
                    ],
                    is_active=True,
                )

                user.set_password(
                    create_form.cleaned_data[
                        "password"
                    ]
                )

                user.save()

                employee_group, _ = (
                    Group.objects.get_or_create(
                        name="Employee"
                    )
                )

                user.groups.add(
                    employee_group
                )

                employee = Employee.objects.create(
                    user=user,
                    employee_number=(
                        create_form.cleaned_data[
                            "employee_number"
                        ]
                    ),
                    job_title=(
                        create_form.cleaned_data[
                            "job_title"
                        ]
                    ),
                    employment_type=(
                        create_form.cleaned_data[
                            "employment_type"
                        ]
                    ),
                    hire_date=(
                        create_form.cleaned_data[
                            "hire_date"
                        ]
                    ),
                    is_active=True,
                )

                ActivityLog.objects.create(
                    actor=request.user,
                    action=(
                        ActivityLog.Action.EMPLOYEE_ADD
                    ),
                    object_type="Employee",
                    object_id=str(employee.id),
                    description=(
                        f"Employee "
                        f"{employee.employee_number} "
                        f"was added."
                    ),
                    details={
                        "employee_number":
                            employee.employee_number,
                        "username":
                            user.username,
                        "name":
                            user.get_full_name(),
                        "job_title":
                            employee.job_title,
                    },
                )

            messages.success(
                request,
                "Employee added successfully."
            )

            return redirect("employees")

    return render(
        request,
        "core/employees.html",
        {
            "employees": employee_list,
            "create_form": create_form,
            "can_manage": can_manage,
        },
    )


@login_required
def deactivate_employee(request, employee_id):

    role = get_role(request.user)

    if (
        role != "Manager"
        and not request.user.is_superuser
    ):
        return HttpResponseForbidden(
            "You do not have permission to deactivate employees."
        )

    if request.method != "POST":
        return redirect("employees")

    try:
        employee = (
            Employee.objects
            .select_related("user")
            .get(id=employee_id)
        )
    except Employee.DoesNotExist:
        raise Http404("Employee not found.")

    if employee.user == request.user:
        messages.error(
            request,
            "You cannot deactivate your own account."
        )
        return redirect("employees")

    if not employee.is_active:
        messages.warning(
            request,
            "That employee is already inactive."
        )
        return redirect("employees")

    with transaction.atomic():

        employee.is_active = False
        employee.save(
            update_fields=[
                "is_active",
                "updated_at",
            ]
        )

        if employee.user:
            employee.user.is_active = False
            employee.user.save(
                update_fields=["is_active"]
            )

        ActivityLog.objects.create(
            actor=request.user,
            action=(
                ActivityLog.Action.EMPLOYEE_DEACTIVATE
            ),
            object_type="Employee",
            object_id=str(employee.id),
            description=(
                f"Employee "
                f"{employee.employee_number} "
                f"was deactivated."
            ),
            details={
                "employee_number":
                    employee.employee_number,
                "username":
                    (
                        employee.user.username
                        if employee.user
                        else ""
                    ),
            },
        )

    messages.success(
        request,
        "Employee deactivated successfully."
    )

    return redirect("employees")



@login_required
def employees(request):

    role = get_role(request.user)

    if role not in ["Manager", "Owner"]:
        return HttpResponseForbidden(
            "You do not have permission to view employees."
        )

    can_manage = (
        role == "Manager"
        or request.user.is_superuser
    )

    employee_list = (
        Employee.objects
        .select_related("user")
        .order_by(
            "-is_active",
            "employee_number",
        )
    )

    create_form = EmployeeCreateForm()

    if request.method == "POST":

        if not can_manage:
            return HttpResponseForbidden(
                "You do not have permission to add employees."
            )

        create_form = EmployeeCreateForm(
            request.POST
        )

        if create_form.is_valid():

            with transaction.atomic():

                user = request.user.__class__.objects.create(
                    username=create_form.cleaned_data[
                        "username"
                    ],
                    first_name=create_form.cleaned_data[
                        "first_name"
                    ],
                    last_name=create_form.cleaned_data[
                        "last_name"
                    ],
                    is_active=True,
                )

                user.set_password(
                    create_form.cleaned_data[
                        "password"
                    ]
                )

                user.save()

                employee_group, _ = (
                    Group.objects.get_or_create(
                        name="Employee"
                    )
                )

                user.groups.add(
                    employee_group
                )

                employee = Employee.objects.create(
                    user=user,
                    employee_number=(
                        create_form.cleaned_data[
                            "employee_number"
                        ]
                    ),
                    job_title=(
                        create_form.cleaned_data[
                            "job_title"
                        ]
                    ),
                    employment_type=(
                        create_form.cleaned_data[
                            "employment_type"
                        ]
                    ),
                    hire_date=(
                        create_form.cleaned_data[
                            "hire_date"
                        ]
                    ),
                    is_active=True,
                )

                ActivityLog.objects.create(
                    actor=request.user,
                    action=(
                        ActivityLog.Action.EMPLOYEE_ADD
                    ),
                    object_type="Employee",
                    object_id=str(employee.id),
                    description=(
                        f"Employee "
                        f"{employee.employee_number} "
                        f"was added."
                    ),
                    details={
                        "employee_number":
                            employee.employee_number,
                        "username":
                            user.username,
                        "name":
                            user.get_full_name(),
                        "job_title":
                            employee.job_title,
                    },
                )

            messages.success(
                request,
                "Employee added successfully."
            )

            return redirect("employees")

    return render(
        request,
        "core/employees.html",
        {
            "employees": employee_list,
            "create_form": create_form,
            "can_manage": can_manage,
        },
    )


@login_required
def deactivate_employee(request, employee_id):

    role = get_role(request.user)

    if (
        role != "Manager"
        and not request.user.is_superuser
    ):
        return HttpResponseForbidden(
            "You do not have permission to deactivate employees."
        )

    if request.method != "POST":
        return redirect("employees")

    try:
        employee = (
            Employee.objects
            .select_related("user")
            .get(id=employee_id)
        )
    except Employee.DoesNotExist:
        raise Http404("Employee not found.")

    if employee.user == request.user:
        messages.error(
            request,
            "You cannot deactivate your own account."
        )
        return redirect("employees")

    if not employee.is_active:
        messages.warning(
            request,
            "That employee is already inactive."
        )
        return redirect("employees")

    with transaction.atomic():

        employee.is_active = False
        employee.save(
            update_fields=[
                "is_active",
                "updated_at",
            ]
        )

        if employee.user:
            employee.user.is_active = False
            employee.user.save(
                update_fields=["is_active"]
            )

        ActivityLog.objects.create(
            actor=request.user,
            action=(
                ActivityLog.Action.EMPLOYEE_DEACTIVATE
            ),
            object_type="Employee",
            object_id=str(employee.id),
            description=(
                f"Employee "
                f"{employee.employee_number} "
                f"was deactivated."
            ),
            details={
                "employee_number":
                    employee.employee_number,
                "username":
                    (
                        employee.user.username
                        if employee.user
                        else ""
                    ),
            },
        )

    messages.success(
        request,
        "Employee deactivated successfully."
    )

    return redirect("employees")


@login_required
def manager_employee_earnings(request):

    role = get_role(request.user)

    if role != "Manager" and not request.user.is_superuser:
        return HttpResponseForbidden(
            "You do not have permission to enter employee earnings."
        )

    if request.method == "POST":

        form = ManagerEmployeeEarningForm(request.POST)

        if form.is_valid():

            business_date = form.cleaned_data["business_date"]
            employee = form.cleaned_data["employee"]

            try:
                daily_sales = DailySales.objects.get(
                    business_date=business_date
                )

            except DailySales.DoesNotExist:
                form.add_error(
                    "business_date",
                    "No sales record exists for this date. "
                    "Daily sales must be entered first."
                )

            else:
                existing = (
                    EmployeeEarning.objects
                    .filter(
                        daily_sales=daily_sales,
                        employee=employee,
                    )
                    .first()
                )

                new_values = {
                    "cash_pay": form.cleaned_data["cash_pay"],
                    "card_tips": form.cleaned_data["card_tips"],
                    "cash_tips": form.cleaned_data["cash_tips"],
                }

                with transaction.atomic():

                    if existing:

                        previous_values = {
                            "cash_pay": str(existing.cash_pay),
                            "card_tips": str(existing.card_tips),
                            "cash_tips": str(existing.cash_tips),
                        }

                        changed = (
                            existing.cash_pay != new_values["cash_pay"]
                            or existing.card_tips != new_values["card_tips"]
                            or existing.cash_tips != new_values["cash_tips"]
                        )

                        existing.cash_pay = new_values["cash_pay"]
                        existing.card_tips = new_values["card_tips"]
                        existing.cash_tips = new_values["cash_tips"]
                        existing.last_modified_by = request.user

                        existing.save()

                        if changed:
                            ActivityLog.objects.create(
                                actor=request.user,
                                action=ActivityLog.Action.UPDATE,
                                object_type="EmployeeEarning",
                                object_id=str(existing.id),
                                description=(
                                    f"Manager corrected earnings for "
                                    f"{employee.employee_number} "
                                    f"on {business_date}."
                                ),
                                details={
                                    "employee": employee.employee_number,
                                    "previous": previous_values,
                                    "new": {
                                        "cash_pay": str(existing.cash_pay),
                                        "card_tips": str(existing.card_tips),
                                        "cash_tips": str(existing.cash_tips),
                                    },
                                },
                            )

                    else:

                        earning = EmployeeEarning.objects.create(
                            daily_sales=daily_sales,
                            employee=employee,
                            cash_pay=new_values["cash_pay"],
                            card_tips=new_values["card_tips"],
                            cash_tips=new_values["cash_tips"],
                            entered_by=request.user,
                        )

                        ActivityLog.objects.create(
                            actor=request.user,
                            action=ActivityLog.Action.CREATE,
                            object_type="EmployeeEarning",
                            object_id=str(earning.id),
                            description=(
                                f"Manager entered earnings for "
                                f"{employee.employee_number} "
                                f"on {business_date}."
                            ),
                            details={
                                "employee": employee.employee_number,
                                "cash_pay": str(earning.cash_pay),
                                "card_tips": str(earning.card_tips),
                                "cash_tips": str(earning.cash_tips),
                            },
                        )

                messages.success(
                    request,
                    f"Earnings saved for {employee}."
                )

                return redirect("manager_employee_earnings")

    else:

        form = ManagerEmployeeEarningForm(
            initial={
                "business_date": timezone.localdate(),
            }
        )

    return render(
        request,
        "core/manager_employee_earnings.html",
        {
            "form": form,
        },
    )


@login_required
def manager_add_employee_earnings(request):

    role = get_role(request.user)

    if role != "Manager" and not request.user.is_superuser:
        return HttpResponseForbidden(
            "You do not have permission to enter earnings "
            "for other employees."
        )

    if request.method != "POST":
        return redirect("enter_today")

    try:
        current_employee = request.user.employee_profile
    except Exception:
        current_employee = None

    form = ManagerOtherEmployeeEarningsForm(
        request.POST,
        current_employee=current_employee,
    )

    if not form.is_valid():

        for error in form.non_field_errors():
            messages.error(request, error)

        for field_errors in form.errors.values():
            for error in field_errors:
                messages.error(request, error)

        return redirect("enter_today")

    business_date = timezone.localdate()

    try:
        daily_sales = DailySales.objects.get(
            business_date=business_date
        )

    except DailySales.DoesNotExist:

        messages.error(
            request,
            "Today's sales must be entered before employee "
            "pay and tips can be recorded."
        )

        return redirect("enter_today")

    employee = form.cleaned_data["employee"]

    cash_pay = form.cleaned_data["cash_pay"]
    card_tips = form.cleaned_data["card_tips"]
    cash_tips = form.cleaned_data["cash_tips"]

    with transaction.atomic():

        earning = (
            EmployeeEarning.objects
            .filter(
                daily_sales=daily_sales,
                employee=employee,
            )
            .first()
        )

        if earning:

            previous_values = {
                "cash_pay": str(earning.cash_pay),
                "card_tips": str(earning.card_tips),
                "cash_tips": str(earning.cash_tips),
            }

            changed = (
                earning.cash_pay != cash_pay
                or earning.card_tips != card_tips
                or earning.cash_tips != cash_tips
            )

            earning.cash_pay = cash_pay
            earning.card_tips = card_tips
            earning.cash_tips = cash_tips
            earning.last_modified_by = request.user

            earning.save()

            if changed:

                ActivityLog.objects.create(
                    actor=request.user,
                    action=ActivityLog.Action.UPDATE,
                    object_type="EmployeeEarning",
                    object_id=str(earning.id),
                    description=(
                        f"Manager updated earnings for "
                        f"{employee.employee_number} "
                        f"on {business_date}."
                    ),
                    details={
                        "employee":
                            employee.employee_number,

                        "previous":
                            previous_values,

                        "new": {
                            "cash_pay":
                                str(earning.cash_pay),

                            "card_tips":
                                str(earning.card_tips),

                            "cash_tips":
                                str(earning.cash_tips),
                        },
                    },
                )

        else:

            earning = EmployeeEarning.objects.create(
                daily_sales=daily_sales,
                employee=employee,
                cash_pay=cash_pay,
                card_tips=card_tips,
                cash_tips=cash_tips,
                entered_by=request.user,
            )

            ActivityLog.objects.create(
                actor=request.user,
                action=ActivityLog.Action.CREATE,
                object_type="EmployeeEarning",
                object_id=str(earning.id),
                description=(
                    f"Manager entered earnings for "
                    f"{employee.employee_number} "
                    f"on {business_date}."
                ),
                details={
                    "employee":
                        employee.employee_number,

                    "cash_pay":
                        str(earning.cash_pay),

                    "card_tips":
                        str(earning.card_tips),

                    "cash_tips":
                        str(earning.cash_tips),
                },
            )

    messages.success(
        request,
        f"Pay and tips saved for {employee}."
    )

    return redirect("enter_today")


@login_required
def edit_employee(request, employee_id):

    role = get_role(request.user)

    if (
        role != "Manager"
        and not request.user.is_superuser
    ):
        return HttpResponseForbidden(
            "You do not have permission to edit employees."
        )

    try:
        employee = (
            Employee.objects
            .select_related("user")
            .get(id=employee_id)
        )

    except Employee.DoesNotExist:
        raise Http404("Employee not found.")

    if request.method == "POST":

        form = EmployeeEditForm(
            request.POST,
            employee=employee,
        )

        if form.is_valid():

            previous = {
                "username": (
                    employee.user.username
                    if employee.user
                    else ""
                ),
                "first_name": (
                    employee.user.first_name
                    if employee.user
                    else ""
                ),
                "last_name": (
                    employee.user.last_name
                    if employee.user
                    else ""
                ),
                "employee_number":
                    employee.employee_number,
                "job_title":
                    employee.job_title,
                "employment_type":
                    employee.employment_type,
                "hire_date": (
                    str(employee.hire_date)
                    if employee.hire_date
                    else None
                ),
            }

            with transaction.atomic():

                if employee.user:

                    employee.user.username = (
                        form.cleaned_data["username"]
                    )

                    employee.user.first_name = (
                        form.cleaned_data["first_name"]
                    )

                    employee.user.last_name = (
                        form.cleaned_data["last_name"]
                    )

                    employee.user.save()

                employee.employee_number = (
                    form.cleaned_data[
                        "employee_number"
                    ]
                )

                employee.job_title = (
                    form.cleaned_data[
                        "job_title"
                    ]
                )

                employee.employment_type = (
                    form.cleaned_data[
                        "employment_type"
                    ]
                )

                employee.hire_date = (
                    form.cleaned_data[
                        "hire_date"
                    ]
                )

                employee.save()

                new_values = {
                    "username": (
                        employee.user.username
                        if employee.user
                        else ""
                    ),
                    "first_name": (
                        employee.user.first_name
                        if employee.user
                        else ""
                    ),
                    "last_name": (
                        employee.user.last_name
                        if employee.user
                        else ""
                    ),
                    "employee_number":
                        employee.employee_number,
                    "job_title":
                        employee.job_title,
                    "employment_type":
                        employee.employment_type,
                    "hire_date": (
                        str(employee.hire_date)
                        if employee.hire_date
                        else None
                    ),
                }

                ActivityLog.objects.create(
                    actor=request.user,
                    action=ActivityLog.Action.UPDATE,
                    object_type="Employee",
                    object_id=str(employee.id),
                    description=(
                        f"Employee "
                        f"{employee.employee_number} "
                        f"was updated."
                    ),
                    details={
                        "previous": previous,
                        "new": new_values,
                    },
                )

            messages.success(
                request,
                "Employee updated successfully."
            )

            return redirect("employees")

    else:

        form = EmployeeEditForm(
            employee=employee
        )

    return render(
        request,
        "core/employee_edit.html",
        {
            "employee": employee,
            "form": form,
        },
    )
