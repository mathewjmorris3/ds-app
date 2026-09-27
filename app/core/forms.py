from decimal import Decimal

from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .models import DailySales, Employee, EmployeeEarning


# =========================================================
# DAILY BUSINESS SALES
# =========================================================

class DailySalesForm(forms.ModelForm):

    class Meta:
        model = DailySales

        fields = [
            "cash_sales",
            "credit_card_sales",
        ]

        widgets = {
            "cash_sales": forms.NumberInput(
                attrs={
                    "step": "0.01",
                    "min": "0",
                    "inputmode": "decimal",
                    "placeholder": "0.00",
                }
            ),

            "credit_card_sales": forms.NumberInput(
                attrs={
                    "step": "0.01",
                    "min": "0",
                    "inputmode": "decimal",
                    "placeholder": "0.00",
                }
            ),
        }


# =========================================================
# EMPLOYEE ENTERING THEIR OWN PAY/TIPS
# =========================================================

class EmployeeEarningForm(forms.ModelForm):

    class Meta:
        model = EmployeeEarning

        fields = [
            "cash_pay",
            "card_tips",
            "cash_tips",
        ]

        widgets = {
            "cash_pay": forms.NumberInput(
                attrs={
                    "step": "0.01",
                    "min": "0",
                    "inputmode": "decimal",
                    "placeholder": "0.00",
                }
            ),

            "card_tips": forms.NumberInput(
                attrs={
                    "step": "0.01",
                    "min": "0",
                    "inputmode": "decimal",
                    "placeholder": "0.00",
                }
            ),

            "cash_tips": forms.NumberInput(
                attrs={
                    "step": "0.01",
                    "min": "0",
                    "inputmode": "decimal",
                    "placeholder": "0.00",
                }
            ),
        }

    def clean(self):

        cleaned_data = super().clean()

        for field in [
            "cash_pay",
            "card_tips",
            "cash_tips",
        ]:

            if cleaned_data.get(field) is None:
                cleaned_data[field] = Decimal("0.00")

        return cleaned_data


# =========================================================
# MANAGER PAGE FOR ENTERING/CORRECTING AN EMPLOYEE'S
# PAY AND TIPS FOR A SELECTED DATE
# =========================================================

class ManagerEmployeeEarningForm(forms.Form):

    business_date = forms.DateField(
        label="Business Date",
        widget=forms.DateInput(
            attrs={
                "type": "date",
            }
        ),
    )

    employee = forms.ModelChoiceField(
        queryset=Employee.objects.none(),
        label="Employee",
    )

    cash_pay = forms.DecimalField(
        label="Cash Pay",
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.00"),
        initial=Decimal("0.00"),
        widget=forms.NumberInput(
            attrs={
                "step": "0.01",
                "min": "0",
                "inputmode": "decimal",
                "placeholder": "0.00",
            }
        ),
    )

    card_tips = forms.DecimalField(
        label="Credit Card Tips",
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.00"),
        initial=Decimal("0.00"),
        widget=forms.NumberInput(
            attrs={
                "step": "0.01",
                "min": "0",
                "inputmode": "decimal",
                "placeholder": "0.00",
            }
        ),
    )

    cash_tips = forms.DecimalField(
        label="Cash Tips",
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.00"),
        initial=Decimal("0.00"),
        widget=forms.NumberInput(
            attrs={
                "step": "0.01",
                "min": "0",
                "inputmode": "decimal",
                "placeholder": "0.00",
            }
        ),
    )

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        self.fields["employee"].queryset = (
            Employee.objects
            .filter(is_active=True)
            .select_related("user")
            .order_by("employee_number")
        )


# =========================================================
# ADD A NEW EMPLOYEE
# =========================================================

class EmployeeCreateForm(forms.Form):

    username = forms.CharField(
        max_length=150,
        label="Username",
    )

    first_name = forms.CharField(
        max_length=150,
        label="First Name",
    )

    last_name = forms.CharField(
        max_length=150,
        label="Last Name",
    )

    employee_number = forms.CharField(
        max_length=20,
        label="Employee Number",
    )

    job_title = forms.CharField(
        max_length=100,
        required=False,
        label="Job Title",
    )

    employment_type = forms.ChoiceField(
        choices=Employee.EmploymentType.choices,
        label="Employment Type",
    )

    hire_date = forms.DateField(
        required=False,
        label="Hire Date",
        widget=forms.DateInput(
            attrs={
                "type": "date",
            }
        ),
    )

    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput,
    )

    password_confirm = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput,
    )

    def clean_username(self):

        username = (
            self.cleaned_data["username"]
            .strip()
        )

        if User.objects.filter(
            username__iexact=username
        ).exists():

            raise forms.ValidationError(
                "That username already exists."
            )

        return username

    def clean_employee_number(self):

        employee_number = (
            self.cleaned_data["employee_number"]
            .strip()
            .upper()
        )

        if Employee.objects.filter(
            employee_number__iexact=employee_number
        ).exists():

            raise forms.ValidationError(
                "That employee number already exists."
            )

        return employee_number

    def clean(self):

        cleaned_data = super().clean()

        password = cleaned_data.get(
            "password"
        )

        password_confirm = cleaned_data.get(
            "password_confirm"
        )

        if (
            password
            and password_confirm
            and password != password_confirm
        ):

            self.add_error(
                "password_confirm",
                "Passwords do not match.",
            )

        if password:
            candidate = User(username=cleaned_data.get("username", ""),
                             first_name=cleaned_data.get("first_name", ""),
                             last_name=cleaned_data.get("last_name", ""))
            try:
                validate_password(password, candidate)
            except ValidationError as exc:
                self.add_error("password", exc)

        return cleaned_data


