from datetime import date
from decimal import Decimal as D
from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from .models import ActivityLog, DailySales, Employee, EmployeeEarning
from .forms import DailySalesForm, EmployeeCreateForm


class BusinessTests(TestCase):
    def setUp(self):
        self.users = {}
        for role in ('Employee', 'Manager', 'Owner', 'Unassigned'):
            user = User.objects.create_user(role, password='test-password')
            if role != 'Unassigned':
                user.groups.add(Group.objects.get_or_create(name=role)[0])
            Employee.objects.create(user=user, employee_number=role)
            self.users[role] = user
        self.sales = DailySales.objects.create(business_date=timezone.localdate(), cash_sales=D('100.25'), credit_card_sales=D('200.50'))
        self.earning = EmployeeEarning.objects.create(daily_sales=self.sales,
            employee=self.users['Employee'].employee_profile, cash_pay=D('20.10'), card_tips=D('30.20'), cash_tips=D('5.05'))

    def login(self, role):
        self.client.force_login(self.users[role])

    def test_financial_model_and_report_agree(self):
        self.assertEqual(self.sales.expected_cash_deposit, D('49.95'))
        self.assertEqual(self.sales.gross_card_batch, D('230.70'))
        self.assertEqual(self.sales.net_daily_proceeds, D('280.65'))
        self.assertEqual(self.earning.total_earnings, D('55.35'))
        self.login('Owner')
        response = self.client.get(reverse('reports_period', args=['daily']))
        for key in ('expected_cash_deposit', 'gross_card_batch', 'net_daily_proceeds', 'total_sales'):
            self.assertEqual(response.context['summary'][key], getattr(self.sales, key))

    def test_negative_deposit_is_not_clamped(self):
        self.sales.cash_sales = D('0')
        self.assertEqual(self.sales.expected_cash_deposit, D('-50.30'))

    def test_employee_cannot_access_management_or_other_earnings(self):
        self.login('Employee')
        for url in ('reports', 'employees', 'activity_log', 'manager_employee_earnings', 'manage_sales'):
            self.assertEqual(self.client.get(reverse(url)).status_code, 403)
        other = EmployeeEarning.objects.create(daily_sales=self.sales, employee=self.users['Manager'].employee_profile, cash_pay=999)
        response = self.client.get(reverse('employee_earnings_report'), {'employee': other.employee_id})
        self.assertNotContains(response, '999.00')

    def test_owner_cannot_write_sales(self):
        self.login('Owner')
        self.assertEqual(self.client.post(reverse('manage_sales'), {}).status_code, 403)

    def test_employee_cannot_create_sales(self):
        self.sales.delete()
        self.login('Employee')
        self.client.post(reverse('enter_today'), {'sales-cash_sales': '500', 'sales-credit_card_sales': '20', 'earning-cash_pay': '1', 'earning-card_tips': '2', 'earning-cash_tips': '3'})
        self.assertFalse(DailySales.objects.exists())

    def test_employee_cannot_overwrite_existing_sales_or_earnings(self):
        self.login('Employee')
        self.client.post(reverse('enter_today'), {'sales-cash_sales': '999', 'earning-cash_pay': '999'})
        self.sales.refresh_from_db(); self.earning.refresh_from_db()
        self.assertEqual(self.sales.cash_sales, D('100.25'))
        self.assertEqual(self.earning.cash_pay, D('20.10'))
        self.assertNotContains(self.client.get(reverse('enter_today')), '100.25')

    def test_manager_today_audit_preserves_previous_values(self):
        self.login('Manager')
        EmployeeEarning.objects.create(daily_sales=self.sales, employee=self.users['Manager'].employee_profile, cash_pay=D('1.00'))
        response = self.client.post(reverse('enter_today'), {'sales-cash_sales': '150.00', 'sales-credit_card_sales': '220.00', 'earning-cash_pay': '5.00', 'earning-card_tips': '2.00', 'earning-cash_tips': '3.00'})
        self.assertEqual(response.status_code, 302)
        log = ActivityLog.objects.get(object_type='DailySales')
        self.assertEqual(log.details['previous_cash_sales'], '100.25')
        log = ActivityLog.objects.get(object_type='EmployeeEarning')
        self.assertEqual(log.details['previous']['cash_pay'], '1.00')

    def test_historical_sales_correction_is_audited(self):
        self.login('Manager')
        DailySales.objects.create(business_date=date(2024, 2, 29), cash_sales=D('10.01'), credit_card_sales=D('20.02'))
        data = {'business_date': '2024-02-29', 'cash_sales': '10.01', 'credit_card_sales': '20.02'}
        self.assertEqual(self.client.post(reverse('manage_sales'), data).status_code, 302)
        data['cash_sales'] = '30.03'
        self.client.post(reverse('manage_sales'), data)
        record = DailySales.objects.get(business_date=date(2024, 2, 29))
        self.assertEqual(record.cash_sales, D('30.03'))
        self.assertEqual(ActivityLog.objects.first().details['previous']['cash_sales'], '10.01')

    def test_invalid_money_rejected(self):
        for value in ('-1', '0.001', 'NaN', 'Infinity'):
            self.assertFalse(DailySalesForm({'cash_sales': value, 'credit_card_sales': '0'}).is_valid())

    def test_weak_employee_password_rejected(self):
        form = EmployeeCreateForm({'username': 'newperson', 'first_name': 'New', 'last_name': 'Person', 'employee_number': 'NEW', 'employment_type': 'HOURLY', 'password': '123', 'password_confirm': '123'})
        self.assertFalse(form.is_valid())
        self.assertIn('password', form.errors)

    def test_deactivation_disables_login_and_preserves_history(self):
        self.login('Manager')
        self.client.post(reverse('deactivate_employee', args=[self.earning.employee_id]))
        self.users['Employee'].refresh_from_db()
        self.assertFalse(self.users['Employee'].is_active)
        self.assertTrue(EmployeeEarning.objects.filter(pk=self.earning.pk).exists())
        self.assertTrue(ActivityLog.objects.filter(action='EMPLOYEE_DEACTIVATE').exists())


    def test_after_payout_drawer_closeout_and_inclusive_card_batch(self):
        self.login('Manager')
        sales = DailySales.objects.create(business_date=date(2024, 3, 1),
            starting_cash=D('100.00'), ending_cash=D('350.00'), card_batch_total=D('220.00'))
        response = self.client.get(reverse('manage_sales'), {'date': '2024-03-01'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'historical record')
        EmployeeEarning.objects.create(daily_sales=sales, employee=self.earning.employee,
            cash_pay=D('50.00'), card_tips=D('20.00'), cash_tips=D('7.00'))
        self.assertEqual(sales.expected_cash_deposit, D('250.00'))
        self.assertEqual(sales.sales_cash, D('320.00'))
        self.assertEqual(sales.sales_card, D('200.00'))
        self.assertEqual(sales.total_sales, D('520.00'))
        self.assertEqual(sales.gross_card_batch, D('220.00'))
        self.assertEqual(sales.net_daily_proceeds, D('470.00'))
        response = self.client.get(reverse('reports_period', args=['daily']), {'date': '2024-03-01'})
        self.assertEqual(response.context['summary']['expected_cash_deposit'], D('250.00'))
        self.assertEqual(response.context['summary']['gross_card_batch'], D('220.00'))
        self.assertEqual(response.context['summary']['total_sales'], D('520.00'))

    def test_starting_cash_is_required_for_new_closeout(self):
        self.login('Manager')
        self.client.post(reverse('manage_sales'), {'business_date': '2024-03-01', 'ending_cash': '350', 'card_batch_total': '220'})
        self.assertFalse(DailySales.objects.filter(business_date=date(2024, 3, 1)).exists())


    def test_finalization_blocks_all_entry_routes_until_reopened(self):
        self.login('Manager')
        status_url = reverse('closeout_status', args=[self.sales.pk])
        self.client.post(status_url, {'action': 'finalize'})
        self.sales.refresh_from_db()
        self.assertIsNotNone(self.sales.finalized_at)
        for name in ('enter_today', 'manager_employee_earnings', 'manager_add_employee_earnings', 'manage_sales'):
            self.assertEqual(self.client.post(reverse(name), {'business_date': str(self.sales.business_date)}).status_code, 403)
        self.assertEqual(self.client.post(reverse('enter_today'), {'business_date': '2000-01-01'}).status_code, 403)
        self.login('Employee')
        self.assertEqual(self.client.post(status_url, {'action': 'reopen'}).status_code, 403)
        self.login('Manager')
        self.client.post(status_url, {'action': 'reopen'})
        self.sales.refresh_from_db()
        self.assertIsNone(self.sales.finalized_at)
        self.assertEqual(ActivityLog.objects.filter(details__transition='reopen').count(), 1)
        self.assertEqual(ActivityLog.objects.filter(details__transition='finalize').count(), 1)

    def test_cannot_finalize_card_tips_exceeding_batch(self):
        self.sales.starting_cash = D('100')
        self.sales.ending_cash = D('200')
        self.sales.card_batch_total = D('10')
        self.sales.save()
        self.login('Manager')
        self.client.post(reverse('closeout_status', args=[self.sales.pk]), {'action': 'finalize'})
        self.sales.refresh_from_db()
        self.assertIsNone(self.sales.finalized_at)

    def test_login_and_logout_through_authentication_views(self):
        self.assertRedirects(self.client.get('/'), '/accounts/login/?next=/')
        login_page = self.client.get('/accounts/login/')
        self.assertContains(login_page, 'href="/static/core/app.css"')
        response = self.client.post('/accounts/login/', {'username': 'Manager', 'password': 'test-password'})
        self.assertRedirects(response, '/')
        self.assertEqual(self.client.get(reverse('manage_sales')).status_code, 200)
        self.client.post('/accounts/logout/')
        self.assertRedirects(self.client.get('/'), '/accounts/login/?next=/')

    def test_wrong_password_and_inactive_login_rejected(self):
        self.client.post('/accounts/login/', {'username': 'Manager', 'password': 'wrong'})
        self.assertNotIn('_auth_user_id', self.client.session)
        self.users['Manager'].is_active = False
        self.users['Manager'].save(update_fields=['is_active'])
        self.client.post('/accounts/login/', {'username': 'Manager', 'password': 'test-password'})
        self.assertNotIn('_auth_user_id', self.client.session)


class DailyFinancialTests(TestCase):
    setUp = BusinessTests.setUp
    login = BusinessTests.login

    def data(self, **changes):
        values = {'business_date': '2024-03-04', 'register_cash': '850.00',
                  'card_charges': '620.00', 'daily_card_tips': '95.00',
                  'daily_employee_pay': '180.00', 'starting_cash': '205.00'}
        values.update(changes)
        return values

    def save_financial(self, **changes):
        self.login('Manager')
        response = self.client.post(reverse('manage_sales'), self.data(**changes))
        self.assertEqual(response.status_code, 302)
        return DailySales.objects.get(business_date=self.data(**changes)['business_date'])

    def test_example_persistence_and_independent_earnings(self):
        record = self.save_financial(subtotal='1', total_deposit='2', cash_deposit='3')
        for field, value in {'subtotal': '1470.00', 'total_deposit': '1565.00', 'cash_deposit': '560.00',
                             'starting_cash': '205.00', 'register_cash': '850.00', 'card_charges': '620.00',
                             'daily_card_tips': '95.00', 'daily_employee_pay': '180.00'}.items():
            self.assertEqual(getattr(record, field), D(value))
        self.assertFalse(record.employee_earnings.exists())
        EmployeeEarning.objects.create(daily_sales=record, employee=self.earning.employee,
                                      cash_pay=D('180'), card_tips=D('95'), cash_tips=D('12'))
        self.assertEqual(record.cash_deposit, D('560.00'))
        self.assertEqual(record.total_employee_earnings, D('287.00'))
        self.assertEqual(EmployeeEarning.objects.get(pk=self.earning.pk).cash_pay, D('20.10'))
        self.assertEqual(record.expected_cash_deposit, record.cash_deposit)
        page = self.client.get(reverse('manage_sales'), {'date': record.business_date})
        self.assertContains(page, 'Daily data saved.')
        self.assertContains(page, 'Calculated Totals')
        self.assertContains(page, 'daily_financial.js')
        self.assertContains(page, 'type="hidden" name="business_date" value="2024-03-04"')

    def test_local_date_and_starting_cash_defaults(self):
        self.login('Manager')
        self.sales.delete()
        page = self.client.get(reverse('manage_sales'))
        self.assertEqual(page.context['form']['business_date'].value(), timezone.localdate())
        self.assertEqual(page.context['form']['starting_cash'].value(), D('205.00'))

    def test_zero_and_exact_cents(self):
        record = self.save_financial(register_cash='0', card_charges='0', daily_card_tips='0',
                                     daily_employee_pay='0', starting_cash='0')
        for field in ('subtotal', 'total_deposit', 'cash_deposit'):
            self.assertEqual(getattr(record, field), D('0.00'))
        record = self.save_financial(business_date='2024-03-05', register_cash='0.10',
                                    card_charges='0.20', daily_card_tips='0.03',
                                    daily_employee_pay='0.01', starting_cash='0.02')
        self.assertEqual(record.subtotal, D('0.30'))
        self.assertEqual(record.total_deposit, D('0.33'))
        self.assertEqual(record.cash_deposit, D('0.10'))

    def test_invalid_and_missing_inputs_are_not_rounded_or_defaulted(self):
        from .forms import DailyFinancialForm
        for field in ('register_cash', 'card_charges', 'daily_card_tips', 'daily_employee_pay', 'starting_cash'):
            for invalid in ('', '-0.01', 'abc', 'NaN', 'Infinity', '0.001', '10000000000.00'):
                with self.subTest(field=field, value=invalid):
                    form = DailyFinancialForm(self.data(**{field: invalid}))
                    self.assertFalse(form.is_valid())
                    self.assertIn(field, form.errors)
        self.login('Manager')
        response = self.client.post(reverse('manage_sales'), self.data(starting_cash=''))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'This field is required.')
        self.assertFalse(DailySales.objects.filter(business_date='2024-03-04').exists())
        self.assertFalse(DailyFinancialForm(self.data(business_date='invalid')).is_valid())

    def test_duplicate_requires_loading_and_authorized_edit_is_audited(self):
        record = self.save_financial()
        response = self.client.post(reverse('manage_sales'), self.data(register_cash='999'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Load it before editing')
        record.refresh_from_db()
        self.assertEqual(record.register_cash, D('850.00'))
        self.assertEqual(DailySales.objects.filter(business_date=record.business_date).count(), 1)
        response = self.client.post(reverse('manage_sales'), self.data(record_id=str(record.pk), register_cash='900.00'))
        self.assertEqual(response.status_code, 302)
        record.refresh_from_db()
        self.assertEqual(record.cash_deposit, D('610.00'))
        log = ActivityLog.objects.filter(object_id=str(record.pk), action='UPDATE').get()
        self.assertEqual(log.actor, self.users['Manager'])
        self.assertIsNotNone(log.created_at)
        self.assertEqual(log.details['previous']['register_cash'], '850.00')
        self.assertEqual(log.details['new']['register_cash'], '900.00')
        self.assertEqual(log.details['previous']['cash_deposit'], '560.00')
        self.assertEqual(log.details['new']['cash_deposit'], '610.00')
        self.client.post(reverse('manage_sales'), self.data(record_id=str(record.pk), register_cash='900.00'))
        self.assertEqual(ActivityLog.objects.filter(object_id=str(record.pk), action='UPDATE').count(), 1)

    def test_unauthorized_posts_and_csrf(self):
        from django.test import Client
        for role in ('Employee', 'Owner', 'Unassigned'):
            self.login(role)
            self.assertEqual(self.client.post(reverse('manage_sales'), self.data()).status_code, 403)
        self.assertFalse(DailySales.objects.filter(business_date='2024-03-04').exists())
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.users['Manager'])
        self.assertEqual(csrf_client.post(reverse('manage_sales'), self.data()).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.post(reverse('manage_sales'), self.data()).status_code, 302)

    def test_negative_deposit_warns_and_cannot_finalize(self):
        record = self.save_financial(register_cash='0', daily_card_tips='0')
        self.assertEqual(record.cash_deposit, D('-385.00'))
        page = self.client.get(reverse('manage_sales'), {'date': record.business_date})
        self.assertContains(page, 'Negative cash deposit: review')
        self.client.post(reverse('closeout_status', args=[record.pk]), {'action': 'finalize'})
        record.refresh_from_db()
        self.assertIsNone(record.finalized_at)

    def test_new_records_finalize_and_reopen_with_earnings_locks(self):
        record = self.save_financial()
        self.client.post(reverse('closeout_status', args=[record.pk]), {'action': 'finalize'})
        record.refresh_from_db()
        self.assertIsNotNone(record.finalized_at)
        payload = self.data(record_id=str(record.pk))
        self.assertEqual(self.client.post(reverse('manage_sales'), payload).status_code, 403)
        self.assertEqual(self.client.post(reverse('manager_employee_earnings'), payload).status_code, 403)
        self.client.post(reverse('closeout_status', args=[record.pk]), {'action': 'reopen'})
        self.assertEqual(self.client.post(reverse('manage_sales'), payload).status_code, 302)

    def test_reports_separate_history_and_include_all_employee_earnings(self):
        record = self.save_financial(business_date="2024-03-06")
        EmployeeEarning.objects.create(daily_sales=record, employee=self.earning.employee,
                                      cash_pay=D('180'), card_tips=D('95'), cash_tips=D('12'))
        legacy = DailySales.objects.create(business_date=date(2024, 3, 4), cash_sales=D('50'), credit_card_sales=D('20'))
        drawer = DailySales.objects.create(business_date=date(2024, 3, 5), starting_cash=D('100'),
                                          ending_cash=D('200'), card_batch_total=D('30'))
        EmployeeEarning.objects.create(daily_sales=drawer, employee=self.earning.employee,
                                      cash_pay=D('10'), card_tips=D('5'))
        self.login('Owner')
        for period in ('daily', 'weekly', 'monthly', 'ytd'):
            with self.subTest(period=period):
                response = self.client.get(reverse('reports_period', args=[period]), {'date': '2024-03-06'})
                self.assertEqual(response.status_code, 200)
                for key in ('register_cash', 'card_charges', 'daily_card_tips', 'daily_employee_pay',
                            'starting_cash', 'subtotal', 'total_deposit', 'cash_deposit'):
                    self.assertEqual(response.context['financial_summary'][key], getattr(record, key))
                self.assertEqual(len(response.context['financial_rows']), 1)
                self.assertContains(response, 'Historical Business Summary')
                if period != 'daily':
                    self.assertEqual(response.context['summary']['expected_cash_deposit'], D('150'))
                    self.assertEqual(response.context['employee_rows'][0]['cash_pay'], D('190'))
                    self.assertEqual(response.context['employee_rows'][0]['card_tips'], D('100'))
                else:
                    self.assertEqual(response.context['summary']['total_sales'], D('0'))
        legacy.refresh_from_db(); drawer.refresh_from_db()
        self.assertIsNone(legacy.subtotal)
        self.assertIsNone(drawer.cash_deposit)
        self.assertIsNone(legacy.register_cash)
        self.assertEqual(legacy.expected_cash_deposit, D('50'))
        self.assertEqual(drawer.expected_cash_deposit, D('100'))

    def test_unique_date_and_complete_input_database_constraints(self):
        from django.db import IntegrityError, transaction
        record = self.save_financial()
        with self.assertRaises(IntegrityError), transaction.atomic():
            DailySales.objects.create(business_date=record.business_date)
        with self.assertRaises(IntegrityError), transaction.atomic():
            DailySales.objects.create(business_date=date(2024, 3, 7), register_cash=D('10'))
        with self.assertRaises(IntegrityError), transaction.atomic():
            DailySales.objects.create(business_date=date(2024, 3, 7), register_cash=D('-1'),
                card_charges=D('0'), daily_card_tips=D('0'), daily_employee_pay=D('0'), starting_cash=D('0'))

    def test_concurrent_duplicate_is_a_validation_error(self):
        from unittest.mock import patch
        from django.db import IntegrityError
        self.login('Manager')
        with patch.object(DailySales, 'save', side_effect=IntegrityError('duplicate')):
            response = self.client.post(reverse('manage_sales'), self.data())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Load it before editing')
        self.assertFalse(ActivityLog.objects.exists())
        self.assertFalse(DailySales.objects.filter(business_date='2024-03-04').exists())

    def test_failed_audit_rolls_back_financial_save(self):
        from unittest.mock import patch
        self.login('Manager')
        with patch.object(ActivityLog.objects, 'create', side_effect=RuntimeError('audit unavailable')):
            with self.assertRaises(RuntimeError):
                self.client.post(reverse('manage_sales'), self.data())
        self.assertFalse(DailySales.objects.filter(business_date='2024-03-04').exists())

    def test_employee_self_entry_does_not_change_manual_totals(self):
        self.sales.delete()
        record = self.save_financial(business_date=str(timezone.localdate()))
        self.login('Employee')
        response = self.client.post(reverse('enter_today'), {
            'earning-cash_pay': '20.00', 'earning-card_tips': '10.00', 'earning-cash_tips': '5.00',
            'sales-cash_sales': '999', 'sales-credit_card_sales': '999'})
        self.assertEqual(response.status_code, 302)
        record.refresh_from_db()
        self.assertEqual(record.cash_deposit, D('560.00'))
        self.assertEqual(record.daily_employee_pay, D('180.00'))
        self.assertEqual(record.daily_card_tips, D('95.00'))
        self.assertEqual(record.employee_earnings.get().total_earnings, D('35.00'))
