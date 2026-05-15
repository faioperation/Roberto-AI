import os
import requests
from dotenv import load_dotenv
from core.settings import (
    VAPI_BASE_URL,
    VAPI_HEADERS,
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_PHONE_NUMBER
)
from vapi.vapi_config import get_assistant_payload
from schemas.payloads import (
    LeadData,
    LeadStatus,
    CallOutcome,
    SentimentType,
    ServiceType
)
from tools.crm_tool import save_lead

load_dotenv()

VAPI_PHONE_NUMBER_ID = os.getenv("VAPI_PHONE_NUMBER_ID", "")


# ================================
# 1. CREATE ASSISTANT
# ================================
def create_assistant(tenant_id: str, business_name: str) -> dict:
    """
    Creates Luna on Vapi for a specific tenant.
    Call this ONCE during business onboarding.
    Returns assistant_id — save this in your database.
    """
    url = f"{VAPI_BASE_URL}/assistant"
    payload = get_assistant_payload(tenant_id, business_name)

    response = requests.post(url, headers=VAPI_HEADERS, json=payload)
    response.raise_for_status()

    data = response.json()
    print(f"[VAPI] Assistant created: {data.get('id')} for {tenant_id}")
    return data


# ================================
# 2. TRIGGER OUTBOUND CALL
# ================================
def trigger_call(customer_phone: str, assistant_id: str) -> dict:
    """
    Triggers an outbound call to the customer.
    Called when user clicks Get a Call on the frontend.
    """
    url = f"{VAPI_BASE_URL}/call"

    payload = {
        "assistantId": assistant_id,
        "customer": {
            "number": customer_phone
        },
        "phoneNumberId": VAPI_PHONE_NUMBER_ID
    }

    print(f"[VAPI] Triggering call to: {customer_phone}")
    response = requests.post(url, headers=VAPI_HEADERS, json=payload)
    response.raise_for_status()

    data = response.json()
    print(f"[VAPI] Call triggered → {customer_phone} | Call ID: {data.get('id')}")
    return data


# ================================
# 3. LINK TWILIO TO ASSISTANT
# ================================
def link_telephony(assistant_id: str) -> dict:
    """
    Links Twilio phone number to Luna on Vapi.
    Run this ONCE after creating the assistant.
    """
    url = f"{VAPI_BASE_URL}/phone-number"

    payload = {
        "provider": "twilio",
        "number": TWILIO_PHONE_NUMBER,
        "assistantId": assistant_id,
        "twilioAccountSid": TWILIO_ACCOUNT_SID,
        "twilioAuthToken": TWILIO_AUTH_TOKEN,
        "name": f"Luna Line - {assistant_id}"
    }

    response = requests.post(url, headers=VAPI_HEADERS, json=payload)
    response.raise_for_status()

    data = response.json()
    print(f"[VAPI] Twilio linked: {TWILIO_PHONE_NUMBER} → {assistant_id}")
    return data


