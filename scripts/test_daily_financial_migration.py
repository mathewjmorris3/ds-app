"""Verify additive migrations against historical fixtures in a fresh in-memory DB.

Run with the application's Python environment. No deployment settings or secrets
are loaded and no existing database is connected, reset, or deleted.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.test_settings'
import django
django.setup()
from decimal import Decimal
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
executor = MigrationExecutor(connection)
executor.migrate([('core', '0004_dailysales_finalized_at')])
apps = executor.loader.project_state([('core', '0004_dailysales_finalized_at')]).apps
Sales = apps.get_model('core', 'DailySales')
Employee = apps.get_model('core', 'Employee')
Earning = apps.get_model('core', 'EmployeeEarning')
legacy = Sales.objects.create(business_date='2024-01-01', cash_sales=Decimal('850.00'), credit_card_sales=Decimal('620.00'))
drawer = Sales.objects.create(business_date='2024-01-02', starting_cash=Decimal('100.00'), ending_cash=Decimal('350.00'), card_batch_total=Decimal('220.00'))
employee = Employee.objects.create(employee_number='HISTORY')
earning = Earning.objects.create(daily_sales=drawer, employee=employee, cash_pay=Decimal('50'), card_tips=Decimal('20'), cash_tips=Decimal('7'))
executor = MigrationExecutor(connection)
executor.migrate(executor.loader.graph.leaf_nodes())
from core.models import DailySales, EmployeeEarning
legacy_new = DailySales.objects.get(pk=legacy.pk)
drawer_new = DailySales.objects.get(pk=drawer.pk)
assert legacy_new.cash_sales == Decimal('850.00')
assert legacy_new.credit_card_sales == Decimal('620.00')
assert legacy_new.register_cash is None and drawer_new.register_cash is None
assert legacy_new.total_deposit is None and drawer_new.total_deposit is None
assert drawer_new.expected_cash_deposit == Decimal('250.00')
assert EmployeeEarning.objects.get(pk=earning.pk).total_earnings == Decimal('77.00')
assert DailySales.objects.count() == 2
print('Forward migration verification passed: legacy sales, drawer closeout, and individual earnings unchanged; new inputs remain NULL.')