# =========================================================
# MANAGER: ENTER TODAY'S PAY/TIPS FOR ANOTHER EMPLOYEE
#
# This is the form displayed directly underneath
# NLingle's own earnings form.
# =========================================================

class ManagerOtherEmployeeEarningsForm(forms.Form):

    employee = forms.ModelChoiceField(
        queryset=Employee.objects.none(),
        label="Employee",
    )

    cash_pay = forms.DecimalField(
        label="Cash Pay",
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.00"),
        initial=Decimal("0.00"),
        widget=forms.NumberInput(
            attrs={
                "step": "0.01",
                "min": "0",
                "inputmode": "decimal",
                "placeholder": "0.00",
            }
        ),
    )

    card_tips = forms.DecimalField(
        label="Credit Card Tips",
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.00"),
        initial=Decimal("0.00"),
        widget=forms.NumberInput(
            attrs={
                "step": "0.01",
                "min": "0",
                "inputmode": "decimal",
                "placeholder": "0.00",
            }
        ),
    )

    cash_tips = forms.DecimalField(
        label="Cash Tips",
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.00"),
        initial=Decimal("0.00"),
        widget=forms.NumberInput(
            attrs={
                "step": "0.01",
                "min": "0",
                "inputmode": "decimal",
                "placeholder": "0.00",
            }
        ),
    )

    def __init__(
        self,
        *args,
        current_employee=None,
        **kwargs
    ):

        super().__init__(*args, **kwargs)

        employees = (
            Employee.objects
            .filter(is_active=True)
            .select_related("user")
            .order_by("employee_number")
        )

        # NLingle enters her own pay/tips above,
        # so don't show herself in this dropdown.
        if current_employee:

            employees = employees.exclude(
                id=current_employee.id
            )

        self.fields["employee"].queryset = employees


# =========================================================
# MANAGER: EDIT EXISTING EMPLOYEE
# =========================================================

class EmployeeEditForm(forms.Form):

    username = forms.CharField(
        max_length=150,
        label="Username",
    )

    first_name = forms.CharField(
        max_length=150,
        label="First Name",
    )

    last_name = forms.CharField(
        max_length=150,
        label="Last Name",
    )

    employee_number = forms.CharField(
        max_length=20,
        label="Employee Number",
    )

    job_title = forms.CharField(
        max_length=100,
        required=False,
        label="Job Title",
    )

    employment_type = forms.ChoiceField(
        choices=Employee.EmploymentType.choices,
        label="Employment Type",
    )

    hire_date = forms.DateField(
        required=False,
        label="Hire Date",
        widget=forms.DateInput(
            attrs={
                "type": "date",
            }
        ),
    )

    def __init__(self, *args, employee=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.employee = employee

        if employee and not self.is_bound:

            user = employee.user

            self.initial.update(
                {
                    "username":
                        user.username if user else "",

                    "first_name":
                        user.first_name if user else "",

                    "last_name":
                        user.last_name if user else "",

                    "employee_number":
                        employee.employee_number,

                    "job_title":
                        employee.job_title,

                    "employment_type":
                        employee.employment_type,

                    "hire_date":
                        employee.hire_date,
                }
            )

    def clean_username(self):

        username = (
            self.cleaned_data["username"]
            .strip()
        )

        users = User.objects.filter(
            username__iexact=username
        )

        if (
            self.employee
            and self.employee.user
        ):
            users = users.exclude(
                id=self.employee.user.id
            )

        if users.exists():
            raise forms.ValidationError(
                "That username is already in use."
            )

        return username

    def clean_employee_number(self):

        employee_number = (
            self.cleaned_data["employee_number"]
            .strip()
            .upper()
        )

        employees = Employee.objects.filter(
            employee_number__iexact=employee_number
        )

        if self.employee:
            employees = employees.exclude(
                id=self.employee.id
            )

        if employees.exists():
            raise forms.ValidationError(
                "That employee number is already in use."
            )

        return employee_number


class HistoricalSalesForm(DailySalesForm):
    business_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))

    class Meta(DailySalesForm.Meta):
        fields = ["business_date", "cash_sales", "credit_card_sales"]


class DrawerCloseoutForm(forms.ModelForm):
    class Meta:
        model = DailySales
        fields = ["business_date", "starting_cash", "ending_cash", "card_batch_total"]
        labels = {"starting_cash": "Starting cash retained in drawer",
                  "ending_cash": "Ending cash count AFTER payouts (including starting cash)",
                  "card_batch_total": "Card batch total INCLUDING card tips"}
        widgets = {"business_date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in ("starting_cash", "ending_cash", "card_batch_total"):
            self.fields[field].required = True
