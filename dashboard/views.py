from __future__ import annotations

from django import forms
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from shop.services import send_order_status_change_email
from shop.models import Coupon, Order, Product


def staff_required(view_func):
    return login_required(user_passes_test(lambda u: u.is_staff, login_url="dashboard:login")(view_func))


class LoginForm(forms.Form):
    username = forms.CharField()
    password = forms.CharField(widget=forms.PasswordInput)


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ["name", "price", "short_description", "stock_quantity", "is_active", "image"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "e.g. Blue T-Shirt"}),
            "price": forms.NumberInput(attrs={"placeholder": "0.00", "min": "0", "step": "0.01"}),
            "short_description": forms.Textarea(attrs={"placeholder": "Brief product description", "rows": 3}),
            "stock_quantity": forms.NumberInput(attrs={"placeholder": "0", "min": "0"}),
            "image": forms.FileInput(attrs={"accept": "image/*"}),
        }
        help_texts = {
            "price": "Amount in dollars ($). Minimum: 0. No negative values.",
            "stock_quantity": "Number of units in stock. Minimum: 0.",
        }
        labels = {
            "price": "Price ($)",
        }

    def clean_price(self):
        value = self.cleaned_data.get("price")
        if value is not None and value < 0:
            raise forms.ValidationError("Price cannot be negative. Minimum is 0.")
        return value

    def clean_stock_quantity(self):
        value = self.cleaned_data.get("stock_quantity")
        if value is not None and value < 0:
            raise forms.ValidationError("Stock cannot be negative. Minimum is 0.")
        return value


