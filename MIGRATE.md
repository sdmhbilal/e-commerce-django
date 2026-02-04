# Fix: "You have 2 unapplied migration(s)"

Run migrations from the **e-commerce-backend** folder:

```bash
cd e-commerce-backend
.venv/bin/python manage.py migrate
```

If you use a different virtualenv, activate it first then run:

```bash
cd e-commerce-backend
source .venv/bin/activate   # or: source venv/bin/activate
python manage.py migrate
```

Then start the server again:

```bash
python manage.py runserver 127.0.0.1:8000
```

The warning will disappear once all migrations are applied.
