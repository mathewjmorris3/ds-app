import csv
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import DailySales, Employee, EmployeeEarning


class Command(BaseCommand):
    help = "Import DailySales and EmployeeEarning records from CSV"

    def add_arguments(self, parser):
        parser.add_argument(
            "csv_file",
            type=str,
            help="Path to CSV file",
        )

    @transaction.atomic
    def handle(self, *args, **options):

        csv_file = options["csv_file"]

        required_columns = {
            "business_date",
            "cash_sales",
            "credit_card_sales",
            "employee_number",
            "cash_pay",
            "card_tips",
            "cash_tips",
        }

        sales_created = 0
        earnings_created = 0
        earnings_updated = 0

        try:
            handle = open(
                csv_file,
                "r",
                newline="",
                encoding="utf-8-sig",
            )
        except FileNotFoundError:
            raise CommandError(
                f"CSV file not found: {csv_file}"
            )

        with handle:

            reader = csv.DictReader(handle)

            if not reader.fieldnames:
                raise CommandError(
                    "CSV file has no header row."
                )

            missing = (
                required_columns
                - set(reader.fieldnames)
            )

            if missing:
                raise CommandError(
                    "Missing CSV columns: "
                    + ", ".join(sorted(missing))
                )

            daily_values = {}

            for row_number, row in enumerate(
                reader,
                start=2,
            ):

                business_date = (
                    row["business_date"].strip()
                )

                employee_number = (
                    row["employee_number"]
                    .strip()
                    .upper()
                )

                cash_sales = Decimal(
                    row["cash_sales"]
                )

                credit_card_sales = Decimal(
                    row["credit_card_sales"]
                )

                cash_pay = Decimal(
                    row["cash_pay"]
                )

                card_tips = Decimal(
                    row["card_tips"]
                )

                cash_tips = Decimal(
                    row["cash_tips"]
                )

                #
                # Ensure repeated sales figures for
                # the same date are consistent.
                #
                current_sales = (
                    cash_sales,
                    credit_card_sales,
                )

                if business_date in daily_values:

                    if (
                        daily_values[business_date]
                        != current_sales
                    ):
                        raise CommandError(
                            f"Row {row_number}: "
                            f"inconsistent sales values "
                            f"for {business_date}."
                        )

                else:
                    daily_values[
                        business_date
                    ] = current_sales

                try:
                    employee = Employee.objects.get(
                        employee_number=employee_number
                    )

                except Employee.DoesNotExist:
                    raise CommandError(
                        f"Row {row_number}: "
                        f"employee {employee_number} "
                        f"does not exist."
                    )

                daily_sales, created = (
                    DailySales.objects.get_or_create(
                        business_date=business_date,
                        defaults={
                            "cash_sales":
                                cash_sales,
                            "credit_card_sales":
                                credit_card_sales,
                        },
                    )
                )

                if created:
                    sales_created += 1

                else:

                    #
                    # Don't silently overwrite an
                    # existing business record with
                    # different values.
                    #
                    if (
                        daily_sales.cash_sales
                        != cash_sales
                        or
                        daily_sales.credit_card_sales
                        != credit_card_sales
                    ):
                        raise CommandError(
                            f"Row {row_number}: "
                            f"DailySales already exists "
                            f"for {business_date} with "
                            f"different sales amounts."
                        )

                daily_sales = DailySales.objects.select_for_update().get(pk=daily_sales.pk)
                if daily_sales.finalized_at or daily_sales.is_drawer_closeout:
                    raise CommandError(f"Row {row_number}: importer only supports open legacy sales records.")

                earning, created = (
                    EmployeeEarning.objects.update_or_create(
                        daily_sales=daily_sales,
                        employee=employee,
                        defaults={
                            "cash_pay":
                                cash_pay,
                            "card_tips":
                                card_tips,
                            "cash_tips":
                                cash_tips,
                        },
                    )
                )

                if created:
                    earnings_created += 1
                else:
                    earnings_updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                "Import complete."
            )
        )

        self.stdout.write(
            f"Daily sales created: "
            f"{sales_created}"
        )

        self.stdout.write(
            f"Employee earnings created: "
            f"{earnings_created}"
        )

        self.stdout.write(
            f"Employee earnings updated: "
            f"{earnings_updated}"
        )
