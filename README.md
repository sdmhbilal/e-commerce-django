# E-Commerce Backend

Django + DRF backend: REST API for products, cart, coupons, orders; staff dashboard for management.

**Tech stack:** Python, Django 6, Django REST Framework, PostgreSQL (or SQLite), Jinja2, Bootstrap 5.

## Setup

```bash
cd e-commerce-backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # edit .env: SECRET_KEY, DB, CORS, ALLOWED_HOSTS
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

- API: `http://localhost:8000/api/`
- Dashboard: `http://localhost:8000/dashboard/`

## API (basic)

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `auth/register/` | No | Register |
| POST | `auth/login/` | No | Login |
| GET | `auth/me/` | Token | Current user |
| GET | `products/` | No | List products |
| GET | `products/<id>/` | No | Product detail |
| GET | `cart/` | Token or X-Cart-Token | Get cart |
| POST | `cart/items/` | Token or X-Cart-Token | Add item |
| PUT/PATCH | `cart/items/<id>/` | Token or X-Cart-Token | Update quantity |
| DELETE | `cart/items/<id>/delete/` | Token or X-Cart-Token | Remove item |
| POST | `coupons/validate/` | No | Validate coupon |
| POST | `orders/` | Token or X-Cart-Token | Create order |
| GET | `my-orders/` | Token | List orders |

Auth header: `Authorization: Token <token>`. Guest cart: `X-Cart-Token: <uuid>`.
