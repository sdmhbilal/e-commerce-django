from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from shop.models import Cart, CartItem, Coupon, Order, OrderItem, Product, ProductImage

User = get_user_model()


class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    first_name = serializers.CharField(max_length=150, required=True, allow_blank=False)
    last_name = serializers.CharField(max_length=150, required=True, allow_blank=False)
    password = serializers.CharField(write_only=True, min_length=8)

    def validate_username(self, value: str) -> str:
        if User.objects.filter(username__iexact=value.strip()).exists():
            raise serializers.ValidationError("A user with this username already exists.")
        return value.strip()

    def validate_email(self, value: str) -> str:
        if User.objects.filter(email__iexact=value.strip().lower()).exists():
            raise serializers.ValidationError("A user with this email is already registered.")
        return value.strip().lower()

    def validate_password(self, value: str) -> str:
        validate_password(value)
        return value

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data["username"],
            email=validated_data["email"],
            password=validated_data["password"],
            first_name=validated_data.get("first_name", ""),
            last_name=validated_data.get("last_name", ""),
            is_active=False,
        )
        return user


class VerifyEmailSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=10)


class VerifyEmailChangeSerializer(serializers.Serializer):
    new_email = serializers.EmailField()
    otp = serializers.CharField(max_length=10)


class ProfileUpdateSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)


def _build_image_url(request, image_field):
    if not image_field:
        return None
    url = image_field.url
    return request.build_absolute_uri(url) if request else url


class ProductImageSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    image_url = serializers.SerializerMethodField()
    is_cover = serializers.BooleanField(read_only=True)
    order = serializers.IntegerField(read_only=True)

    def get_image_url(self, obj):
        request = self.context.get("request")
        return _build_image_url(request, obj.image if hasattr(obj, "image") else None)


class ProductSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()
    in_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "price",
            "short_description",
            "stock_quantity",
            "in_stock",
            "image_url",
            "images",
        ]

    def get_image_url(self, obj: Product):
        """Cover image URL: from ProductImage (cover or first) or legacy Product.image."""
        request = self.context.get("request")
        cover_image = obj.get_cover_image()
        return _build_image_url(request, cover_image)

    def get_images(self, obj: Product):
        """All product images (cover + others) for buyer to view."""
        qs = obj.images.all()
        if not qs.exists() and obj.image:
            return [
                {
                    "id": 0,
                    "image_url": _build_image_url(self.context.get("request"), obj.image),
                    "is_cover": True,
                    "order": 0,
                }
            ]
        return ProductImageSerializer(qs, many=True, context=self.context).data


class CartItemSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.filter(is_active=True), source="product", write_only=True
    )

    class Meta:
        model = CartItem
        fields = ["id", "product", "product_id", "quantity", "unit_price", "created_at", "updated_at"]
        read_only_fields = ["unit_price", "created_at", "updated_at"]


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    subtotal = serializers.SerializerMethodField()
    total_items = serializers.SerializerMethodField()
    cart_token = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = ["id", "cart_token", "items", "subtotal", "total_items"]

    def get_subtotal(self, obj: Cart) -> Decimal:
        return obj.subtotal()

    def get_total_items(self, obj: Cart) -> int:
        return obj.total_items()

    def get_cart_token(self, obj: Cart):
        return str(obj.guest_token) if obj.guest_token else None


class CouponValidateSerializer(serializers.Serializer):
    code = serializers.CharField()


class CouponValidationResultSerializer(serializers.Serializer):
    code = serializers.CharField()
    discount_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    subtotal_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_amount = serializers.DecimalField(max_digits=12, decimal_places=2)


class OrderCreateSerializer(serializers.Serializer):
    coupon_code = serializers.CharField(required=False, allow_blank=True)
    guest_full_name = serializers.CharField(required=False, allow_blank=True)
    guest_email = serializers.EmailField(required=False, allow_blank=True)

    def validate(self, attrs):
        request = self.context["request"]
        if not request.user.is_authenticated:
            if not attrs.get("guest_full_name") or not attrs.get("guest_email"):
                raise serializers.ValidationError("Guest checkout requires full name and email.")
        return attrs


class OrderItemSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)

    class Meta:
        model = OrderItem
        fields = ["id", "product", "quantity", "unit_price", "line_total"]


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    coupon_code = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id",
            "status",
            "guest_full_name",
            "guest_email",
            "coupon_code",
            "subtotal_amount",
            "discount_amount",
            "total_amount",
            "items",
            "created_at",
        ]

    def get_coupon_code(self, obj: Order):
        return obj.coupon.code if obj.coupon else None

