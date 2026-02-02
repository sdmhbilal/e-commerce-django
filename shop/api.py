from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.contrib.auth import authenticate
from django.db import transaction
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from shop.models import Cart, CartItem, Coupon, Product, create_order_from_cart
from shop.serializers import (
    CartItemSerializer,
    CartSerializer,
    CouponValidateSerializer,
    CouponValidationResultSerializer,
    LoginSerializer,
    OrderCreateSerializer,
    OrderSerializer,
    ProductSerializer,
    RegisterSerializer,
)


def _min_order_amount() -> Decimal:
    raw = getattr(settings, "MIN_ORDER_AMOUNT", None) or "0"
    try:
        return Decimal(str(raw)).quantize(Decimal("0.01"))
    except Exception:
        return Decimal("0.00")


def _get_or_create_cart(request) -> Cart:
    """
    Authenticated: single active cart per user (checked_out_at is null)
    Guest: use X-Cart-Token header (UUID). If missing, create new guest cart.
    """
    if request.user.is_authenticated:
        cart, _ = Cart.objects.get_or_create(user=request.user, checked_out_at__isnull=True)
        return cart

    token = request.headers.get("X-Cart-Token") or request.query_params.get("cart_token")
    if token:
        try:
            return Cart.objects.get(guest_token=token, checked_out_at__isnull=True)
        except Cart.DoesNotExist:
            pass
    return Cart.objects.create()


@api_view(["POST"])
@permission_classes([AllowAny])
def register(request):
    s = RegisterSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    user = s.save()
    token, _ = Token.objects.get_or_create(user=user)
    return Response({"token": token.key})


@api_view(["POST"])
@permission_classes([AllowAny])
def login(request):
    s = LoginSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    user = authenticate(username=s.validated_data["username"], password=s.validated_data["password"])
    if not user:
        return Response({"detail": "Invalid credentials."}, status=status.HTTP_400_BAD_REQUEST)
    token, _ = Token.objects.get_or_create(user=user)
    return Response({"token": token.key})


@api_view(["GET"])
@permission_classes([AllowAny])
def products_list(request):
    qs = Product.objects.filter(is_active=True).order_by("id")
    return Response(ProductSerializer(qs, many=True, context={"request": request}).data)


@api_view(["GET"])
@permission_classes([AllowAny])
def cart_detail(request):
    cart = _get_or_create_cart(request)
    return Response(CartSerializer(cart, context={"request": request}).data)


@api_view(["POST"])
@permission_classes([AllowAny])
@transaction.atomic
def cart_item_add(request):
    cart = _get_or_create_cart(request)
    s = CartItemSerializer(data=request.data, context={"request": request})
    s.is_valid(raise_exception=True)
    product: Product = s.validated_data["product"]
    quantity: int = int(s.validated_data["quantity"])

    if quantity > product.stock_quantity:
        return Response({"detail": "Insufficient stock."}, status=status.HTTP_400_BAD_REQUEST)

    item, created = CartItem.objects.select_for_update().get_or_create(
        cart=cart, product=product, defaults={"quantity": quantity, "unit_price": product.price}
    )
    if not created:
        new_qty = item.quantity + quantity
        if new_qty > product.stock_quantity:
            return Response({"detail": "Insufficient stock."}, status=status.HTTP_400_BAD_REQUEST)
        item.quantity = new_qty
        item.unit_price = product.price
        item.save(update_fields=["quantity", "unit_price", "updated_at"])

    return Response(CartSerializer(cart, context={"request": request}).data, status=status.HTTP_200_OK)


@api_view(["PATCH"])
@permission_classes([AllowAny])
@transaction.atomic
def cart_item_update(request, item_id: int):
    cart = _get_or_create_cart(request)
    try:
        item = CartItem.objects.select_for_update().select_related("product").get(cart=cart, id=item_id)
    except CartItem.DoesNotExist:
        return Response({"detail": "Item not found."}, status=status.HTTP_404_NOT_FOUND)

    qty = request.data.get("quantity")
    if qty is None:
        return Response({"detail": "quantity is required."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        qty = int(qty)
    except Exception:
        return Response({"detail": "quantity must be an integer."}, status=status.HTTP_400_BAD_REQUEST)
    if qty < 1:
        return Response({"detail": "quantity must be >= 1."}, status=status.HTTP_400_BAD_REQUEST)
    if qty > item.product.stock_quantity:
        return Response({"detail": "Insufficient stock."}, status=status.HTTP_400_BAD_REQUEST)

    item.quantity = qty
    item.unit_price = item.product.price
    item.save(update_fields=["quantity", "unit_price", "updated_at"])
    return Response(CartSerializer(cart, context={"request": request}).data)


@api_view(["DELETE"])
@permission_classes([AllowAny])
def cart_item_delete(request, item_id: int):
    cart = _get_or_create_cart(request)
    CartItem.objects.filter(cart=cart, id=item_id).delete()
    return Response(CartSerializer(cart, context={"request": request}).data)


@api_view(["POST"])
@permission_classes([AllowAny])
def coupon_validate(request):
    cart = _get_or_create_cart(request)
    s = CouponValidateSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    code = s.validated_data["code"].strip()
    try:
        coupon = Coupon.objects.get(code__iexact=code)
    except Coupon.DoesNotExist:
        return Response({"detail": "Invalid coupon code."}, status=status.HTTP_400_BAD_REQUEST)

    ok, msg = coupon.is_applicable_to_cart(cart)
    if not ok:
        return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)

    subtotal = cart.subtotal()
    discount = coupon.compute_discount(cart)
    total = (subtotal - discount).quantize(Decimal("0.01"))

    data = CouponValidationResultSerializer(
        {
            "code": coupon.code,
            "discount_amount": discount,
            "subtotal_amount": subtotal,
            "total_amount": total,
        }
    ).data
    return Response(data)


@api_view(["POST"])
@permission_classes([AllowAny])
def order_create(request):
    cart = _get_or_create_cart(request)
    s = OrderCreateSerializer(data=request.data, context={"request": request})
    s.is_valid(raise_exception=True)

    coupon = None
    code = (s.validated_data.get("coupon_code") or "").strip()
    if code:
        try:
            coupon = Coupon.objects.get(code__iexact=code)
        except Coupon.DoesNotExist:
            return Response({"detail": "Invalid coupon code."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        order = create_order_from_cart(
            cart=cart,
            user=request.user if request.user.is_authenticated else None,
            guest_full_name=s.validated_data.get("guest_full_name", ""),
            guest_email=s.validated_data.get("guest_email", ""),
            coupon=coupon,
            min_order_amount=_min_order_amount(),
        )
    except ValueError as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    return Response(OrderSerializer(order, context={"request": request}).data, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    return Response({"id": request.user.id, "username": request.user.get_username(), "email": request.user.email})

