from django.urls import path

from shop import api

urlpatterns = [
    # Auth
    path("auth/register/", api.register),
    path("auth/login/", api.login),
    path("auth/me/", api.me),
    path("auth/profile/", api.profile_update),
    path("auth/profile/avatar/", api.profile_avatar_upload),
    path("auth/verify-email/", api.verify_email),
    path("auth/verify-email-change/", api.verify_email_change),
    path("auth/logout/", api.logout_view),
    # Products
    path("products/", api.products_list),
    path("products/<int:product_id>/", api.product_detail),
    # Cart
    path("cart/", api.cart_detail),
    path("cart/items/", api.cart_item_add),
    path("cart/items/<int:item_id>/", api.cart_item_update),
    path("cart/items/<int:item_id>/delete/", api.cart_item_delete),
    # Coupons
    path("coupons/validate/", api.coupon_validate),
    # Orders
    path("orders/", api.order_create),
    path("my-orders/", api.order_list),
]

