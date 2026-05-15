import json
import os
import requests
from datetime import datetime
from schemas.payloads import LeadData

BACKEND_URL = os.getenv("BACKEND_URL", "")


def save_lead(lead: LeadData) -> dict:
    """
    Saves lead to backend CRM if available.
    Falls back to local JSON file if backend is not ready.
    """
    payload = {
        "tenant_id": lead.tenant_id,
        "call_id": lead.call_id,
        "customer_phone": lead.customer_phone,
        "destination_country": lead.destination_country,
        "destination_city": lead.destination_city,
        "pickup_location": lead.pickup_location,
        "pickup_time": lead.pickup_time,
        "service_type": str(lead.service_type.value) if lead.service_type else "unknown",
        "booking_confirmed": lead.booking_confirmed,
        "lead_status": str(lead.lead_status.value) if lead.lead_status else "cold",
        "follow_up_required": lead.follow_up_required,
        "follow_up_time": lead.follow_up_time,
        "sentiment": str(lead.sentiment.value) if lead.sentiment else "neutral",
        "call_outcome": str(lead.call_outcome.value) if lead.call_outcome else "completed",
        "call_summary": lead.call_summary,
        "call_duration": lead.call_duration,
        "created_at": datetime.utcnow().isoformat()
    }

    # Backend ready থাকলে POST করো
    if BACKEND_URL and BACKEND_URL != "http://localhost:8000":
        try:
            response = requests.post(
                f"{BACKEND_URL}/api/leads",
                json=payload,
                timeout=10
            )
            if response.status_code in [200, 201]:
                print(f"[CRM] Lead pushed to backend: {lead.customer_phone} | {lead.lead_status}")
                return {"success": True, "data": response.json()}
            else:
                print(f"[CRM] Backend error: {response.status_code}")
                save_lead_locally(payload)
                return {"success": False, "error": response.text}

        except Exception as e:
            print(f"[CRM] Backend not reachable: {e}")
            save_lead_locally(payload)
            return {"success": False, "error": str(e)}

    # Backend নেই → locally save করো
    else:
        save_lead_locally(payload)
        return {"success": True, "saved": "local"}


def save_lead_locally(payload: dict):
    """
    Saves lead to local JSON file.
    Used when backend CRM is not ready yet.
    """
    try:
        with open("leads_backup.json", "a") as f:
            f.write(json.dumps(payload) + "\n")
        print(f"[CRM] Lead saved locally ✅ | Phone: {payload.get('customer_phone')} | Status: {payload.get('lead_status')}")
    except Exception as e:
        print(f"[CRM] Local save failed: {e}")