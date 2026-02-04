from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("", views.dashboard_home, name="home"),
    # Products
    path("products/", views.product_list, name="product_list"),
    path("products/create/", views.product_create, name="product_create"),
    path("products/<int:pk>/edit/", views.product_edit, name="product_edit"),
    path("products/<int:pk>/images/", views.product_images, name="product_images"),
    path("products/<int:pk>/images/upload/", views.product_images_upload, name="product_images_upload"),
    path("products/<int:pk>/images/<int:image_pk>/set-cover/", views.product_image_set_cover, name="product_image_set_cover"),
    path("products/<int:pk>/images/<int:image_pk>/delete/", views.product_image_delete, name="product_image_delete"),
    path("products/<int:pk>/delete/", views.product_delete, name="product_delete"),
    # Coupons
    path("coupons/", views.coupon_list, name="coupon_list"),
    path("coupons/create/", views.coupon_create, name="coupon_create"),
    path("coupons/<int:pk>/edit/", views.coupon_edit, name="coupon_edit"),
    path("coupons/<int:pk>/toggle/", views.coupon_toggle_enabled, name="coupon_toggle"),
    # Orders
    path("orders/", views.order_list, name="order_list"),
    path("orders/<int:pk>/detail/", views.order_detail, name="order_detail"),
    path("orders/<int:pk>/status/", views.order_update_status, name="order_update_status"),
]

