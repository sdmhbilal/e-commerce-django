# Email configuration (OTP & order confirmation)

The app sends email for:

1. **Signup OTP** — verification code when a user registers.
2. **Order confirmation** — after an order is placed (to user or guest email).

## What you need to provide

Set these in your `.env` (or environment). Without them, Django uses the **console backend**: emails are printed in the terminal (no real sending). That is fine for local development.

For **real email** (production or testing with real inboxes), configure SMTP.

### Option 1: Console (development, no real email)

No config. Emails are printed in the terminal where you run `python manage.py runserver`. OTP and order text will appear there.

### Option 2: Gmail

1. Use an **App Password** (not your normal password):  
   [Google App Passwords](https://support.google.com/accounts/answer/185833)

2. In `.env`:

```env
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=true
EMAIL_HOST_USER=your@gmail.com
EMAIL_HOST_PASSWORD=your-16-char-app-password
DEFAULT_FROM_EMAIL=your@gmail.com
```

### Option 3: Any SMTP server

```env
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.your-provider.com
EMAIL_PORT=587
EMAIL_USE_TLS=true
EMAIL_HOST_USER=your-username
EMAIL_HOST_PASSWORD=your-password
DEFAULT_FROM_EMAIL=noreply@yourdomain.com
```

### Optional

- **OTP expiry (minutes):** `OTP_EXPIRE_MINUTES=15` (default 15).

## Summary

| Purpose              | When it’s sent        | Recipient        |
|----------------------|------------------------|------------------|
| Signup OTP           | After registration     | User’s email     |
| Order confirmation   | After order is placed  | User or guest   |

If `EMAIL_BACKEND` is not set (or console), nothing is sent; OTP and order text are only in the server logs/console.
