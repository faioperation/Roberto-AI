from pydantic import BaseModel
from typing import Optional
from enum import Enum


class ServiceType(str, Enum):
    sea = "sea"
    air = "air"
    dhl = "dhl"
    unknown = "unknown"


class LeadStatus(str, Enum):
    cold = "cold"
    warm = "warm"
    hot = "hot"


class CallOutcome(str, Enum):
    answered = "answered"
    not_answered = "not_answered"
    transferred = "transferred"
    completed = "completed"


class SentimentType(str, Enum):
    positive = "positive"
    neutral = "neutral"
    negative = "negative"


# ================================
# Lead Model
# ================================
class LeadData(BaseModel):
    # Identity
    tenant_id: Optional[str] = "tugatai_cargo_qatar"
    call_id: Optional[str] = ""
    customer_phone: Optional[str] = ""

    # Shipping Details
    destination_country: Optional[str] = ""
    destination_city: Optional[str] = ""
    pickup_location: Optional[str] = ""
    pickup_time: Optional[str] = ""
    items: Optional[str] = ""
    service_type: Optional[ServiceType] = ServiceType.unknown

    # Lead Intelligence
    lead_status: Optional[LeadStatus] = LeadStatus.cold
    booking_confirmed: Optional[bool] = False
    follow_up_required: Optional[bool] = False
    follow_up_time: Optional[str] = ""
    sentiment: Optional[SentimentType] = SentimentType.neutral
    call_outcome: Optional[CallOutcome] = CallOutcome.answered

    # Summary
    call_summary: Optional[str] = ""
    call_duration: Optional[str] = ""


# ================================
# Call Request Model
# ================================
class CallRequest(BaseModel):
    customer_phone: str
    assistant_id: str


class AssistantRequest(BaseModel):
    tenant_id: str
    business_name: str


class TelephonyRequest(BaseModel):
    assistant_id: str