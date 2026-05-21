# Contractly — Backend

FastAPI service powering the Contractly mobile app.

**Frontend repo:** [contractly-frontend](https://github.com/hassaankhalid225/contractly-frontend)

## Quick Start

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows PowerShell
# source .venv/bin/activate       # macOS / Linux
pip install -r requirements.txt
copy .env.example .env            # then edit .env
uvicorn main:app --reload
```

Open the auto-generated docs at <http://localhost:8000/docs>.

## Environment

All configuration lives in `.env`. See `.env.example` for the full list.

The most important variables are:

- `MONGODB_URL` — connection string (Atlas or local)
- `SECRET_KEY` — JWT signing secret (at least 16 chars)
- `GOOGLE_CLIENT_ID` — required to verify Google ID tokens
- `ANTHROPIC_API_KEY` — required for AI generation/analysis (otherwise local fallbacks are used)
- `CLOUDINARY_*` — required to upload PDFs / signatures
- `TWILIO_*` — optional, for production SMS OTP delivery (development logs OTPs to the console)

## Test Phone Numbers

These two numbers always succeed with OTP `123456`:

- `+923001234567`
- `+923009876543`

## API Surface (v1)

```
POST   /api/v1/auth/google
POST   /api/v1/auth/phone/send-otp
POST   /api/v1/auth/phone/verify
POST   /api/v1/auth/refresh
POST   /api/v1/auth/logout

GET    /api/v1/users/me
PATCH  /api/v1/users/me
DELETE /api/v1/users/me

GET    /api/v1/contracts
POST   /api/v1/contracts
GET    /api/v1/contracts/{id}
PATCH  /api/v1/contracts/{id}
DELETE /api/v1/contracts/{id}
POST   /api/v1/contracts/{id}/upload-pdf
POST   /api/v1/contracts/{id}/sign
GET    /api/v1/contracts/stats/summary

GET    /api/v1/payments
POST   /api/v1/payments
PATCH  /api/v1/payments/{id}
DELETE /api/v1/payments/{id}
GET    /api/v1/payments/summary

POST   /api/v1/ai/generate-contract
POST   /api/v1/ai/analyze-contract
POST   /api/v1/ai/suggest-template

GET    /api/v1/notifications
```

## Response Envelope

Every endpoint returns the same shape:

```json
{ "success": true, "data": { ... }, "message": "..." }
```

On error:

```json
{ "success": false, "error": { "code": "...", "message": "...", "details": null } }
```
