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
        response = self.client.post(reverse('manage_sales'), {
            'business_date': '2024-03-01', 'starting_cash': '100.00',
            'ending_cash': '350.00', 'card_batch_total': '220.00'})
        self.assertEqual(response.status_code, 302)
        sales = DailySales.objects.get(business_date=date(2024, 3, 1))
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
