from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase

from accounts.models import Role, User
from restaurants.models import Category, FoodItem, Restaurant, Cart, CartItem
from .models import Address, Order, OrderItem, OrderStatus, InvalidStatusTransition 
from rest_framework.test import APIClient


class OrderModelTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="order_owner", password="StrongPass123!", role=Role.RESTAURANT_OWNER
        )
        self.customer = User.objects.create_user(
            username="order_customer", password="StrongPass123!", role=Role.CUSTOMER
        )
        self.restaurant = Restaurant.objects.create(
            owner=self.owner, name="Order Place", address="X"
        )
        self.category = Category.objects.create(restaurant=self.restaurant, name="Mains")
        self.food_item = FoodItem.objects.create(
            restaurant=self.restaurant, category=self.category,
            name="Burger", price=Decimal("100.00"),
        )
        self.address = Address.objects.create(
            customer=self.customer, label="Home", full_address="123 St",
            city="Kochi", pincode="682001", phone_number="9999999999",
        )

    def _create_order(self, **overrides):
        defaults = dict(
            customer=self.customer,
            restaurant=self.restaurant,
            delivery_address=self.address,
            subtotal=Decimal("100.00"),
            total_amount=Decimal("100.00"),
        )
        defaults.update(overrides)
        return Order.objects.create(**defaults)

    def test_order_number_is_auto_generated(self):
        order = self._create_order()
        self.assertTrue(order.order_number.startswith("ORD-"))

    def test_order_number_is_unique_across_orders(self):
        order1 = self._create_order()
        order2 = self._create_order()
        self.assertNotEqual(order1.order_number, order2.order_number)

    def test_default_status_is_placed(self):
        order = self._create_order()
        self.assertEqual(order.status, OrderStatus.PLACED)

    def test_idempotency_key_must_be_unique(self):
        self._create_order(idempotency_key="key-123")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._create_order(idempotency_key="key-123")

    def test_multiple_orders_can_have_null_idempotency_key(self):
        order1 = self._create_order()
        order2 = self._create_order()
        self.assertIsNone(order1.idempotency_key)
        self.assertIsNone(order2.idempotency_key)

    def test_order_item_snapshots_price_and_name(self):
        order = self._create_order()
        item = OrderItem.objects.create(
            order=order, food_item=self.food_item,
            food_item_name=self.food_item.name,
            price_at_purchase=self.food_item.price,
            quantity=2,
        )
        self.assertEqual(item.price_at_purchase, Decimal("100.00"))
        self.assertEqual(item.line_total, Decimal("200.00"))

    def test_order_item_price_unaffected_by_later_menu_price_change(self):
        order = self._create_order()
        item = OrderItem.objects.create(
            order=order, food_item=self.food_item,
            food_item_name=self.food_item.name,
            price_at_purchase=self.food_item.price,
            quantity=1,
        )
        self.food_item.price = Decimal("999.00")
        self.food_item.save()

        item.refresh_from_db()
        self.assertEqual(item.price_at_purchase, Decimal("100.00"))

    def test_order_item_survives_food_item_deletion(self):
        order = self._create_order()
        item = OrderItem.objects.create(
            order=order, food_item=self.food_item,
            food_item_name=self.food_item.name,
            price_at_purchase=self.food_item.price,
            quantity=1,
        )
        self.food_item.delete()
        item.refresh_from_db()
        self.assertIsNone(item.food_item)
        self.assertEqual(item.food_item_name, "Burger")
        self.assertEqual(item.price_at_purchase, Decimal("100.00"))

    def test_cannot_delete_restaurant_with_existing_orders(self):
        self._create_order()
        with self.assertRaises(ProtectedError):
            self.restaurant.delete()

    def test_cannot_delete_customer_with_existing_orders(self):
        self._create_order()
        with self.assertRaises(ProtectedError):
            self.customer.delete()

    def test_cannot_delete_address_with_existing_orders(self):
        self._create_order()
        with self.assertRaises(ProtectedError):
            self.address.delete()

    def test_deleting_order_cascades_to_order_items(self):
        order = self._create_order()
        OrderItem.objects.create(
            order=order, food_item=self.food_item, food_item_name="Burger",
            price_at_purchase=Decimal("100.00"), quantity=1,
        )
        order_id = order.id
        order.delete()
        self.assertEqual(OrderItem.objects.filter(order_id=order_id).count(), 0)
        
class OrderStateMachineTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="sm_owner", password="StrongPass123!", role=Role.RESTAURANT_OWNER
        )
        self.customer = User.objects.create_user(
            username="sm_customer", password="StrongPass123!", role=Role.CUSTOMER
        )
        self.restaurant = Restaurant.objects.create(
            owner=self.owner, name="State Machine Place", address="X"
        )
        self.address = Address.objects.create(
            customer=self.customer, label="Home", full_address="123 St",
            city="Kochi", pincode="682001", phone_number="9999999999",
        )
        self.order = Order.objects.create(
            customer=self.customer, restaurant=self.restaurant,
            delivery_address=self.address,
            subtotal=Decimal("100.00"), total_amount=Decimal("100.00"),
        )

    def test_placed_can_move_to_accepted(self):
        self.order.transition_to(OrderStatus.ACCEPTED)
        self.assertEqual(self.order.status, OrderStatus.ACCEPTED)

    def test_placed_can_move_to_rejected(self):
        self.order.transition_to(OrderStatus.REJECTED)
        self.assertEqual(self.order.status, OrderStatus.REJECTED)

    def test_placed_cannot_move_to_preparing_directly(self):
        with self.assertRaises(InvalidStatusTransition):
            self.order.transition_to(OrderStatus.PREPARING)

    def test_delivered_is_terminal(self):
        self.order.status = OrderStatus.DELIVERED
        with self.assertRaises(InvalidStatusTransition):
            self.order.transition_to(OrderStatus.PLACED)

    def test_full_happy_path_transition_chain(self):
        self.order.transition_to(OrderStatus.ACCEPTED)
        self.order.transition_to(OrderStatus.PREPARING)
        self.order.transition_to(OrderStatus.OUT_FOR_DELIVERY)
        self.order.transition_to(OrderStatus.DELIVERED)
        self.assertEqual(self.order.status, OrderStatus.DELIVERED)

    def test_cancelled_is_terminal(self):
        self.order.transition_to(OrderStatus.CANCELLED)
        with self.assertRaises(InvalidStatusTransition):
            self.order.transition_to(OrderStatus.PLACED)

    def test_transition_does_not_persist_without_explicit_save(self):
        self.order.transition_to(OrderStatus.ACCEPTED)
        reloaded = Order.objects.get(pk=self.order.pk)
        self.assertEqual(reloaded.status, OrderStatus.PLACED)
        

class CheckoutViewTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="checkout_owner", password="StrongPass123!", role=Role.RESTAURANT_OWNER
        )
        self.customer = User.objects.create_user(
            username="checkout_customer", password="StrongPass123!", role=Role.CUSTOMER
        )
        self.restaurant = Restaurant.objects.create(
            owner=self.owner, name="Checkout Place", address="X"
        )
        self.category = Category.objects.create(restaurant=self.restaurant, name="Mains")
        self.food_item = FoodItem.objects.create(
            restaurant=self.restaurant, category=self.category,
            name="Pizza", price=Decimal("250.00"),
        )
        self.address = Address.objects.create(
            customer=self.customer, label="Home", full_address="123 St",
            city="Kochi", pincode="682001", phone_number="9999999999",
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.customer)

    def _add_to_cart(self, quantity=2):
        cart, _ = Cart.objects.get_or_create(customer=self.customer)
        cart.restaurant = self.restaurant
        cart.save()
        CartItem.objects.create(cart=cart, food_item=self.food_item, quantity=quantity)
        return cart

    def test_checkout_without_idempotency_header_returns_400(self):
        self._add_to_cart()
        response = self.client.post(
            "/api/orders/checkout/", {"address_id": self.address.id}
        )
        self.assertEqual(response.status_code, 400)

    def test_checkout_with_empty_cart_returns_400(self):
        response = self.client.post(
            "/api/orders/checkout/",
            {"address_id": self.address.id},
            HTTP_IDEMPOTENCY_KEY="key-1",
        )
        self.assertEqual(response.status_code, 400)

    def test_checkout_with_unavailable_item_returns_400(self):
        self._add_to_cart()
        self.food_item.is_available = False
        self.food_item.save()
        response = self.client.post(
            "/api/orders/checkout/",
            {"address_id": self.address.id},
            HTTP_IDEMPOTENCY_KEY="key-2",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("unavailable_items", response.data)

    def test_successful_checkout_creates_order_and_clears_cart(self):
        cart = self._add_to_cart(quantity=3)
        response = self.client.post(
            "/api/orders/checkout/",
            {"address_id": self.address.id},
            HTTP_IDEMPOTENCY_KEY="key-3",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["subtotal"], "750.00")
        cart.refresh_from_db()
        self.assertEqual(cart.items.count(), 0)
        self.assertIsNone(cart.restaurant)

    def test_duplicate_idempotency_key_returns_same_order_not_a_new_one(self):
        self._add_to_cart()
        first = self.client.post(
            "/api/orders/checkout/",
            {"address_id": self.address.id},
            HTTP_IDEMPOTENCY_KEY="key-4",
        )
        self.assertEqual(first.status_code, 201)

        # Cart is empty now, but replay should NOT hit the "empty cart" branch
        # — it should short-circuit before touching the cart at all.
        second = self.client.post(
            "/api/orders/checkout/",
            {"address_id": self.address.id},
            HTTP_IDEMPOTENCY_KEY="key-4",
        )
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data["order_number"], second.data["order_number"])
        self.assertEqual(Order.objects.count(), 1)

    def test_menu_price_change_after_checkout_does_not_affect_order_total(self):
        self._add_to_cart(quantity=1)
        response = self.client.post(
            "/api/orders/checkout/",
            {"address_id": self.address.id},
            HTTP_IDEMPOTENCY_KEY="key-5",
        )
        order = Order.objects.get(order_number=response.data["order_number"])

        self.food_item.price = Decimal("999.00")
        self.food_item.save()

        order.refresh_from_db()
        self.assertEqual(order.subtotal, Decimal("250.00"))
        self.assertEqual(order.total_amount, Decimal("250.00"))

    def test_different_customers_can_reuse_the_same_idempotency_key(self):
        other_customer = User.objects.create_user(
            username="checkout_customer_2", password="StrongPass123!", role=Role.CUSTOMER
        )
        other_address = Address.objects.create(
            customer=other_customer, label="Home", full_address="456 St",
            city="Kochi", pincode="682002", phone_number="8888888888",
        )
        self._add_to_cart()
        first = self.client.post(
            "/api/orders/checkout/",
            {"address_id": self.address.id},
            HTTP_IDEMPOTENCY_KEY="shared-key",
        )
        self.assertEqual(first.status_code, 201)

        other_cart, _ = Cart.objects.get_or_create(customer=other_customer)
        other_cart.restaurant = self.restaurant
        other_cart.save()
        CartItem.objects.create(cart=other_cart, food_item=self.food_item, quantity=1)

        other_client = APIClient()
        other_client.force_authenticate(user=other_customer)
        second = other_client.post(
            "/api/orders/checkout/",
            {"address_id": other_address.id},
            HTTP_IDEMPOTENCY_KEY="shared-key",
        )
        self.assertEqual(second.status_code, 201)
        self.assertNotEqual(first.data["order_number"], second.data["order_number"])