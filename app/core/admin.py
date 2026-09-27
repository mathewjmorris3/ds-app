from django.contrib import admin

from .models import (
    ActivityLog,
    DailySales,
    Employee,
    EmployeeEarning,
)


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = (
        "employee_number",
        "get_name",
        "job_title",
        "employment_type",
        "hire_date",
        "is_active",
    )

    list_filter = (
        "is_active",
        "employment_type",
    )

    search_fields = (
        "employee_number",
        "user__username",
        "user__first_name",
        "user__last_name",
    )

    ordering = (
        "employee_number",
    )

    @admin.display(description="Employee")
    def get_name(self, obj):

        if not obj.user:
            return "No account assigned"

        full_name = obj.user.get_full_name().strip()

        return full_name or obj.user.username


class FinancialReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(DailySales)
class DailySalesAdmin(FinancialReadOnlyAdmin):
    list_display = (
        "business_date",
        "cash_sales",
        "credit_card_sales",
        "total_sales",
        "total_employee_pay",
        "total_card_tips",
        "total_cash_tips",
        "net_daily_proceeds",
    )

    ordering = (
        "-business_date",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )


@admin.register(EmployeeEarning)
class EmployeeEarningAdmin(FinancialReadOnlyAdmin):
    list_display = (
        "get_business_date",
        "employee",
        "cash_pay",
        "card_tips",
        "cash_tips",
        "total_earnings",
        "entered_by",
        "last_modified_by",
    )

    list_filter = (
        "daily_sales__business_date",
        "employee",
    )

    search_fields = (
        "employee__employee_number",
        "employee__user__username",
        "employee__user__first_name",
        "employee__user__last_name",
    )

    ordering = (
        "-daily_sales__business_date",
        "employee__employee_number",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    @admin.display(
        description="Business Date",
        ordering="daily_sales__business_date",
    )
    def get_business_date(self, obj):
        return obj.daily_sales.business_date


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "actor",
        "action",
        "object_type",
        "description",
    )

    list_filter = (
        "action",
        "object_type",
    )

    search_fields = (
        "actor__username",
        "description",
        "object_type",
    )

    ordering = (
        "-created_at",
    )

    readonly_fields = (
        "actor",
        "action",
        "object_type",
        "object_id",
        "description",
        "details",
        "created_at",
    )


    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
