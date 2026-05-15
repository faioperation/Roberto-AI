import asyncio
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from schemas.payloads import CallRequest, AssistantRequest, TelephonyRequest
from vapi.vapi_handler import (
    create_assistant,
    trigger_call,
    link_telephony,
    process_webhook,
    get_call_status
)

app = FastAPI(title="Tugatai AI - Voice Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ================================
# ENDPOINTS
# ================================

@app.get("/")
def root():
    return {"message": "Tugatai AI Voice Agent is running"}


# ================================
# TRIGGER CALL
# ================================
@app.post("/voice/call")
def make_call(req: CallRequest):
    """
    Frontend sends customer phone number.
    Luna calls them back immediately.
    """
    try:
        result = trigger_call(
            customer_phone=req.customer_phone,
            assistant_id=req.assistant_id
        )
        return {
            "success": True,
            "call_id": result.get("id"),
            "message": "Luna is calling the customer now."
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
            business_name=req.business_name
        )
        return {
            "success": True,
            "assistant_id": result.get("id"),
            "message": f"Luna created for {req.business_name}"
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
            "data": result
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
    except Exception as e:
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
        with open("leads_backup.json", "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    leads.append(line)
        return {
            "success": True,
            "total": len(leads),
            "leads": leads
        }
    except FileNotFoundError:
        return {"success": True, "total": 0, "leads": []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))