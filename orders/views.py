from decimal import Decimal

from django.db import IntegrityError, transaction
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsCustomer
from restaurants.models import Cart, CartItem
from .models import Address, Order, OrderItem
from .serializers import OrderSerializer


class CheckoutView(APIView):
    permission_classes = [IsCustomer]

    def post(self, request):
        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key:
            return Response(
                {"detail": "Idempotency-Key header is required."}, status=400
            )

        address_id = request.data.get("address_id")
        if not address_id:
            return Response({"detail": "address_id is required."}, status=400)

        # Fast path: this exact (customer, key) already produced an order.
        existing = Order.objects.filter(
            customer=request.user, idempotency_key=idempotency_key
        ).first()
        if existing:
            return Response(OrderSerializer(existing).data, status=200)

        try:
            address = Address.objects.get(pk=address_id, customer=request.user)
        except Address.DoesNotExist:
            return Response({"detail": "Address not found."}, status=404)

        with transaction.atomic():
            cart, _ = Cart.objects.get_or_create(customer=request.user)
            # Lock the cart row itself, then lock every cart item AND (via
            # the inner join from select_related) its FoodItem row. This
            # blocks a concurrent price/availability change or a second
            # simultaneous checkout of the same cart until we're done.
            cart = Cart.objects.select_for_update().get(pk=cart.pk)
            cart_items = list(
                CartItem.objects.select_for_update()
                .select_related("food_item")
                .filter(cart=cart)
            )

            if not cart_items:
                return Response({"detail": "Your cart is empty."}, status=400)

            unavailable = [
                ci.food_item.name for ci in cart_items if not ci.food_item.is_available
            ]
            if unavailable:
                return Response(
                    {
                        "detail": "Some items in your cart are no longer available.",
                        "unavailable_items": unavailable,
                    },
                    status=400,
                )

            subtotal = sum(
                (ci.food_item.price * ci.quantity for ci in cart_items),
                Decimal("0.00"),
            )
            discount_amount = Decimal("0.00")
            delivery_fee = Decimal("0.00")
            tax_amount = Decimal("0.00")
            total_amount = subtotal + delivery_fee + tax_amount - discount_amount

            try:
                with transaction.atomic():  # savepoint: isolate the race
                    order = Order.objects.create(
                        customer=request.user,
                        restaurant=cart.restaurant,
                        delivery_address=address,
                        subtotal=subtotal,
                        discount_amount=discount_amount,
                        delivery_fee=delivery_fee,
                        tax_amount=tax_amount,
                        total_amount=total_amount,
                        idempotency_key=idempotency_key,
                    )
                    OrderItem.objects.bulk_create(
                        [
                            OrderItem(
                                order=order,
                                food_item=ci.food_item,
                                food_item_name=ci.food_item.name,
                                price_at_purchase=ci.food_item.price,
                                quantity=ci.quantity,
                            )
                            for ci in cart_items
                        ]
                    )
            except IntegrityError:
                # Another request with the same (customer, key) won the race
                # and committed first — return their order, not an error.
                winning_order = Order.objects.get(
                    customer=request.user, idempotency_key=idempotency_key
                )
                return Response(OrderSerializer(winning_order).data, status=200)

            cart_items_ids = [ci.id for ci in cart_items]
            CartItem.objects.filter(id__in=cart_items_ids).delete()
            cart.restaurant = None
            cart.save()

        return Response(OrderSerializer(order).data, status=201)