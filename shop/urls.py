from django.urls import path

from shop import api

urlpatterns = [
    # Auth
    path("auth/register/", api.register),
    path("auth/login/", api.login),
    path("auth/me/", api.me),
    # Products
    path("products/", api.products_list),
    # Cart
    path("cart/", api.cart_detail),
    path("cart/items/", api.cart_item_add),
    path("cart/items/<int:item_id>/", api.cart_item_update),
    path("cart/items/<int:item_id>/delete/", api.cart_item_delete),
    # Coupons
    path("coupons/validate/", api.coupon_validate),
    # Orders
    path("orders/", api.order_create),
]

