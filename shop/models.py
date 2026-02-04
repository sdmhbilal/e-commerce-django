from __future__ import annotations

import random
import string
import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.utils import timezone


def _generate_otp(length=6):
    return "".join(random.choices(string.digits, k=length))


class EmailVerificationCode(models.Model):
    """OTP for email verification on signup."""
    email = models.EmailField()
    code = models.CharField(max_length=10)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["email"])]
        ordering = ["-created_at"]

    @staticmethod
    def create_for_email(email):
        code = _generate_otp(6)
        EmailVerificationCode.objects.filter(email__iexact=email).delete()
        return EmailVerificationCode.objects.create(email=email, code=code)


class EmailChangeRequest(models.Model):
    """OTP for verifying a user's new email before updating."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="email_change_requests"
    )
    new_email = models.EmailField()
    code = models.CharField(max_length=10)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["user", "new_email"])]
        ordering = ["-created_at"]


class UserProfile(models.Model):
    """Extended profile for user (e.g. avatar)."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="shop_profile"
    )
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)

    class Meta:
        db_table = "shop_userprofile"


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Product(TimestampedModel):
    name = models.CharField(max_length=200)
    price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    short_description = models.TextField(blank=True)
    stock_quantity = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    image = models.ImageField(upload_to="products/", blank=True, null=True)

    def __str__(self) -> str:
        return self.name

    @property
    def in_stock(self) -> bool:
        return self.stock_quantity > 0

    def get_cover_image(self):
        """Cover = first ProductImage with is_cover=True, else first by order, else legacy Product.image."""
        cover = self.images.filter(is_cover=True).first()
        if cover:
            return cover.image
        first = self.images.order_by("order", "id").first()
        if first:
            return first.image
        return self.image


class ProductImage(models.Model):
    """Multiple images per product; one can be the cover."""
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="images"
    )
    image = models.ImageField(upload_to="products/")
    is_cover = models.BooleanField(default=False)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]
        db_table = "shop_productimage"

    def save(self, *args, **kwargs):
        if self.is_cover:
            self.product.images.exclude(pk=self.pk).update(is_cover=False)
        super().save(*args, **kwargs)


class Coupon(TimestampedModel):
    class DiscountType(models.TextChoices):
        PERCENTAGE = "percentage", "Percentage"
        FLAT = "flat", "Flat"

    code = models.CharField(max_length=50, unique=True)
    discount_type = models.CharField(
        max_length=20, choices=DiscountType.choices, default=DiscountType.FLAT
    )
    discount_value = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    minimum_cart_value = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)]
    )
    usage_limit = models.PositiveIntegerField(blank=True, null=True)
    times_used = models.PositiveIntegerField(default=0)
    is_enabled = models.BooleanField(default=True)
    applicable_products = models.ManyToManyField(Product, blank=True, related_name="coupons")

    def __str__(self) -> str:
        return self.code

    def is_active_now(self) -> bool:
        if not self.is_enabled:
            return False
        now = timezone.now()
        if now < self.start_at or now > self.end_at:
            return False
        if self.usage_limit is not None and self.times_used >= self.usage_limit:
            return False
        return True

    def is_applicable_to_cart(self, cart: "Cart") -> tuple[bool, str]:
        if not self.is_active_now():
            return False, "Coupon is expired or disabled."

        subtotal = cart.subtotal()
        if subtotal < self.minimum_cart_value:
            return False, "Minimum cart value not met for this coupon."

        # If applicable_products is empty => applies to all products.
        restricted = self.applicable_products.exists()
        if restricted:
            product_ids = set(cart.items.values_list("product_id", flat=True))
            allowed_ids = set(self.applicable_products.values_list("id", flat=True))
            if product_ids.isdisjoint(allowed_ids):
                return False, "Coupon is not applicable to items in your cart."

        return True, ""

    def compute_discount(self, cart: "Cart") -> Decimal:
        subtotal = cart.subtotal()

        if self.discount_type == self.DiscountType.PERCENTAGE:
            # discount_value = percent (e.g. 10 => 10%)
            pct = (self.discount_value / Decimal("100")).quantize(Decimal("0.0001"))
            return (subtotal * pct).quantize(Decimal("0.01"))

        return min(self.discount_value, subtotal).quantize(Decimal("0.01"))


