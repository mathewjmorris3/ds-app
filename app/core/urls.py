from django.urls import path

from . import views


urlpatterns = [

    path(
        "",
        views.dashboard,
        name="dashboard",
    ),

    path(
        "today/",
        views.enter_today,
        name="enter_today",
    ),

    path(
        "reports/",
        views.reports,
        name="reports",
    ),

    path(
        "reports/<str:period>/",
        views.reports,
        name="reports_period",
    ),

    path(
        "my-earnings/",
        views.employee_earnings_report,
        name="employee_earnings_report",
    ),

    path(
        "my-earnings/<str:period>/",
        views.employee_earnings_report,
        name="employee_earnings_report_period",
    ),

    path(
        "activity/",
        views.activity_log,
        name="activity_log",
    ),

    path(
        "employees/",
        views.employees,
        name="employees",
    ),

    path(
        "employees/<int:employee_id>/edit/",
        views.edit_employee,
        name="edit_employee",
    ),

    path(
        "employees/<int:employee_id>/deactivate/",
        views.deactivate_employee,
        name="deactivate_employee",
    ),

    path(
        "manager/employee-earnings/",
        views.manager_employee_earnings,
        name="manager_employee_earnings",
    ),

    path(
        "manager/add-employee-earnings/",
        views.manager_add_employee_earnings,
        name="manager_add_employee_earnings",
    ),
]
