from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Role, User
from .models import Restaurant


class RestaurantAPITests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner1", password="StrongPass123!", role=Role.RESTAURANT_OWNER
        )
        self.other_owner = User.objects.create_user(
            username="owner2", password="StrongPass123!", role=Role.RESTAURANT_OWNER
        )
        self.customer = User.objects.create_user(
            username="cust1", password="StrongPass123!", role=Role.CUSTOMER
        )
        self.list_url = reverse("restaurant-list")

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def test_anyone_can_list_restaurants_without_auth(self):
        Restaurant.objects.create(owner=self.owner, name="Pizza Place", address="123 St")
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]) if "results" in response.data else len(response.data), 1)

    def test_inactive_restaurant_excluded_from_public_list(self):
        Restaurant.objects.create(owner=self.owner, name="Closed Place", address="X", is_active=False)
        response = self.client.get(self.list_url)
        names = [r["name"] for r in (response.data["results"] if "results" in response.data else response.data)]
        self.assertNotIn("Closed Place", names)

    def test_owner_still_sees_own_inactive_restaurant_in_list(self):
        Restaurant.objects.create(owner=self.owner, name="My Closed Place", address="X", is_active=False)
        self._auth(self.owner)
        response = self.client.get(self.list_url)
        names = [r["name"] for r in (response.data["results"] if "results" in response.data else response.data)]
        self.assertIn("My Closed Place", names)

    def test_restaurant_owner_can_create_restaurant(self):
        self._auth(self.owner)
        response = self.client.post(self.list_url, {
            "name": "New Place", "address": "456 Ave", "description": "desc",
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        restaurant = Restaurant.objects.get(name="New Place")
        self.assertEqual(restaurant.owner, self.owner)

    def test_customer_cannot_create_restaurant(self):
        self._auth(self.customer)
        response = self.client.post(self.list_url, {"name": "Nope", "address": "X"})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_user_cannot_create_restaurant(self):
        response = self.client.post(self.list_url, {"name": "Nope", "address": "X"})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_owner_can_update_own_restaurant(self):
        restaurant = Restaurant.objects.create(owner=self.owner, name="Old Name", address="X")
        self._auth(self.owner)
        url = reverse("restaurant-detail", args=[restaurant.id])
        response = self.client.patch(url, {"name": "New Name"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        restaurant.refresh_from_db()
        self.assertEqual(restaurant.name, "New Name")

    def test_other_owner_cannot_update_restaurant(self):
        restaurant = Restaurant.objects.create(owner=self.owner, name="Old Name", address="X")
        self._auth(self.other_owner)
        url = reverse("restaurant-detail", args=[restaurant.id])
        response = self.client.patch(url, {"name": "Hacked"})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        restaurant.refresh_from_db()
        self.assertEqual(restaurant.name, "Old Name")

    def test_deactivated_restaurant_hidden_from_others_detail_view(self):
        restaurant = Restaurant.objects.create(
            owner=self.owner, name="Closed", address="X", is_active=False
        )
        self._auth(self.customer)
        url = reverse("restaurant-detail", args=[restaurant.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_owner_can_still_view_own_deactivated_restaurant(self):
        restaurant = Restaurant.objects.create(
            owner=self.owner, name="Closed", address="X", is_active=False
        )
        self._auth(self.owner)
        url = reverse("restaurant-detail", args=[restaurant.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)