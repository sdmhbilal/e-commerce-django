from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.mail import send_mail

from shop.constants import (
    DEFAULT_FROM_EMAIL,
    DEFAULT_MIN_ORDER_AMOUNT,
    DEFAULT_OTP_EXPIRE_MINUTES,
    SETTING_DEFAULT_FROM_EMAIL,
    SETTING_MIN_ORDER_AMOUNT,
    SETTING_OTP_EXPIRE_MINUTES,
)
from shop.models import Order


def get_otp_expire_minutes() -> int:
    return getattr(settings, SETTING_OTP_EXPIRE_MINUTES, DEFAULT_OTP_EXPIRE_MINUTES)


def get_min_order_amount() -> Decimal:
    raw = getattr(settings, SETTING_MIN_ORDER_AMOUNT, None) or DEFAULT_MIN_ORDER_AMOUNT
    try:
        return Decimal(str(raw)).quantize(Decimal("0.01"))
    except Exception:
        return Decimal("0.00")


def get_from_email() -> str:
    return getattr(settings, SETTING_DEFAULT_FROM_EMAIL, DEFAULT_FROM_EMAIL)


def send_otp_email(email: str, otp: str) -> None:
    minutes = get_otp_expire_minutes()
    subject = "Your verification code"
    message = (
        f"Your OTP for account verification is: {otp}\n\n"
        f"It is valid for {minutes} minutes."
    )
    send_mail(subject, message, get_from_email(), [email], fail_silently=False)


def send_email_change_otp(new_email: str, otp: str) -> None:
    minutes = get_otp_expire_minutes()
    subject = "Verify your new email address"
    message = (
        f"Your code to confirm your new email address is: {otp}\n\n"
        f"It is valid for {minutes} minutes."
    )
    send_mail(subject, message, get_from_email(), [new_email], fail_silently=False)


def send_order_confirmation_email(order: Order) -> None:
    to_email = order.user.email if order.user else order.guest_email
    if not to_email:
        return
    subject = f"Order #{order.id} confirmed"
    lines = [
        f"Thank you for your order #{order.id}.",
        f"Status: {order.status}",
        f"Subtotal: {order.subtotal_amount}",
        f"Discount: {order.discount_amount}",
        f"Total: {order.total_amount}",
    ]
    for item in order.items.select_related("product").all():
        lines.append(f"  - {item.product.name} x {item.quantity}: {item.line_total}")
    message = "\n".join(lines)
    send_mail(subject, message, get_from_email(), [to_email], fail_silently=True)


def send_order_status_change_email(order: Order) -> None:
    to_email = order.user.email if order.user else order.guest_email
    if not to_email or not to_email.strip():
        return
    status_display = dict(Order.Status.choices).get(order.status, order.status)
    subject = f"Order #{order.id} – status updated to {status_display}"
    lines = [
        f"Your order #{order.id} has been updated.",
        f"New status: {status_display}",
        f"Total: PKR {order.total_amount}",
    ]
    message = "\n".join(lines)
    send_mail(subject, message, get_from_email(), [to_email.strip()], fail_silently=True)
