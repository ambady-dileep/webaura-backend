# accounts/tests.py
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

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