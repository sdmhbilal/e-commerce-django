from __future__ import annotations

import random
import string
from decimal import Decimal

from django.contrib.auth import authenticate, get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from shop.constants import CART_TOKEN_HEADER, CART_TOKEN_QUERY_PARAM
from shop.models import (
    Cart,
    CartItem,
    Coupon,
    EmailChangeRequest,
    EmailVerificationCode,
    Order,
    Product,
    UserProfile,
    create_order_from_cart,
)
from shop.services import (
    get_min_order_amount,
    get_otp_expire_minutes,
    send_email_change_otp,
    send_order_confirmation_email,
    send_otp_email,
)
from shop.serializers import (
    CartItemSerializer,
    CartSerializer,
    CouponValidateSerializer,
    CouponValidationResultSerializer,
    LoginSerializer,
    OrderCreateSerializer,
    OrderSerializer,
    ProductSerializer,
    ProfileUpdateSerializer,
    RegisterSerializer,
    VerifyEmailSerializer,
    VerifyEmailChangeSerializer,
)

User = get_user_model()


def _merge_guest_cart_into_user_cart(user_cart: Cart, guest_cart: Cart) -> None:
    for guest_item in guest_cart.items.select_related("product").all():
        existing = user_cart.items.filter(product=guest_item.product).first()
        if existing:
            existing.quantity += guest_item.quantity
            existing.unit_price = guest_item.product.price
            existing.save(update_fields=["quantity", "unit_price", "updated_at"])
        else:
            CartItem.objects.create(
                cart=user_cart,
                product=guest_item.product,
                quantity=guest_item.quantity,
                unit_price=guest_item.product.price,
            )
    guest_cart.items.all().delete()


def _get_or_create_cart(request) -> Cart:
    if request.user.is_authenticated:
        user_cart, _ = Cart.objects.get_or_create(
            user=request.user, checked_out_at__isnull=True
        )
        if user_cart.total_items() == 0:
            token = request.headers.get(CART_TOKEN_HEADER) or request.query_params.get(
                CART_TOKEN_QUERY_PARAM
            )
            if token:
                try:
                    guest_cart = Cart.objects.get(
                        guest_token=token, checked_out_at__isnull=True
                    )
                    if guest_cart.total_items() > 0:
                        _merge_guest_cart_into_user_cart(user_cart, guest_cart)
                except Cart.DoesNotExist:
                    pass
        return user_cart

    token = request.headers.get(CART_TOKEN_HEADER) or request.query_params.get(
        CART_TOKEN_QUERY_PARAM
    )
    if token:
        try:
            return Cart.objects.get(guest_token=token, checked_out_at__isnull=True)
        except Cart.DoesNotExist:
            pass
    return Cart.objects.create()


def _profile_response(user, request=None):
    data = {
        "id": user.id,
        "username": user.get_username(),
        "email": user.email or "",
        "first_name": user.first_name or "",
        "last_name": user.last_name or "",
    }
    try:
        profile = user.shop_profile
        if profile.avatar:
            url = profile.avatar.url
            data["avatar_url"] = request.build_absolute_uri(url) if request else url
        else:
            data["avatar_url"] = None
    except UserProfile.DoesNotExist:
        data["avatar_url"] = None
    return data