class Cart(TimestampedModel):
    """
    Supports both:
    - Authenticated carts (user is set)
    - Guest carts (guest_token is set)
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, blank=True, null=True, related_name="carts"
    )
    guest_token = models.UUIDField(default=uuid.uuid4, unique=True, blank=True, null=True)
    checked_out_at = models.DateTimeField(blank=True, null=True)

    def __str__(self) -> str:
        return f"Cart {self.id}"

    def subtotal(self) -> Decimal:
        total = Decimal("0.00")
        for item in self.items.select_related("product").all():
            total += (item.unit_price * item.quantity)
        return total.quantize(Decimal("0.01"))

    def total_items(self) -> int:
        return int(self.items.aggregate(models.Sum("quantity")).get("quantity__sum") or 0)


class CartItem(TimestampedModel):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="cart_items")
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])

    class Meta:
        unique_together = [("cart", "product")]

    def __str__(self) -> str:
        return f"{self.product} x {self.quantity}"


class Order(TimestampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SHIPPED = "shipped", "Shipped"
        CANCELLED = "cancelled", "Cancelled"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True, related_name="orders"
    )
    guest_full_name = models.CharField(max_length=200, blank=True)
    guest_email = models.EmailField(blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    coupon = models.ForeignKey(Coupon, on_delete=models.SET_NULL, blank=True, null=True, related_name="orders")
    subtotal_amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])

    def __str__(self) -> str:
        return f"Order {self.id}"


class OrderItem(TimestampedModel):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="order_items")
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    line_total = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])

    def __str__(self) -> str:
        return f"{self.product} x {self.quantity}"


@transaction.atomic
def create_order_from_cart(
    *,
    cart: Cart,
    user=None,
    guest_full_name: str = "",
    guest_email: str = "",
    coupon: Coupon | None = None,
    min_order_amount: Decimal = Decimal("0.00"),
) -> Order:
    if cart.items.select_related("product").count() == 0:
        raise ValueError("Cart is empty.")

    subtotal = cart.subtotal()
    if subtotal < min_order_amount:
        raise ValueError("Minimum order amount not met.")

    discount = Decimal("0.00")
    if coupon is not None:
        ok, msg = coupon.is_applicable_to_cart(cart)
        if not ok:
            raise ValueError(msg)
        discount = coupon.compute_discount(cart)

    total = (subtotal - discount).quantize(Decimal("0.01"))
    if total < 0:
        total = Decimal("0.00")

    # Stock validation and decrement
    for item in cart.items.select_related("product").select_for_update():
        if item.quantity > item.product.stock_quantity:
            raise ValueError(f"Insufficient stock for {item.product.name}.")

    for item in cart.items.select_related("product").select_for_update():
        item.product.stock_quantity -= item.quantity
        item.product.save(update_fields=["stock_quantity"])

    order = Order.objects.create(
        user=user,
        guest_full_name=guest_full_name,
        guest_email=guest_email,
        coupon=coupon,
        subtotal_amount=subtotal,
        discount_amount=discount,
        total_amount=total,
    )

    for item in cart.items.select_related("product").all():
        OrderItem.objects.create(
            order=order,
            product=item.product,
            quantity=item.quantity,
            unit_price=item.unit_price,
            line_total=(item.unit_price * item.quantity).quantize(Decimal("0.01")),
        )

    if coupon is not None:
        Coupon.objects.filter(pk=coupon.pk).update(times_used=models.F("times_used") + 1)

    cart.checked_out_at = timezone.now()
    cart.save(update_fields=["checked_out_at"])
    cart.items.all().delete()

    return order
