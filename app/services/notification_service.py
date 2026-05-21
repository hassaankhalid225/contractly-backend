"""Server-side notification helpers.

The mobile app handles local push reminders. This module is a thin abstraction
that lets routers ask "what notifications should this user see?" and exists so
the surface area is ready when push delivery is added later.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from bson import ObjectId

from app.core.database import get_db
from app.models.contract import ContractStatus, derive_status


async def list_user_alerts(user_id: str) -> List[Dict[str, Any]]:
    """Return contract & payment alerts that are pending action for the user."""
    db = get_db()
    now = datetime.now(timezone.utc)
    alerts: List[Dict[str, Any]] = []

    contracts_cursor = db["contracts"].find({"user_id": ObjectId(user_id)})
    async for c in contracts_cursor:
        derived = derive_status(c)
        end_date = c.get("end_date")
        if derived == ContractStatus.EXPIRING_SOON and end_date:
            days_left = max(0, (end_date.replace(tzinfo=timezone.utc) - now).days) if end_date.tzinfo is None else max(0, (end_date - now).days)
            alerts.append(
                {
                    "type": "contract_expiring",
                    "contract_id": str(c["_id"]),
                    "title": c.get("title", "Contract"),
                    "message": f"Contract expiring in {days_left} day(s)",
                    "timestamp": now,
                }
            )
        elif derived == ContractStatus.EXPIRED and end_date:
            alerts.append(
                {
                    "type": "contract_expired",
                    "contract_id": str(c["_id"]),
                    "title": c.get("title", "Contract"),
                    "message": "Contract has expired",
                    "timestamp": now,
                }
            )

    payments_cursor = db["payments"].find(
        {
            "user_id": ObjectId(user_id),
            "status": {"$in": ["pending", "overdue"]},
        }
    )
    async for p in payments_cursor:
        due = p.get("due_date")
        if not due:
            continue
        due = due if due.tzinfo else due.replace(tzinfo=timezone.utc)
        if due <= now + timedelta(days=3):
            overdue = due < now
            alerts.append(
                {
                    "type": "payment_overdue" if overdue else "payment_due",
                    "payment_id": str(p["_id"]),
                    "contract_id": str(p["contract_id"]),
                    "title": "Payment Reminder",
                    "message": (
                        f"Payment of {p.get('currency', 'USD')} "
                        f"{float(p.get('amount', 0)):,.2f} "
                        + ("is overdue" if overdue else "is due soon")
                    ),
                    "timestamp": due,
                }
            )

    alerts.sort(key=lambda a: a.get("timestamp") or now, reverse=True)
    return alerts
