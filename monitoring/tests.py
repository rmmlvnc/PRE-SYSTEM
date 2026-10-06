import json
from pathlib import Path

from django.test import RequestFactory, TestCase
from django.template.loader import get_template

from .locations import ILIGAN_BARANGAYS, canonicalize_barangay
from .models import Barangay, Purok, UserAccount
from .views import build_hotspot_data, load_dengue_cases


class MobileApiTests(TestCase):
    def setUp(self):
        self.barangay = Barangay.objects.create(barangay_name="Abuno")
        self.purok = Purok.objects.create(barangay=self.barangay, purok_name="Test Purok")

    def test_health_and_locations_are_public(self):
        health = self.client.get('/api/mobile/health/')
        locations = self.client.get('/api/mobile/locations/')

        self.assertEqual(health.status_code, 200)
        self.assertTrue(health.json()['success'])
        self.assertEqual(locations.status_code, 200)
        self.assertEqual(locations.json()['barangays'][0]['puroks'][0]['name'], 'Test Purok')

    def test_canonical_barangay_scope_is_exactly_44_official_labels(self):
        self.assertEqual(len(ILIGAN_BARANGAYS), 44)
        self.assertEqual(len(set(ILIGAN_BARANGAYS)), 44)
        self.assertEqual(canonicalize_barangay('Maria-Cristina'), 'Maria Cristina')
        self.assertIsNone(canonicalize_barangay('Old Poblacion'))

    def test_patient_dataset_loader_excludes_non_iligan_barangay_labels(self):
        cases = load_dengue_cases()
        self.assertGreater(len(cases), 0)
        self.assertTrue(all(case['barangay'] in ILIGAN_BARANGAYS for case in cases))

    def test_saray_and_tibanga_remain_distinct_canonical_barangays(self):
        cases = load_dengue_cases()
        labels = {case['barangay'] for case in cases}
        self.assertIn('Saray', labels)
        self.assertIn('Tibanga', labels)
        self.assertNotEqual(canonicalize_barangay('Saray'), canonicalize_barangay('Tibanga'))
        self.assertTrue(any(case['blood_type'] != 'N/A' for case in cases))

    def test_web_hotspot_data_has_all_44_official_barangays(self):
        context = build_hotspot_data(RequestFactory().get('/hotspot-map/'))
        labels = {item['barangay'] for item in context['hotspot_data']}
        self.assertEqual(labels, set(ILIGAN_BARANGAYS))
        self.assertEqual(context['total_barangays'], 44)

    def test_web_api_preflight_is_allowed(self):
        response = self.client.options(
            '/api/mobile/auth/register/',
            HTTP_ORIGIN='http://localhost:8081',
            HTTP_ACCESS_CONTROL_REQUEST_METHOD='POST',
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response['Access-Control-Allow-Origin'], 'http://localhost:8081')

    def test_resident_can_register_and_use_authenticated_endpoint(self):
        response = self.client.post(
            '/api/mobile/auth/register/',
            data=json.dumps({
                'first_name': 'Ada',
                'last_name': 'Resident',
                'email': 'ada@example.com',
                'password': 'safe-password-123',
                'barangay_id': self.barangay.pk,
                'purok_id': self.purok.pk,
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 201)
        token = response.json()['token']
        profile = self.client.get('/api/mobile/me/', HTTP_AUTHORIZATION=f'Bearer {token}')
        self.assertEqual(profile.status_code, 200)
        self.assertEqual(profile.json()['user']['email'], 'ada@example.com')


class RoleSidebarTests(TestCase):
    def dashboard_response(self, role, url):
        user = UserAccount.objects.create_user(
            username=f'{role.lower()}_user',
            password='safe-password-123',
            first_name=role,
            last_name='Tester',
            role=role,
            account_status='APPROVED',
        )
        self.client.force_login(user)
        return self.client.get(url)

    def test_each_role_dashboard_displays_the_signed_in_user(self):
        pages = [
            ('CHO', '/dashboard/cho/'),
            ('CHW', '/dashboard/chw/'),
            ('BHW', '/dashboard/bhw/'),
            ('LGU', '/lgu-dashboard/'),
        ]
        for role, url in pages:
            with self.subTest(role=role):
                response = self.dashboard_response(role, url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, f'{role} Tester')
                self.assertContains(response, UserAccount.ROLE_CHOICES[[item[0] for item in UserAccount.ROLE_CHOICES].index(role)][1])

    def test_every_dashboard_template_compiles(self):
        templates_dir = Path(__file__).resolve().parent / 'templates'
        templates = list(templates_dir.glob('*.html'))
        self.assertGreater(len(templates), 0)
        for template in templates:
            with self.subTest(template=template.name):
                get_template(template.name)
