from decimal import Decimal

from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Sum
from django.utils import timezone


class Employee(models.Model):

    class EmploymentType(models.TextChoices):
        HOURLY = "HOURLY", "Hourly"
        SALARY = "SALARY", "Salary"

    user = models.OneToOneField(
        User,
        on_delete=models.PROTECT,
        related_name="employee_profile",
        null=True,
        blank=True,
    )

    employee_number = models.CharField(
        max_length=20,
        unique=True,
    )

    job_title = models.CharField(
        max_length=100,
        blank=True,
    )

    employment_type = models.CharField(
        max_length=10,
        choices=EmploymentType.choices,
        default=EmploymentType.HOURLY,
    )

    hire_date = models.DateField(
        null=True,
        blank=True,
    )

    is_active = models.BooleanField(
        default=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    def __str__(self):
        if self.user:
            full_name = self.user.get_full_name().strip()

            if full_name:
                return f"{self.employee_number} - {full_name}"

            return f"{self.employee_number} - {self.user.username}"

        return self.employee_number


class DailySales(models.Model):

    business_date = models.DateField(
        unique=True,
        default=timezone.localdate,
    )

    cash_sales = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    credit_card_sales = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    entered_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="daily_sales_entered",
    )

    last_modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="daily_sales_modified",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["-business_date"]

    def _earning_total(self, field_name):
        result = self.employee_earnings.aggregate(
            total=Sum(field_name, default=Decimal("0.00"))
        )
        return result["total"]

    @property
    def total_sales(self):
        return self.cash_sales + self.credit_card_sales

    @property
    def total_employee_pay(self):
        return self._earning_total("cash_pay")

    @property
    def total_card_tips(self):
        return self._earning_total("card_tips")

    @property
    def total_cash_tips(self):
        return self._earning_total("cash_tips")

    @property
    def total_employee_earnings(self):
        return (
            self.total_employee_pay
            + self.total_card_tips
            + self.total_cash_tips
        )

    @property
    def expected_cash_deposit(self):
        return (
            self.cash_sales
            - self.total_employee_pay
            - self.total_card_tips
        )

    @property
    def gross_card_batch(self):
        return self.credit_card_sales + self.total_card_tips

    @property
    def net_daily_proceeds(self):
        return (
            self.cash_sales
            + self.credit_card_sales
            - self.total_employee_pay
        )

    def __str__(self):
        return f"Daily Sales - {self.business_date}"


class EmployeeEarning(models.Model):

    daily_sales = models.ForeignKey(
        DailySales,
        on_delete=models.CASCADE,
        related_name="employee_earnings",
    )

    employee = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        related_name="earnings",
    )

    cash_pay = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    card_tips = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    cash_tips = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    entered_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="earnings_entered",
    )

    last_modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="earnings_modified",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = [
            "daily_sales__business_date",
            "employee__employee_number",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=["daily_sales", "employee"],
                name="unique_employee_earning_per_day",
            )
        ]

    @property
    def total_earnings(self):
        return self.cash_pay + self.card_tips + self.cash_tips

    def __str__(self):
        return (
            f"{self.employee} - "
            f"{self.daily_sales.business_date}"
        )


class ActivityLog(models.Model):

    class Action(models.TextChoices):
        CREATE = "CREATE", "Created"
        UPDATE = "UPDATE", "Updated"
        EMPLOYEE_ADD = "EMPLOYEE_ADD", "Employee Added"
        EMPLOYEE_DEACTIVATE = "EMPLOYEE_DEACTIVATE", "Employee Deactivated"

    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="activity_logs",
    )

    action = models.CharField(
        max_length=30,
        choices=Action.choices,
    )

    object_type = models.CharField(
        max_length=50,
    )

    object_id = models.CharField(
        max_length=50,
        blank=True,
    )

    description = models.TextField()

    details = models.JSONField(
        default=dict,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.created_at} - {self.action}"
