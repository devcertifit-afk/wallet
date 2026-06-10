from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from .models import Company, Employee, PassTemplate, PassInstance, PassAnalytics

class PassFlowModelTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Test Merchant", slug="test-merchant")
        self.user = User.objects.create_user(username="owner_user", password="testpassword")
        self.employee = Employee.objects.create(
            user=self.user,
            company=self.company,
            role=Employee.Roles.OWNER
        )

    def test_company_creation(self):
        self.assertEqual(self.company.name, "Test Merchant")
        self.assertEqual(self.company.slug, "test-merchant")

    def test_employee_role_assignment(self):
        self.assertEqual(self.employee.role, Employee.Roles.OWNER)
        self.assertEqual(self.employee.user.username, "owner_user")
        self.assertEqual(self.employee.company, self.company)

class PassFlowAPITests(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Cafe Nero", slug="cafe-nero")
        self.user = User.objects.create_user(username="merchant_admin", password="password123")
        self.employee = Employee.objects.create(
            user=self.user,
            company=self.company,
            role=Employee.Roles.ADMIN
        )
        self.template = PassTemplate.objects.create(
            company=self.company,
            pass_type=PassTemplate.PassTypes.LOYALTY,
            title="Nero Rewards",
            background_color="#4f46e5",
            foreground_color="#ffffff"
        )
        self.instance = PassInstance.objects.create(
            template=self.template,
            customer_name="Jane Doe",
            customer_email="jane@example.com",
            balance=100.00
        )
        self.client.force_authenticate(user=self.user)


    def test_get_companies(self):
        url = reverse('company-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_get_templates(self):
        url = reverse('template-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_add_points(self):
        url = reverse('instance-add-points', kwargs={'serial_number': self.instance.serial_number})
        response = self.client.post(url, {'amount': '50.00'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify instance balance updated
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.balance, 150.00)
        
        # Verify analytics event logged
        analytics_event = PassAnalytics.objects.filter(pass_instance=self.instance).first()
        self.assertIsNotNone(analytics_event)
        self.assertEqual(analytics_event.event_type, PassAnalytics.EventTypes.UPDATE)
        self.assertEqual(analytics_event.value_changed, 50.00)
 
    def test_redeem_points_success(self):
        url = reverse('instance-redeem', kwargs={'serial_number': self.instance.serial_number})
        response = self.client.post(url, {'amount': '40.00'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify instance balance updated
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.balance, 60.00)
        
        # Verify analytics event logged
        analytics_event = PassAnalytics.objects.filter(pass_instance=self.instance).first()
        self.assertIsNotNone(analytics_event)
        self.assertEqual(analytics_event.event_type, PassAnalytics.EventTypes.REDEMPTION)
        self.assertEqual(analytics_event.value_changed, -40.00)
 
    def test_redeem_points_insufficient_balance(self):
        url = reverse('instance-redeem', kwargs={'serial_number': self.instance.serial_number})
        response = self.client.post(url, {'amount': '120.00'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error'], 'Insufficient balance')
        
        # Verify balance remained unchanged
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.balance, 100.00)

    def test_redeem_points_decimal_error(self):
        url = reverse('instance-redeem', kwargs={'serial_number': self.instance.serial_number})
        response = self.client.post(url, {'amount': '10.5'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error'], 'Points must be a whole number (no decimals)')
        
        # Verify balance remained unchanged
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.balance, 100.00)

    def test_add_points_decimal_error(self):
        url = reverse('instance-add-points', kwargs={'serial_number': self.instance.serial_number})
        response = self.client.post(url, {'amount': '10.5'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error'], 'Points must be a whole number (no decimals)')
        
        # Verify balance remained unchanged
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.balance, 100.00)
 
    def test_apple_pass_mock_generation(self):
        import io
        import zipfile
        import json
        url = reverse('instance-apple', kwargs={'serial_number': self.instance.serial_number})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.headers['Content-Type'], 'application/vnd.apple.pkpass')
        
        # Verify it is a valid zip archive containing standard files
        zip_bytes = io.BytesIO(response.content)
        self.assertTrue(zipfile.is_zipfile(zip_bytes))
        with zipfile.ZipFile(zip_bytes, 'r') as zf:
            namelist = zf.namelist()
            self.assertIn('pass.json', namelist)
            self.assertIn('manifest.json', namelist)
            self.assertIn('signature', namelist)
 
            # Check manifest contents
            manifest = json.loads(zf.read('manifest.json').decode('utf-8'))
            self.assertIn('pass.json', manifest)
 
    def test_google_pass_jwt_generation(self):
        url = reverse('instance-google', kwargs={'serial_number': self.instance.serial_number})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('save_url', response.data)
        self.assertTrue(response.data['save_url'].startswith('https://pay.google.com/gp/v/save/'))
 
    def test_lookup_by_uuid(self):
        url = reverse('instance-detail', kwargs={'serial_number': str(self.instance.serial_number)})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['customer_name'], "Jane Doe")

    def test_custom_sku_and_metadata_pass_generation(self):
        template_with_payload = PassTemplate.objects.create(
            company=self.company,
            pass_type=PassTemplate.PassTypes.LOYALTY,
            title="Promo Pass",
            background_color="#4f46e5",
            foreground_color="#ffffff",
            sku="SKU-TEST-VIP-99",
            custom_metadata={"campaign": "summer_sale", "limits": 5}
        )
        instance = PassInstance.objects.create(
            template=template_with_payload,
            customer_name="George Smith",
            customer_email="george@example.com",
            balance=100
        )
        
        # Verify API detail returns sku
        url_detail = reverse('instance-detail', kwargs={'serial_number': str(instance.serial_number)})
        res_detail = self.client.get(url_detail)
        self.assertEqual(res_detail.status_code, status.HTTP_200_OK)
        self.assertEqual(res_detail.data['sku'], "SKU-TEST-VIP-99")
        
        # Verify Apple pass generation contains userInfo dictionary
        import io
        import zipfile
        import json
        url_apple = reverse('instance-apple', kwargs={'serial_number': instance.serial_number})
        res_apple = self.client.get(url_apple)
        self.assertEqual(res_apple.status_code, status.HTTP_200_OK)
        
        zip_bytes = io.BytesIO(res_apple.content)
        with zipfile.ZipFile(zip_bytes, 'r') as zf:
            pass_json = json.loads(zf.read('pass.json').decode('utf-8'))
            self.assertIn('userInfo', pass_json)
            self.assertEqual(pass_json['userInfo']['sku'], "SKU-TEST-VIP-99")
            self.assertEqual(pass_json['userInfo']['metadata']['campaign'], "summer_sale")

        # Verify Google save URL contains customData payload
        url_google = reverse('instance-google', kwargs={'serial_number': instance.serial_number})
        res_google = self.client.get(url_google)
        self.assertEqual(res_google.status_code, status.HTTP_200_OK)
        self.assertIn('save_url', res_google.data)

    def test_coupon_pass_generation(self):
        coupon_template = PassTemplate.objects.create(
            company=self.company,
            pass_type=PassTemplate.PassTypes.COUPON,
            title="Summer Coupon",
            background_color="#4f46e5",
            foreground_color="#ffffff",
            sku="SKU-COUPON-SUMMER"
        )
        instance = PassInstance.objects.create(
            template=coupon_template,
            customer_name="Bob Jones",
            customer_email="bob@example.com"
        )
        
        import io
        import zipfile
        import json
        url_apple = reverse('instance-apple', kwargs={'serial_number': instance.serial_number})
        res_apple = self.client.get(url_apple)
        self.assertEqual(res_apple.status_code, status.HTTP_200_OK)
        
        zip_bytes = io.BytesIO(res_apple.content)
        with zipfile.ZipFile(zip_bytes, 'r') as zf:
            pass_json = json.loads(zf.read('pass.json').decode('utf-8'))
            self.assertIn('coupon', pass_json)
            self.assertEqual(pass_json['userInfo']['sku'], "SKU-COUPON-SUMMER")

    def test_event_ticket_creation_and_generation(self):
        ticket_template = PassTemplate.objects.create(
            company=self.company,
            pass_type=PassTemplate.PassTypes.EVENT_TICKET,
            title="Concert ticket",
            background_color="#1e1b4b",
            foreground_color="#ffffff",
            default_data={"default_event_name": "Summer Jam", "default_venue": "Sunset Stage"}
        )
        instance = PassInstance.objects.create(
            template=ticket_template,
            customer_name="Alice Smith",
            customer_email="alice@example.com",
            pass_data={
                "event_name": "Summer Jam (Day 2)",
                "venue": "Sunset Main Stage",
                "event_date": "July 12, 2026",
                "seat": "Row 2, Seat 15"
            }
        )
        
        # Verify serialization includes pass_data
        url_detail = reverse('instance-detail', kwargs={'serial_number': str(instance.serial_number)})
        res_detail = self.client.get(url_detail)
        self.assertEqual(res_detail.status_code, status.HTTP_200_OK)
        self.assertEqual(res_detail.data['pass_data']['seat'], "Row 2, Seat 15")
        self.assertEqual(res_detail.data['template'], ticket_template.id)

        # Verify Apple pass generation for EVENT_TICKET
        import io
        import zipfile
        import json
        url_apple = reverse('instance-apple', kwargs={'serial_number': instance.serial_number})
        res_apple = self.client.get(url_apple)
        self.assertEqual(res_apple.status_code, status.HTTP_200_OK)
        
        zip_bytes = io.BytesIO(res_apple.content)
        with zipfile.ZipFile(zip_bytes, 'r') as zf:
            pass_json = json.loads(zf.read('pass.json').decode('utf-8'))
            self.assertIn('eventTicket', pass_json)
            et = pass_json['eventTicket']
            # primaryFields: event_name
            self.assertEqual(et['primaryFields'][0]['value'], "Summer Jam (Day 2)")
            # secondaryFields: venue, seat
            self.assertEqual(et['secondaryFields'][0]['value'], "Sunset Main Stage")
            self.assertEqual(et['secondaryFields'][1]['value'], "Row 2, Seat 15")

        # Verify Google save URL contains event ticket object mapping
        from passes.utils.pass_generator import GoogleWalletGenerator
        generator = GoogleWalletGenerator(instance)
        obj_payload = generator.build_object_payload()
        self.assertEqual(obj_payload['eventName'], "Summer Jam (Day 2)")
        self.assertEqual(obj_payload['venue']['name'], "Sunset Main Stage")
        self.assertEqual(obj_payload['seatInfo']['seat'], "Row 2, Seat 15")

    def test_boarding_pass_creation_and_generation(self):
        boarding_template = PassTemplate.objects.create(
            company=self.company,
            pass_type=PassTemplate.PassTypes.BOARDING_PASS,
            title="Boarding Pass",
            background_color="#0f172a",
            foreground_color="#ffffff",
            default_data={"default_carrier": "AB", "default_origin": "LHR"}
        )
        instance = PassInstance.objects.create(
            template=boarding_template,
            customer_name="Bob Miller",
            customer_email="bob@example.com",
            pass_data={
                "flight_number": "AB123",
                "origin": "LHR",
                "destination": "JFK",
                "departure_time": "10:30 AM",
                "seat": "12B"
            }
        )
        
        # Verify Apple pass generation for BOARDING_PASS contains transitType
        import io
        import zipfile
        import json
        url_apple = reverse('instance-apple', kwargs={'serial_number': instance.serial_number})
        res_apple = self.client.get(url_apple)
        self.assertEqual(res_apple.status_code, status.HTTP_200_OK)
        
        zip_bytes = io.BytesIO(res_apple.content)
        with zipfile.ZipFile(zip_bytes, 'r') as zf:
            pass_json = json.loads(zf.read('pass.json').decode('utf-8'))
            self.assertIn('boardingPass', pass_json)
            bp = pass_json['boardingPass']
            self.assertEqual(bp['transitType'], 'PKTransitTypeGeneric')
            self.assertEqual(bp['primaryFields'][0]['value'], "LHR")
            self.assertEqual(bp['primaryFields'][1]['value'], "JFK")
            self.assertEqual(bp['secondaryFields'][0]['value'], "10:30 AM")

        # Verify Google save URL contains boarding pass mapping
        from passes.utils.pass_generator import GoogleWalletGenerator
        generator = GoogleWalletGenerator(instance)
        obj_payload = generator.build_object_payload()
        self.assertEqual(obj_payload['flightHeader']['flightNumber'], "AB123")
        self.assertEqual(obj_payload['origin']['airportIataCode'], "LHR")
        self.assertEqual(obj_payload['destination']['airportIataCode'], "JFK")

class PassFlowDashboardTests(TestCase):
    def setUp(self):
        # Company A Setup
        self.company_a = Company.objects.create(name="Company A", slug="company-a")
        self.user_a = User.objects.create_user(username="employee_a", password="password123")
        self.employee_a = Employee.objects.create(user=self.user_a, company=self.company_a, role=Employee.Roles.ADMIN)
        self.template_a = PassTemplate.objects.create(company=self.company_a, pass_type='LOYALTY', title="Card A")

        # Company B Setup
        self.company_b = Company.objects.create(name="Company B", slug="company-b")
        self.user_b = User.objects.create_user(username="employee_b", password="password123")
        self.employee_b = Employee.objects.create(user=self.user_b, company=self.company_b, role=Employee.Roles.ADMIN)
        self.template_b = PassTemplate.objects.create(company=self.company_b, pass_type='LOYALTY', title="Card B")

    def test_dashboard_unauthenticated_redirect(self):
        response = self.client.get(reverse('dashboard-index'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_dashboard_authenticated_access(self):
        self.client.login(username="employee_a", password="password123")
        response = self.client.get(reverse('dashboard-index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Company A")

    def test_dashboard_multitenancy_templates(self):
        # Log in as Employee A
        self.client.login(username="employee_a", password="password123")
        response = self.client.get(reverse('dashboard-templates'))
        self.assertEqual(response.status_code, 200)
        
        # Should display Company A's card, but NOT Company B's card
        self.assertContains(response, "Card A")
        self.assertNotContains(response, "Card B")

    def test_dashboard_registration_success(self):
        response = self.client.post(reverse('register'), {
            'company_name': 'New Merchant Corp',
            'username': 'new_owner',
            'email': 'new_owner@example.com',
            'password': 'securepassword'
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard-index'))
        
        # Verify db records
        company = Company.objects.get(name='New Merchant Corp')
        self.assertEqual(company.slug, 'new-merchant-corp')
        user = User.objects.get(username='new_owner')
        self.assertEqual(user.email, 'new_owner@example.com')
        employee = Employee.objects.get(user=user)
        self.assertEqual(employee.company, company)
        self.assertEqual(employee.role, Employee.Roles.OWNER)