@api_view(["POST"])
@permission_classes([AllowAny])
def register(request):
    s = RegisterSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    try:
        user = s.save()
    except IntegrityError:
        return Response(
            {"detail": "A user with this username or email already exists."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    rec = EmailVerificationCode.create_for_email(user.email)
    try:
        send_otp_email(user.email, rec.code)
    except Exception:
        rec.delete()
        user.delete()
        return Response(
            {"detail": "Failed to send verification email. Check email configuration."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return Response({
        "message": "Check your email for the verification code (OTP).",
        "email": user.email,
    }, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([AllowAny])
def verify_email(request):
    s = VerifyEmailSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    email = s.validated_data["email"].strip().lower()
    otp = s.validated_data["otp"].strip()
    try:
        rec = EmailVerificationCode.objects.get(email__iexact=email, code=otp)
    except EmailVerificationCode.DoesNotExist:
        return Response({"detail": "Invalid or expired code."}, status=status.HTTP_400_BAD_REQUEST)
    delta = timezone.now() - rec.created_at
    if delta.total_seconds() > get_otp_expire_minutes() * 60:
        rec.delete()
        return Response({"detail": "Code expired. Please request a new one."}, status=status.HTTP_400_BAD_REQUEST)
    user = User.objects.filter(email__iexact=email).first()
    if not user:
        rec.delete()
        return Response({"detail": "User not found."}, status=status.HTTP_400_BAD_REQUEST)
    user.is_active = True
    user.save(update_fields=["is_active"])
    rec.delete()
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
    if not user.is_active:
        return Response(
            {"detail": "Account not verified. Please verify your email first."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    token, _ = Token.objects.get_or_create(user=user)
    return Response({"token": token.key})


@api_view(["GET"])
@permission_classes([AllowAny])
def products_list(request):
    qs = Product.objects.filter(is_active=True).order_by("id")
    return Response(ProductSerializer(qs, many=True, context={"request": request}).data)


@api_view(["GET"])
@permission_classes([AllowAny])
def product_detail(request, product_id: int):
    product = Product.objects.filter(is_active=True, id=product_id).first()
    if not product:
        return Response({"detail": "Product not found."}, status=status.HTTP_404_NOT_FOUND)
    return Response(ProductSerializer(product, context={"request": request}).data)


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


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def order_list(request):
    qs = (
        Order.objects.filter(user=request.user)
        .select_related("coupon")
        .prefetch_related("items__product")
        .order_by("-created_at")
    )
    return Response(
        OrderSerializer(qs, many=True, context={"request": request}).data
    )


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
            min_order_amount=get_min_order_amount(),
        )
    except ValueError as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    try:
        send_order_confirmation_email(order)
    except Exception:
        pass

    return Response(OrderSerializer(order, context={"request": request}).data, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    return Response(_profile_response(request.user, request))


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def profile_update(request):
    s = ProfileUpdateSerializer(data=request.data, partial=True)
    s.is_valid(raise_exception=True)
    user = request.user
    if "first_name" in s.validated_data:
        user.first_name = (s.validated_data["first_name"] or "").strip()
    if "last_name" in s.validated_data:
        user.last_name = (s.validated_data["last_name"] or "").strip()
    new_email = (s.validated_data.get("email") or "").strip().lower()
    if new_email and new_email != (user.email or "").strip().lower():
        if User.objects.filter(email__iexact=new_email).exclude(pk=user.pk).exists():
            return Response(
                {"detail": "A user with this email already exists."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        EmailChangeRequest.objects.filter(user=user).delete()
        code = "".join(random.choices(string.digits, k=6))
        req = EmailChangeRequest.objects.create(user=user, new_email=new_email, code=code)
        try:
            send_email_change_otp(req.new_email, req.code)
        except Exception:
            req.delete()
            return Response(
                {"detail": "Failed to send verification email. Try again later."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        user.save(update_fields=["first_name", "last_name"])
        return Response({
            **_profile_response(user, request),
            "pending_email": new_email,
            "message": "Check your new email for the verification code.",
        })
    user.save(update_fields=["first_name", "last_name"])
    return Response(_profile_response(user, request))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def verify_email_change(request):
    s = VerifyEmailChangeSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    new_email = s.validated_data["new_email"].strip().lower()
    otp = s.validated_data["otp"].strip()
    user = request.user
    try:
        req = EmailChangeRequest.objects.get(user=user, new_email__iexact=new_email, code=otp)
    except EmailChangeRequest.DoesNotExist:
        return Response(
            {"detail": "Invalid or expired code."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    delta = timezone.now() - req.created_at
    if delta.total_seconds() > get_otp_expire_minutes() * 60:
        req.delete()
        return Response(
            {"detail": "Code expired. Request a new email change."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    user.email = new_email
    user.save(update_fields=["email"])
    req.delete()
    return Response(_profile_response(user, request))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def profile_avatar_upload(request):
    avatar = request.FILES.get("avatar")
    if not avatar:
        return Response(
            {"detail": "No avatar file provided."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not avatar.content_type.startswith("image/"):
        return Response(
            {"detail": "File must be an image."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    profile.avatar = avatar
    profile.save(update_fields=["avatar"])
    return Response(_profile_response(request.user, request))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout_view(request):
    Token.objects.filter(user=request.user).delete()
    return Response(status=status.HTTP_204_NO_CONTENT)