class CouponForm(forms.ModelForm):
    class Meta:
        model = Coupon
        fields = [
            "code",
            "discount_type",
            "discount_value",
            "start_at",
            "end_at",
            "minimum_cart_value",
            "usage_limit",
            "applicable_products",
            "is_enabled",
        ]
        widgets = {
            "code": forms.TextInput(attrs={"placeholder": "e.g. SAVE10"}),
            "discount_type": forms.RadioSelect(choices=[]),
            "discount_value": forms.NumberInput(
                attrs={"placeholder": "0.00", "min": "0", "step": "0.01"}
            ),
            "start_at": forms.DateTimeInput(
                attrs={"type": "datetime-local", "class": "dash-datetime"},
                format="%Y-%m-%dT%H:%M",
            ),
            "end_at": forms.DateTimeInput(
                attrs={"type": "datetime-local", "class": "dash-datetime"},
                format="%Y-%m-%dT%H:%M",
            ),
            "minimum_cart_value": forms.NumberInput(
                attrs={"placeholder": "0.00", "min": "0", "step": "0.01"}
            ),
            "usage_limit": forms.NumberInput(
                attrs={"placeholder": "Leave empty for unlimited", "min": "0"}
            ),
            "applicable_products": forms.SelectMultiple(
                attrs={"size": "8", "class": "dash-multi-select"}
            ),
        }
        help_texts = {
            "discount_value": "Flat: amount in $. Percentage: 0–100 (e.g. 10 = 10%). Minimum: 0.",
            "start_at": "Start of validity (local date & time).",
            "end_at": "End of validity (local date & time). Must be after start.",
            "applicable_products": "Leave empty to apply to all products. Hold Ctrl/Cmd to select multiple.",
        }
        labels = {
            "discount_value": "Discount value ($ or %)",
            "minimum_cart_value": "Minimum cart value ($)",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["discount_type"].widget.choices = Coupon.DiscountType.choices
        if not self.instance.pk:
            self.fields["discount_type"].initial = Coupon.DiscountType.FLAT
        self.fields["applicable_products"].queryset = Product.objects.filter(
            is_active=True
        ).order_by("name")
        self.fields["start_at"].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d"]
        self.fields["end_at"].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d"]

    def clean_discount_value(self):
        value = self.cleaned_data.get("discount_value")
        if value is not None and value < 0:
            raise forms.ValidationError("Discount value cannot be negative. Minimum is 0.")
        discount_type = self.cleaned_data.get("discount_type") or Coupon.DiscountType.FLAT
        if discount_type == Coupon.DiscountType.PERCENTAGE and value is not None and value > 100:
            raise forms.ValidationError("Percentage discount cannot exceed 100.")
        return value

    def clean_end_at(self):
        start = self.cleaned_data.get("start_at")
        end = self.cleaned_data.get("end_at")
        if start and end and end <= start:
            raise forms.ValidationError("End date must be after start date.")
        return end


def login_view(request):
    if request.user.is_authenticated and request.user.is_staff:
        return redirect("dashboard:home")

    form = LoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = authenticate(
            request, username=form.cleaned_data["username"], password=form.cleaned_data["password"]
        )
        if user is not None and user.is_staff:
            login(request, user)
            return redirect("dashboard:home")
        messages.error(request, "Invalid credentials or not an admin user.")
    return render(request, "dashboard/login.html", {"form": form})


def logout_view(request):
    logout(request)
    return redirect("dashboard:login")


@staff_required
def dashboard_home(request):
    orders = Order.objects.order_by("-created_at")[:5]
    products_count = Product.objects.count()
    orders_count = Order.objects.count()
    coupons_count = Coupon.objects.count()
    return render(
        request,
        "dashboard/home.html",
        {
            "orders": orders,
            "products_count": products_count,
            "orders_count": orders_count,
            "coupons_count": coupons_count,
        },
    )


@staff_required
def product_list(request):
    products = Product.objects.order_by("name")
    return render(request, "dashboard/product_list.html", {"products": products})


@staff_required
def product_create(request):
    form = ProductForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Product created.")
        return redirect("dashboard:product_list")
    return render(request, "dashboard/product_form.html", {"form": form, "title": "Create product"})


@staff_required
def product_edit(request, pk: int):
    product = get_object_or_404(Product, pk=pk)
    form = ProductForm(request.POST or None, request.FILES or None, instance=product)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Product updated.")
        return redirect("dashboard:product_list")
    return render(request, "dashboard/product_form.html", {"form": form, "title": "Edit product", "product": product})


@staff_required
def product_delete(request, pk: int):
    product = get_object_or_404(Product, pk=pk)
    if request.method == "POST":
        try:
            product.delete()
            messages.success(request, "Product deleted.")
        except ProtectedError:
            messages.error(
                request,
                "Cannot delete: this product is in orders or carts. Remove or complete those first.",
            )
        return redirect("dashboard:product_list")
    return render(request, "dashboard/product_confirm_delete.html", {"product": product})


@staff_required
def coupon_list(request):
    coupons = Coupon.objects.order_by("-created_at")
    return render(request, "dashboard/coupon_list.html", {"coupons": coupons, "now": timezone.now()})


@staff_required
def coupon_create(request):
    form = CouponForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Coupon created.")
        return redirect("dashboard:coupon_list")
    return render(request, "dashboard/coupon_form.html", {"form": form, "title": "Create coupon"})


@staff_required
def coupon_edit(request, pk: int):
    coupon = get_object_or_404(Coupon, pk=pk)
    form = CouponForm(request.POST or None, instance=coupon)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Coupon updated.")
        return redirect("dashboard:coupon_list")
    return render(request, "dashboard/coupon_form.html", {"form": form, "title": "Edit coupon"})


@staff_required
def coupon_toggle_enabled(request, pk: int):
    coupon = get_object_or_404(Coupon, pk=pk)
    coupon.is_enabled = not coupon.is_enabled
    coupon.save(update_fields=["is_enabled"])
    return redirect("dashboard:coupon_list")


@staff_required
def order_list(request):
    status_filter = request.GET.get("status") or ""
    qs = Order.objects.select_related("coupon").order_by("-created_at")
    if status_filter:
        qs = qs.filter(status=status_filter)
    return render(
        request,
        "dashboard/order_list.html",
        {"orders": qs, "status_filter": status_filter, "order_status_choices": Order.Status.choices},
    )


@staff_required
def order_detail(request, pk: int):
    order = get_object_or_404(Order.objects.select_related("coupon"), pk=pk)
    return render(request, "dashboard/order_detail.html", {"order": order})


@staff_required
def order_update_status(request, pk: int):
    order = get_object_or_404(Order, pk=pk)
    if request.method == "POST":
        new_status = request.POST.get("status")
        if new_status in dict(Order.Status.choices):
            order.status = new_status
            order.save(update_fields=["status"])
            send_order_status_change_email(order)
            messages.success(request, "Order status updated and customer notified by email.")
        return redirect("dashboard:order_detail", pk=order.pk)
    return render(request, "dashboard/order_status_form.html", {"order": order})