# ================================
# 4. LEAD SCORING (No summary_agent)
# ================================
def score_lead_from_call(
    structured_data: dict,
    summary: str,
    customer_number: str,
    call_id: str,
    call_outcome: CallOutcome,
    duration: str
) -> LeadData:
    """
    Scores lead directly from Vapi structured data.
    No summary_agent needed — summary_agent is for social media agent later.
    """

    destination_country = structured_data.get("destination_country", "")
    destination_city = structured_data.get("destination_city", "")
    pickup_location = structured_data.get("pickup_location", "")
    pickup_time = structured_data.get("pickup_time", "")
    phone_number = structured_data.get("phone_number", "") or customer_number
    service_type = structured_data.get("service_type", "unknown")
    booking_confirmed = structured_data.get("booking_confirmed", False)

    # ================================
    # LEAD SCORING LOGIC
    # ================================
    if booking_confirmed and destination_country and pickup_location:
        lead_status = LeadStatus.hot
    elif destination_country and service_type != "unknown":
        lead_status = LeadStatus.warm
    else:
        lead_status = LeadStatus.cold

    # ================================
    # FOLLOW UP LOGIC
    # ================================
    follow_up_required = False
    follow_up_time = ""

    if lead_status == LeadStatus.warm and not booking_confirmed:
        follow_up_required = True
        follow_up_time = pickup_time if pickup_time else "within 24 hours"

    # ================================
    # BASIC SENTIMENT (from summary)
    # ================================
    sentiment = SentimentType.neutral
    summary_lower = summary.lower()

    negative_words = ["angry", "frustrated", "terrible", "worst", "cancel", "refund", "upset", "wrong"]
    positive_words = ["great", "perfect", "thank", "book", "confirm", "yes", "good", "happy"]

    if any(word in summary_lower for word in negative_words):
        sentiment = SentimentType.negative
    elif any(word in summary_lower for word in positive_words):
        sentiment = SentimentType.positive

    return LeadData(
        # Identity
        tenant_id=os.getenv("TENANT_ID", "tugatai_cargo_qatar"),
        call_id=call_id,
        customer_phone=phone_number,

        # Shipping Details
        destination_country=destination_country,
        destination_city=destination_city,
        pickup_location=pickup_location,
        pickup_time=pickup_time,
        service_type=service_type,

        # Lead Intelligence
        booking_confirmed=booking_confirmed,
        lead_status=lead_status,
        follow_up_required=follow_up_required,
        follow_up_time=follow_up_time,
        sentiment=sentiment,
        call_outcome=call_outcome,

        # Call Info
        call_summary=summary,
        call_duration=str(duration),
    )


# ================================
# 5. PROCESS WEBHOOK
# ================================
def process_webhook(payload: dict) -> dict:
    """
    Processes Vapi webhook after call ends.
    Extracts booking data, scores lead, pushes to CRM.
    summary_agent is NOT used here — reserved for social media agent.
    """
    message = payload.get("message", {})
    event_type = message.get("type", "")

    print(f"[WEBHOOK] Event received: {event_type}")

    # ================================
    # END OF CALL REPORT
    # ================================
    if event_type == "end-of-call-report":

        call = message.get("call", {})
        analysis = message.get("analysis", {})
        structured_data = analysis.get("structuredData", {})
        summary = analysis.get("summary", "")

        customer_number = call.get("customer", {}).get("number", "")
        call_id = call.get("id", "")
        ended_reason = call.get("endedReason", "")
        duration = call.get("duration", "")

        # ================================
        # CALL OUTCOME
        # ================================
        if ended_reason == "no-answer":
            call_outcome = CallOutcome.not_answered
        elif "transfer" in ended_reason:
            call_outcome = CallOutcome.transferred
        else:
            call_outcome = CallOutcome.completed

        # ================================
        # SCORE LEAD DIRECTLY
        # ================================
        lead = score_lead_from_call(
            structured_data=structured_data,
            summary=summary,
            customer_number=customer_number,
            call_id=call_id,
            call_outcome=call_outcome,
            duration=duration
        )

        print(f"[LEAD] Phone: {lead.customer_phone} | Status: {lead.lead_status} | Sentiment: {lead.sentiment}")

        # ================================
        # PUSH TO CRM
        # ================================
        crm_result = save_lead(lead)

        return {
            "status": "processed",
            "customer_phone": lead.customer_phone,
            "lead_status": lead.lead_status,
            "booking_confirmed": lead.booking_confirmed,
            "destination": f"{lead.destination_country} - {lead.destination_city}",
            "service_type": lead.service_type,
            "sentiment": lead.sentiment,
            "follow_up_required": lead.follow_up_required,
            "call_outcome": lead.call_outcome,
            "crm": crm_result
        }

    # ================================
    # CALL STARTED
    # ================================
    elif event_type == "call-started":
        call_id = message.get("call", {}).get("id", "")
        print(f"[WEBHOOK] Call started | ID: {call_id}")
        return {"status": "call_started", "call_id": call_id}

    # ================================
    # OTHER EVENTS — IGNORE
    # ================================
    else:
        return {"status": "ignored", "event": event_type}


# ================================
# 6. GET CALL STATUS
# ================================
def get_call_status(call_id: str) -> dict:
    """
    Fetches current status of a call from Vapi.
    """
    url = f"{VAPI_BASE_URL}/call/{call_id}"
    response = requests.get(url, headers=VAPI_HEADERS)
    response.raise_for_status()
    return response.json()