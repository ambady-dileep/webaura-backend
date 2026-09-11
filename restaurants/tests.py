from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from accounts.models import Role, User
from .models import Restaurant, Category, FoodItem, CartItem, Cart
from decimal import Decimal


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
        
        
        
        
        
        
class MenuAPITests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="menu_owner", password="StrongPass123!", role=Role.RESTAURANT_OWNER
        )
        self.other_owner = User.objects.create_user(
            username="menu_other_owner", password="StrongPass123!", role=Role.RESTAURANT_OWNER
        )
        self.customer = User.objects.create_user(
            username="menu_customer", password="StrongPass123!", role=Role.CUSTOMER
        )
        self.restaurant = Restaurant.objects.create(
            owner=self.owner, name="Menu Place", address="X"
        )
        self.other_restaurant = Restaurant.objects.create(
            owner=self.other_owner, name="Other Place", address="Y"
        )
        self.category = Category.objects.create(restaurant=self.restaurant, name="Mains")
        self.other_category = Category.objects.create(
            restaurant=self.other_restaurant, name="Other Mains"
        )

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    # --- Category ---

    def test_owner_can_create_category_for_own_restaurant(self):
        self._auth(self.owner)
        url = reverse("category-list-create", args=[self.restaurant.id])
        response = self.client.post(url, {"name": "Starters"})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_other_owner_cannot_create_category_for_this_restaurant(self):
        self._auth(self.other_owner)
        url = reverse("category-list-create", args=[self.restaurant.id])
        response = self.client.post(url, {"name": "Hacked"})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_anyone_can_list_categories(self):
        url = reverse("category-list-create", args=[self.restaurant.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # --- FoodItem create/update ---

    def test_owner_can_create_food_item(self):
        self._auth(self.owner)
        response = self.client.post(reverse("food-create"), {
            "restaurant": self.restaurant.id,
            "category": self.category.id,
            "name": "Burger",
            "description": "Tasty",
            "price": "9.99",
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_cannot_create_food_item_for_restaurant_you_dont_own(self):
        self._auth(self.other_owner)
        response = self.client.post(reverse("food-create"), {
            "restaurant": self.restaurant.id,
            "category": self.category.id,
            "name": "Sneaky Burger",
            "price": "9.99",
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_use_category_from_a_different_restaurant(self):
        self._auth(self.owner)
        response = self.client.post(reverse("food-create"), {
            "restaurant": self.restaurant.id,
            "category": self.other_category.id,
            "name": "Mismatched Burger",
            "price": "9.99",
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_owner_can_update_own_food_item(self):
        food = FoodItem.objects.create(
            restaurant=self.restaurant, category=self.category, name="Fries", price="3.50"
        )
        self._auth(self.owner)
        url = reverse("food-detail", args=[food.id])
        response = self.client.patch(url, {"price": "4.00"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        food.refresh_from_db()
        self.assertEqual(str(food.price), "4.00")

    def test_other_owner_cannot_update_food_item(self):
        food = FoodItem.objects.create(
            restaurant=self.restaurant, category=self.category, name="Fries", price="3.50"
        )
        self._auth(self.other_owner)
        url = reverse("food-detail", args=[food.id])
        response = self.client.patch(url, {"price": "0.01"})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # --- Menu endpoint ---

    def test_menu_excludes_unavailable_items(self):
        FoodItem.objects.create(
            restaurant=self.restaurant, category=self.category, name="Visible", price="5.00"
        )
        FoodItem.objects.create(
            restaurant=self.restaurant, category=self.category, name="Hidden",
            price="5.00", is_available=False,
        )
        url = reverse("restaurant-menu", args=[self.restaurant.id])
        response = self.client.get(url)
        names = [f["name"] for f in response.data["results"]]
        self.assertIn("Visible", names)
        self.assertNotIn("Hidden", names)

    def test_menu_search_is_case_insensitive(self):
        FoodItem.objects.create(
            restaurant=self.restaurant, category=self.category, name="Cheese Pizza", price="8.00"
        )
        url = reverse("restaurant-menu", args=[self.restaurant.id])
        response = self.client.get(url, {"search": "pizza"})
        names = [f["name"] for f in response.data["results"]]
        self.assertIn("Cheese Pizza", names)

    def test_menu_hidden_for_inactive_restaurant_to_non_owner(self):
        self.restaurant.is_active = False
        self.restaurant.save()
        self._auth(self.customer)
        url = reverse("restaurant-menu", args=[self.restaurant.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_menu_still_visible_to_owner_when_inactive(self):
        self.restaurant.is_active = False
        self.restaurant.save()
        self._auth(self.owner)
        url = reverse("restaurant-menu", args=[self.restaurant.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        
        
class CartAPITests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="cart_owner", password="StrongPass123!", role=Role.RESTAURANT_OWNER
        )
        self.customer = User.objects.create_user(
            username="cart_customer", password="StrongPass123!", role=Role.CUSTOMER
        )
        self.restaurant_a = Restaurant.objects.create(owner=self.owner, name="A", address="X")
        self.restaurant_b = Restaurant.objects.create(owner=self.owner, name="B", address="Y")
        self.category_a = Category.objects.create(restaurant=self.restaurant_a, name="Mains")
        self.category_b = Category.objects.create(restaurant=self.restaurant_b, name="Mains")
        self.food_a1 = FoodItem.objects.create(
            restaurant=self.restaurant_a, category=self.category_a, name="Burger A", price="5.00"
        )
        self.food_a2 = FoodItem.objects.create(
            restaurant=self.restaurant_a, category=self.category_a, name="Fries A", price="3.00"
        )
        self.food_b1 = FoodItem.objects.create(
            restaurant=self.restaurant_b, category=self.category_b, name="Burger B", price="6.00"
        )
        self.client.force_authenticate(user=self.customer)

    def test_get_cart_creates_empty_cart(self):
        response = self.client.get(reverse("cart-detail"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["items"], [])
        self.assertIsNone(response.data["restaurant"])

    def test_add_item_sets_cart_restaurant(self):
        response = self.client.post(reverse("cart-item-create"), {
            "food_item": self.food_a1.id, "quantity": 2,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        cart = Cart.objects.get(customer=self.customer)
        self.assertEqual(cart.restaurant, self.restaurant_a)

    def test_adding_same_item_increments_quantity_not_duplicate_row(self):
        self.client.post(reverse("cart-item-create"), {"food_item": self.food_a1.id, "quantity": 1})
        self.client.post(reverse("cart-item-create"), {"food_item": self.food_a1.id, "quantity": 2})
        cart = Cart.objects.get(customer=self.customer)
        self.assertEqual(cart.items.count(), 1)
        self.assertEqual(cart.items.first().quantity, 3)

    def test_cannot_add_item_from_different_restaurant(self):
        self.client.post(reverse("cart-item-create"), {"food_item": self.food_a1.id, "quantity": 1})
        response = self.client.post(reverse("cart-item-create"), {"food_item": self.food_b1.id, "quantity": 1})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        cart = Cart.objects.get(customer=self.customer)
        self.assertEqual(cart.items.count(), 1)

    def test_subtotal_reflects_live_prices(self):
        self.client.post(reverse("cart-item-create"), {"food_item": self.food_a1.id, "quantity": 2})
        self.client.post(reverse("cart-item-create"), {"food_item": self.food_a2.id, "quantity": 1})
        response = self.client.get(reverse("cart-detail"))
        # 2 * 5.00 + 1 * 3.00 = 13.00
        self.assertEqual(response.data["subtotal"], Decimal("13.00"))

        self.food_a1.price = Decimal("10.00")
        self.food_a1.save()
        response = self.client.get(reverse("cart-detail"))
        # 2 * 10.00 + 1 * 3.00 = 23.00 — proves it's live, not stored
        self.assertEqual(response.data["subtotal"], Decimal("23.00"))

    def test_delete_cart_clears_items_and_restaurant(self):
        self.client.post(reverse("cart-item-create"), {"food_item": self.food_a1.id, "quantity": 1})
        response = self.client.delete(reverse("cart-detail"))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        cart = Cart.objects.get(customer=self.customer)
        self.assertIsNone(cart.restaurant)
        self.assertEqual(cart.items.count(), 0)

    def test_can_add_from_new_restaurant_after_clearing(self):
        self.client.post(reverse("cart-item-create"), {"food_item": self.food_a1.id, "quantity": 1})
        self.client.delete(reverse("cart-detail"))
        response = self.client.post(reverse("cart-item-create"), {"food_item": self.food_b1.id, "quantity": 1})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_customer_can_update_own_cart_item_quantity(self):
        create_response = self.client.post(
            reverse("cart-item-create"), {"food_item": self.food_a1.id, "quantity": 1}
        )
        item_id = create_response.data["id"]
        response = self.client.patch(reverse("cart-item-detail", args=[item_id]), {"quantity": 5})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(CartItem.objects.get(pk=item_id).quantity, 5)

    def test_customer_can_delete_own_cart_item(self):
        create_response = self.client.post(
            reverse("cart-item-create"), {"food_item": self.food_a1.id, "quantity": 1}
        )
        item_id = create_response.data["id"]
        response = self.client.delete(reverse("cart-item-detail", args=[item_id]))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_customer_cannot_touch_another_customers_cart_item(self):
        other_customer = User.objects.create_user(
            username="other_cust", password="StrongPass123!", role=Role.CUSTOMER
        )
        self.client.force_authenticate(user=other_customer)
        create_response = self.client.post(
            reverse("cart-item-create"), {"food_item": self.food_a1.id, "quantity": 1}
        )
        item_id = create_response.data["id"]

        self.client.force_authenticate(user=self.customer)
        response = self.client.patch(reverse("cart-item-detail", args=[item_id]), {"quantity": 99})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_restaurant_owner_cannot_access_cart_endpoints(self):
        self.client.force_authenticate(user=self.owner)
        response = self.client.get(reverse("cart-detail"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)