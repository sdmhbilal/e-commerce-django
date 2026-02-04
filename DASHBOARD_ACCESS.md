# E‑Commerce Admin Dashboard — How to Access

The assignment asks for a **custom admin dashboard** built with **Django + Jinja** (not Django’s built‑in admin).  
That dashboard is here:

---

## Use the dashboard, not Django admin

| Purpose | URL | Use this? |
|--------|-----|------------|
| **E‑commerce admin (products, orders, coupons)** | **http://localhost:8000/dashboard/** | ✅ **Yes — this is the assignment’s admin** |
| Django built‑in admin | http://localhost:8000/admin/ | ❌ No — different from the assignment |

If you open `/admin/`, you get Django’s default admin.  
For **add products, see orders, add coupons**, use **`/dashboard/`**.

---

## 1. Log in to the dashboard

**URL:** http://localhost:8000/dashboard/login/

- **Username:** `admin`  
- **Password:** `admin123`  

(Change this in production. User was created with `createsuperuser`; superusers are staff and can access the dashboard.)

After login you are redirected to the dashboard home.

---

## 2. Dashboard pages (all under `/dashboard/`)

Base URL: **http://localhost:8000/dashboard/**

### Home
- **URL:** http://localhost:8000/dashboard/
- Summary: recent orders, product count, order count, coupon count.

### Products — list
- **URL:** http://localhost:8000/dashboard/products/
- View all products.

### Add product
- **URL:** http://localhost:8000/dashboard/products/create/
- Form: name, price, short description, stock quantity, active, image.

### Edit product
- **URL:** http://localhost:8000/dashboard/products/<id>/edit/  
  Example: http://localhost:8000/dashboard/products/1/edit/

### Delete product
- **URL:** http://localhost:8000/dashboard/products/<id>/delete/  
  (Confirm on the page.)

---

### Orders — list
- **URL:** http://localhost:8000/dashboard/orders/
- Filter by status: `?status=pending`, `?status=shipped`, `?status=cancelled`.

### Order detail (view order, see applied coupon)
- **URL:** http://localhost:8000/dashboard/orders/<id>/detail/  
  Example: http://localhost:8000/dashboard/orders/1/detail/

### Update order status (Pending / Shipped / Cancelled)
- **URL:** http://localhost:8000/dashboard/orders/<id>/status/  
  Example: http://localhost:8000/dashboard/orders/1/status/

---

### Coupons — list
- **URL:** http://localhost:8000/dashboard/coupons/
- View all coupons; enable/disable from here.

### Add coupon
- **URL:** http://localhost:8000/dashboard/coupons/create/
- Form: code, discount type (percentage/flat), discount value, start/end date, minimum cart value, usage limit, applicable products, enabled.

### Edit coupon
- **URL:** http://localhost:8000/dashboard/coupons/<id>/edit/  
  Example: http://localhost:8000/dashboard/coupons/1/edit/

### Enable / disable coupon (toggle)
- **URL:** http://localhost:8000/dashboard/coupons/<id>/toggle/  
  Example: http://localhost:8000/dashboard/coupons/1/toggle/

---

## 3. Quick link list

| What you want | Open this |
|---------------|-----------|
| Admin login | http://localhost:8000/dashboard/login/ |
| Dashboard home | http://localhost:8000/dashboard/ |
| Add product | http://localhost:8000/dashboard/products/create/ |
| List products | http://localhost:8000/dashboard/products/ |
| List orders | http://localhost:8000/dashboard/orders/ |
| Add coupon | http://localhost:8000/dashboard/coupons/create/ |
| List coupons | http://localhost:8000/dashboard/coupons/ |

---

## 4. Logout

**URL:** http://localhost:8000/dashboard/logout/

---

## 5. Run the backend first

```bash
cd e-commerce-backend
source .venv/bin/activate
USE_SQLITE=1 python manage.py runserver 127.0.0.1:8000
```

Then open **http://localhost:8000/dashboard/login/** and use **admin** / **admin123**.
