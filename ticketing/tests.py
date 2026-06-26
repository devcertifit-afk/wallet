from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from unittest.mock import patch

from passes.models import Company, Employee, PassTemplate, PassInstance, StripeTransaction, PassAnalytics
from ticketing.models import Venue, Event, TicketOrder
from ticketing.tasks import fulfill_ticket_order_task

class TicketingModelTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Festivals Corp", slug="festivals-corp", vertical='TICKETING')
        self.venue = Venue.objects.create(company=self.company, name="Grand Arena", address="123 Main St", total_capacity=500)
        self.event = Event.objects.create(
            company=self.company,
            venue=self.venue,
            slug="summer-jam-2026",
            name="Summer Jam 2026",
            date=timezone.now() + timezone.timedelta(days=30),
            description="The biggest summer concert.",
            ticket_types=[
                {'name': 'General Admission', 'price': 25.00, 'qty': 400},
                {'name': 'VIP', 'price': 80.00, 'qty': 100}
            ],
            is_published=True
        )

    def test_venue_creation(self):
        self.assertEqual(self.venue.name, "Grand Arena")
        self.assertEqual(self.venue.company, self.company)
        self.assertEqual(str(self.venue), "Grand Arena - Festivals Corp")

    def test_event_creation(self):
        self.assertEqual(self.event.name, "Summer Jam 2026")
        self.assertEqual(self.event.slug, "summer-jam-2026")
        self.assertTrue(self.event.is_published)

    def test_ticket_order_creation(self):
        order = TicketOrder.objects.create(
            event=self.event,
            order_ref="TKT-TEST1234",
            ticket_type="General Admission",
            buyer_name="Alice Smith",
            buyer_email="alice@example.com"
        )
        self.assertEqual(order.order_ref, "TKT-TEST1234")
        self.assertEqual(order.buyer_name, "Alice Smith")
        self.assertFalse(order.is_scanned)


class TicketingPublicViewTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Festivals Corp", slug="festivals-corp", vertical='TICKETING')
        self.venue = Venue.objects.create(company=self.company, name="Grand Arena", address="123 Main St", total_capacity=500)
        self.event = Event.objects.create(
            company=self.company,
            venue=self.venue,
            slug="summer-jam-2026",
            name="Summer Jam 2026",
            date=timezone.now() + timezone.timedelta(days=30),
            description="The biggest summer concert.",
            ticket_types=[
                {'name': 'General Admission', 'price': 25.00, 'qty': 400},
                {'name': 'VIP', 'price': 80.00, 'qty': 100}
            ],
            is_published=True
        )
        
        # Mock passes generators to avoid external API configuration errors
        self.apple_patcher = patch('passes.utils.pass_generator.ApplePassGenerator.sign_manifest', return_value=b'mock_signature')
        self.google_patcher = patch('passes.utils.pass_generator.GoogleWalletGenerator.generate_save_url', return_value='https://pay.google.com/gp/v/save/mocktoken')
        self.apple_patcher.start()
        self.google_patcher.start()

    def tearDown(self):
        self.apple_patcher.stop()
        self.google_patcher.stop()

    def test_organizer_profile_view(self):
        url = reverse('organizer-profile', kwargs={'organizer_slug': self.company.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.company.name)
        self.assertContains(response, self.event.name)

    def test_organizer_profile_404_not_ticketing(self):
        non_ticketing_company = Company.objects.create(name="Cafe Nero", slug="cafe-nero", vertical='CAFE')
        url = reverse('organizer-profile', kwargs={'organizer_slug': non_ticketing_company.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_event_detail_view(self):
        url = reverse('event-detail', kwargs={'organizer_slug': self.company.slug, 'event_slug': self.event.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.event.name)
        self.assertContains(response, "General Admission")

    def test_initiate_checkout_validation_error(self):
        url = reverse('initiate-checkout', kwargs={'organizer_slug': self.company.slug, 'event_slug': self.event.slug})
        response = self.client.post(url, {
            'ticket_type': 'General Admission',
            'buyer_name': '',  # missing name
            'buyer_email': 'alice@example.com'
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "All fields are required.")

    def test_initiate_checkout_success_redirect_to_mock_stripe(self):
        url = reverse('initiate-checkout', kwargs={'organizer_slug': self.company.slug, 'event_slug': self.event.slug})
        response = self.client.post(url, {
            'ticket_type': 'General Admission',
            'buyer_name': 'Alice Smith',
            'buyer_email': 'alice@example.com'
        })
        # Check that we redirect to mock stripe checkout with order_ref and price
        order = TicketOrder.objects.first()
        self.assertIsNotNone(order)
        self.assertEqual(order.buyer_name, "Alice Smith")
        
        expected_redirect_url = reverse('mock-stripe-checkout') + f"?order_ref={order.order_ref}&amount=25.0"
        self.assertRedirects(response, expected_redirect_url)

    def test_mock_stripe_checkout_and_async_fulfillment(self):
        # 1. Initiate checkout first
        order = TicketOrder.objects.create(
            event=self.event,
            order_ref="TKT-TESTPAY",
            ticket_type="General Admission",
            buyer_name="Alice Smith",
            buyer_email="alice@example.com"
        )
        
        url = reverse('mock-stripe-checkout') + f"?order_ref={order.order_ref}&amount=25.0"
        
        # Fulfill synchronously during test by patching tasks.trigger_order_fulfillment_async
        with patch('ticketing.views.trigger_order_fulfillment_async', side_effect=lambda o: fulfill_ticket_order_task(o.id)):
            response = self.client.post(url, {'action': 'pay'})
            
        # Check redirect to confirm page
        expected_redirect = reverse('order-confirm', kwargs={'organizer_slug': self.company.slug, 'event_slug': self.event.slug}) + f"?order_ref={order.order_ref}"
        self.assertRedirects(response, expected_redirect)

        # Check order state: StripeTransaction created, PassInstance created, PDF URL populated
        order.refresh_from_db()
        self.assertIsNotNone(order.stripe_transaction)
        self.assertEqual(order.stripe_transaction.amount, 25.00)
        self.assertIsNotNone(order.pass_instance)
        self.assertEqual(order.pass_instance.customer_name, "Alice Smith")
        self.assertTrue(order.pdf_url.startswith('/media/tickets/'))

    def test_order_status_polling_api(self):
        order = TicketOrder.objects.create(
            event=self.event,
            order_ref="TKT-POLL1",
            ticket_type="General Admission",
            buyer_name="Alice Smith",
            buyer_email="alice@example.com"
        )
        
        status_url = reverse('order-status-api', kwargs={'order_ref': order.order_ref})
        
        # Initially pending
        response = self.client.get(status_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'pending')

        # Create mock pass template
        pass_template = PassTemplate.objects.create(
            company=self.company,
            pass_type=PassTemplate.PassTypes.EVENT_TICKET,
            title="Concert Pass",
            background_color="#6366f1",
            foreground_color="#ffffff"
        )
        # Fulfilled state
        pass_instance = PassInstance.objects.create(
            template=pass_template,
            customer_name="Alice Smith",
            customer_email="alice@example.com"
        )
        order.pass_instance = pass_instance
        order.pdf_url = "/media/tickets/ticket.pdf"
        order.save()

        # Should be success
        response = self.client.get(status_url)
        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        self.assertEqual(json_data['status'], 'success')
        self.assertEqual(json_data['pdf_url'], '/media/tickets/ticket.pdf')
        self.assertIn(str(pass_instance.serial_number), json_data['apple_url'])


class TicketingDashboardAndScannerTests(APITestCase):
    def setUp(self):
        # Organizer Company (Ticketing)
        self.company = Company.objects.create(name="Festivals Corp", slug="festivals-corp", vertical='TICKETING')
        self.user = User.objects.create_user(username="festivals_staff", password="password123")
        self.employee = Employee.objects.create(
            user=self.user,
            company=self.company,
            role=Employee.Roles.STAFF
        )

        # Other Company (Cafe)
        self.other_company = Company.objects.create(name="Nero Cafe", slug="nero-cafe", vertical='CAFE')
        self.other_user = User.objects.create_user(username="cafe_staff", password="password123")
        self.other_employee = Employee.objects.create(
            user=self.other_user,
            company=self.other_company,
            role=Employee.Roles.STAFF
        )

        # Venue & Event
        self.venue = Venue.objects.create(company=self.company, name="Grand Arena", address="123 Main St", total_capacity=500)
        self.event = Event.objects.create(
            company=self.company,
            venue=self.venue,
            slug="summer-jam-2026",
            name="Summer Jam 2026",
            date=timezone.now() + timezone.timedelta(days=30),
            ticket_types=[{'name': 'General Admission', 'price': 25.00, 'qty': 400}],
            is_published=True
        )

        # Order & Pass Instance
        self.pass_template = PassTemplate.objects.create(
            company=self.company,
            pass_type=PassTemplate.PassTypes.EVENT_TICKET,
            title="Concert Pass",
            background_color="#6366f1",
            foreground_color="#ffffff"
        )
        self.pass_instance = PassInstance.objects.create(
            template=self.pass_template,
            customer_name="Alice Smith",
            customer_email="alice@example.com"
        )
        self.order = TicketOrder.objects.create(
            event=self.event,
            pass_instance=self.pass_instance,
            order_ref="TKT-112233",
            ticket_type="General Admission",
            buyer_name="Alice Smith",
            buyer_email="alice@example.com"
        )

    def test_dashboard_events_restricted_to_merchant_vertical(self):
        url = reverse('dashboard-events')
        
        # Logged in as cafe staff
        self.client.force_login(self.other_user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)  # Forbidden for non-ticketing company

        # Logged in as ticketing staff
        self.client.force_login(self.user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_dashboard_events_new_view(self):
        url = reverse('dashboard-events-new')
        self.client.force_login(self.user)
        
        response = self.client.post(url, {
            'name': 'Winter Gala 2026',
            'venue': self.venue.id,
            'date': '2026-12-15T19:00',
            'description': 'Winter gala event.',
            'ticket_type_name[]': ['VIP Ticket'],
            'ticket_type_price[]': ['120.00'],
            'ticket_type_qty[]': ['50']
        })
        
        self.assertEqual(response.status_code, 302)  # Redirects to dashboard events list
        self.assertTrue(Event.objects.filter(name='Winter Gala 2026').exists())

    def test_scan_api_security_authorization(self):
        scan_url = reverse('dashboard-events-scan-api', kwargs={'event_slug': self.event.slug})
        
        # 1. Unauthenticated user -> 401/403
        response = self.client.post(scan_url, {'qr_data': self.order.order_ref})
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

        # 2. Cafe employee scanning -> 403 Forbidden
        self.client.force_authenticate(user=self.other_user)
        response = self.client.post(scan_url, {'qr_data': self.order.order_ref})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # 3. Ticketing employee scanning -> 200 OK (Successful check-in)
        self.client.force_authenticate(user=self.user)
        response = self.client.post(scan_url, {'qr_data': self.order.order_ref})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        self.assertEqual(response.data['buyer_name'], "Alice Smith")

        # Verify database fields updated
        self.order.refresh_from_db()
        self.assertTrue(self.order.is_scanned)
        self.assertEqual(self.order.scanned_by, self.user)
        self.assertIsNotNone(self.order.scanned_at)

        # Verify PassAnalytics log created
        analytics = PassAnalytics.objects.filter(pass_instance=self.pass_instance).first()
        self.assertIsNotNone(analytics)
        self.assertEqual(analytics.event_type, PassAnalytics.EventTypes.TICKET_SCANNED)

    def test_scan_api_already_scanned(self):
        scan_url = reverse('dashboard-events-scan-api', kwargs={'event_slug': self.event.slug})
        self.client.force_authenticate(user=self.user)

        # Pre-mark order as scanned
        self.order.is_scanned = True
        self.order.scanned_at = timezone.now()
        self.order.scanned_by = self.user
        self.order.save()

        response = self.client.post(scan_url, {'qr_data': self.order.order_ref})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'already_scanned')
        self.assertEqual(response.data['buyer_name'], "Alice Smith")
        self.assertEqual(response.data['scanned_by'], self.user.username)

    def test_scan_api_invalid_code(self):
        scan_url = reverse('dashboard-events-scan-api', kwargs={'event_slug': self.event.slug})
        self.client.force_authenticate(user=self.user)

        response = self.client.post(scan_url, {'qr_data': 'INVALID-QR-CODE'})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data['status'], 'invalid')
