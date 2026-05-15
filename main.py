import os
import json
import asyncio
import requests
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from schemas.payloads import CallRequest, AssistantRequest, TelephonyRequest
from vapi.vapi_handler import (
    create_assistant,
    trigger_call,
    link_telephony,
    process_webhook,
    get_call_status,
)

load_dotenv()

VAPI_ASSISTANT_ID = os.getenv("VAPI_ASSISTANT_ID", "")
LEADS_FILE = "leads_backup.json"

app = FastAPI(title="Tugatai AI - Voice Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ================================
# Schema for the frontend form
# ================================
class CallTriggerRequest(BaseModel):
    phone_number: str = Field(
        ...,
        description="Full phone number in E.164 format, e.g. +93701234567",
        examples=["+93701234567"],
    )
    email: Optional[str] = Field(
        None,
        description="Optional customer email captured with the lead",
    )


# ================================
# Helpers
# ================================
def _save_quick_lead(phone: str, email: Optional[str], call_id: str) -> None:
    """
    Append a lightweight lead entry to leads_backup.json (JSONL format)
    the moment a call is requested. This guarantees we keep the contact
    info even if the user never picks up the phone.
    The full lead from the call itself comes in later via /webhook/vapi.
    """
    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "source": "request_call_form",
        "customer_phone": phone,
        "email": email,
        "call_id": call_id,
        "status": "call_triggered",
    }
    try:
        with open(LEADS_FILE, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        print(f"[LEADS] Failed to write quick lead: {e}")


def _validate_e164(phone: str) -> str:
    """Strip whitespace/dashes and ensure E.164-ish format (+ followed by 7–15 digits)."""
    cleaned = phone.strip().replace(" ", "").replace("-", "")
    if not cleaned.startswith("+") or not cleaned[1:].isdigit() or not (8 <= len(cleaned) <= 16):
        raise HTTPException(
            status_code=400,
            detail="Phone number must be in E.164 format, e.g. +93701234567",
        )
    return cleaned


# ================================
# ENDPOINTS
# ================================

@app.get("/")
def root():
    return {"message": "Tugatai AI Voice Agent is running"}


# ================================
# FRONTEND "Get a call" BUTTON
# This is the one the landing page hits.
# ================================
@app.post("/voice/request-call")
def request_call(req: CallTriggerRequest):
    """
    Triggered when the user clicks 'Get a call' on the landing page.
    Saves their contact info, then asks Vapi to call them via Twilio.
    """
    if not VAPI_ASSISTANT_ID:
        raise HTTPException(
            status_code=500,
            detail="VAPI_ASSISTANT_ID is not configured in .env",
        )

    phone = _validate_e164(req.phone_number)

    try:
        call = trigger_call(
            customer_phone=phone,
            assistant_id=VAPI_ASSISTANT_ID,
        )
    except requests.exceptions.HTTPError as e:
        body = e.response.text if e.response is not None else str(e)
        raise HTTPException(status_code=502, detail=f"Vapi error: {body}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to trigger call: {e}")

    call_id = call.get("id", "")
    _save_quick_lead(phone=phone, email=req.email, call_id=call_id)

    return {
        "success": True,
        "status": "calling",
        "call_id": call_id,
        "phone": phone,
        "email": req.email,
        "message": "Luna will call you in a few seconds.",
    }


# ================================
# TRIGGER CALL (backend-to-backend usage, e.g. admin panel)
# ================================
@app.post("/voice/call")
def make_call(req: CallRequest):
    """
    Direct call trigger when the caller already knows the assistant_id
    (e.g. another internal service, admin panel, scheduled callback).
    The landing page should use /voice/request-call instead.
    """
    try:
        result = trigger_call(
            customer_phone=req.customer_phone,
            assistant_id=req.assistant_id,
        )
        return {
            "success": True,
            "call_id": result.get("id"),
            "message": "Luna is calling the customer now.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ================================
# CREATE ASSISTANT (Onboarding)
# ================================
@app.post("/voice/assistant/create")
def setup_assistant(req: AssistantRequest):
    """
    Creates Luna for a new business tenant.
    Run once during onboarding.
    """
    try:
        result = create_assistant(
            tenant_id=req.tenant_id,
            business_name=req.business_name,
        )
        return {
            "success": True,
            "assistant_id": result.get("id"),
            "message": f"Luna created for {req.business_name}",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ================================
# LINK TWILIO (Once)
# ================================
@app.post("/voice/assistant/link-phone")
def link_phone(req: TelephonyRequest):
    """
    Links Twilio number to Luna.
    Run once after creating the assistant.
    """
    try:
        result = link_telephony(assistant_id=req.assistant_id)
        return {
            "success": True,
            "message": "Twilio number linked to Luna.",
            "data": result,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ================================
# WEBHOOK — Lead Collection
# ================================
@app.post("/webhook/vapi")
async def vapi_webhook(request: Request):
    """
    Vapi calls this after every call ends.
    Responds immediately, processes in background.
    """
    try:
        payload = await request.json()
        asyncio.create_task(handle_webhook_background(payload))
        return {"status": "ok"}
    except Exception:
        return {"status": "ok"}  # Always return 200 fast to Vapi


async def handle_webhook_background(payload: dict):
    """
    Background processing — Vapi won't wait for this.
    Scores lead and pushes to CRM.
    """
    try:
        result = process_webhook(payload)
        print(f"[WEBHOOK] Processed: {result}")
    except Exception as e:
        print(f"[WEBHOOK] Error: {e}")


# ================================
# GET CALL STATUS
# ================================
@app.get("/voice/call/{call_id}")
def call_status(call_id: str):
    """
    Check status of any call by call_id.
    Useful for the frontend to show "ringing → in-progress → ended".
    """
    try:
        result = get_call_status(call_id)
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ================================
# GET LEADS (Testing)
# ================================
@app.get("/leads")
def get_leads():
    """
    Returns locally saved leads from backup file.
    Use this when backend CRM is not connected yet.
    """
    try:
        leads = []
        with open(LEADS_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        leads.append(json.loads(line))
                    except json.JSONDecodeError:
                        leads.append(line)  # fall back to raw line if not JSON
        return {
            "success": True,
            "total": len(leads),
            "leads": leads,
        }
    except FileNotFoundError:
        return {"success": True, "total": 0, "leads": []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))