# accounts/tests.py
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework.test import APIRequestFactory
from django.contrib.auth.models import AnonymousUser
from accounts.permissions import IsCustomer, IsRestaurantOwner, IsDeliveryPartner, IsAdmin
from config.celery import app as celery_app

from accounts.models import Role, User


class UserModelTests(TestCase):
    def test_create_superuser_forces_admin_role(self):
        user = User.objects.create_superuser(username="admin1", password="pass1234")
        self.assertEqual(user.role, Role.ADMIN)

    def test_create_user_does_not_default_to_admin(self):
        user = User.objects.create_user(username="cust1", password="pass1234")
        self.assertNotEqual(user.role, Role.ADMIN)


class RegistrationAPITests(APITestCase):
    def setUp(self):
        self.url = reverse("register")

    def test_customer_can_register(self):
        response = self.client.post(self.url, {
            "username": "cust1",
            "email": "cust1@example.com",
            "password": "StrongPass123!",
            "role": Role.CUSTOMER,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(username="cust1")
        self.assertEqual(user.role, Role.CUSTOMER)
        # password must be hashed, never stored in plain text
        self.assertNotEqual(user.password, "StrongPass123!")
        self.assertTrue(user.check_password("StrongPass123!"))

    def test_restaurant_owner_can_register(self):
        response = self.client.post(self.url, {
            "username": "owner1",
            "email": "owner1@example.com",
            "password": "StrongPass123!",
            "role": Role.RESTAURANT_OWNER,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_delivery_partner_can_register(self):
        response = self.client.post(self.url, {
            "username": "rider1",
            "email": "rider1@example.com",
            "password": "StrongPass123!",
            "role": Role.DELIVERY_PARTNER,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_admin_role_is_rejected(self):
        response = self.client.post(self.url, {
            "username": "wannabe_admin",
            "email": "hacker@example.com",
            "password": "StrongPass123!",
            "role": Role.ADMIN,
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.filter(username="wannabe_admin").exists())

    def test_missing_required_fields_returns_400(self):
        response = self.client.post(self.url, {"username": "incomplete"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_weak_password_is_rejected(self):
        response = self.client.post(self.url, {
            "username": "weakpass",
            "email": "weak@example.com",
            "password": "123",
            "role": Role.CUSTOMER,
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_duplicate_username_is_rejected(self):
        User.objects.create_user(username="dup1", password="StrongPass123!", role=Role.CUSTOMER)
        response = self.client.post(self.url, {
            "username": "dup1",
            "email": "dup2@example.com",
            "password": "StrongPass123!",
            "role": Role.CUSTOMER,
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
from rest_framework_simplejwt.tokens import RefreshToken
# (add this import at the top with the others)


class JWTAuthTests(APITestCase):
    def setUp(self):
        self.login_url = reverse("login")
        self.refresh_url = reverse("refresh")
        self.user = User.objects.create_user(
            username="jwtuser", password="StrongPass123!", role=Role.CUSTOMER
        )

    def test_login_with_valid_credentials_returns_tokens(self):
        response = self.client.post(self.login_url, {
            "username": "jwtuser",
            "password": "StrongPass123!",
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_login_with_invalid_password_is_rejected(self):
        response = self.client.post(self.login_url, {
            "username": "jwtuser",
            "password": "WrongPassword!",
        })
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_with_nonexistent_user_is_rejected(self):
        response = self.client.post(self.login_url, {
            "username": "doesnotexist",
            "password": "whatever123",
        })
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_with_valid_token_returns_new_access_token(self):
        refresh = RefreshToken.for_user(self.user)
        response = self.client.post(self.refresh_url, {"refresh": str(refresh)})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)

    def test_refresh_with_invalid_token_is_rejected(self):
        response = self.client.post(self.refresh_url, {"refresh": "not-a-real-token"})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        
class RolePermissionTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.customer = User.objects.create_user(
            username="perm_customer", password="StrongPass123!", role=Role.CUSTOMER
        )
        self.owner = User.objects.create_user(
            username="perm_owner", password="StrongPass123!", role=Role.RESTAURANT_OWNER
        )
        self.rider = User.objects.create_user(
            username="perm_rider", password="StrongPass123!", role=Role.DELIVERY_PARTNER
        )
        self.admin = User.objects.create_user(
            username="perm_admin", password="StrongPass123!", role=Role.ADMIN
        )

    def _request_as(self, user):
        request = self.factory.get("/")
        request.user = user
        return request

    def test_is_customer_allows_customer(self):
        request = self._request_as(self.customer)
        self.assertTrue(IsCustomer().has_permission(request, None))

    def test_is_customer_rejects_other_roles(self):
        request = self._request_as(self.owner)
        self.assertFalse(IsCustomer().has_permission(request, None))

    def test_is_restaurant_owner_allows_owner(self):
        request = self._request_as(self.owner)
        self.assertTrue(IsRestaurantOwner().has_permission(request, None))

    def test_is_restaurant_owner_rejects_other_roles(self):
        request = self._request_as(self.rider)
        self.assertFalse(IsRestaurantOwner().has_permission(request, None))

    def test_is_delivery_partner_allows_rider(self):
        request = self._request_as(self.rider)
        self.assertTrue(IsDeliveryPartner().has_permission(request, None))

    def test_is_delivery_partner_rejects_other_roles(self):
        request = self._request_as(self.admin)
        self.assertFalse(IsDeliveryPartner().has_permission(request, None))

    def test_is_admin_allows_admin(self):
        request = self._request_as(self.admin)
        self.assertTrue(IsAdmin().has_permission(request, None))

    def test_is_admin_rejects_other_roles(self):
        request = self._request_as(self.customer)
        self.assertFalse(IsAdmin().has_permission(request, None))

    def test_unauthenticated_user_rejected_by_all_permissions(self):
        request = self._request_as(AnonymousUser())
        self.assertFalse(IsCustomer().has_permission(request, None))
        self.assertFalse(IsRestaurantOwner().has_permission(request, None))
        self.assertFalse(IsDeliveryPartner().has_permission(request, None))
        self.assertFalse(IsAdmin().has_permission(request, None))
        
class CeleryConfigTests(TestCase):
    def test_celery_app_is_configured_with_redis_broker(self):
        self.assertTrue(celery_app.conf.broker_url.startswith("redis://"))

    def test_celery_result_backend_is_redis(self):
        self.assertTrue(celery_app.conf.result_backend.startswith("redis://"))
        