from schemas.payloads import LeadData, LeadStatus, SentimentType


def score_lead(structured_data: dict, summary: str) -> LeadData:
    """
    Scores the lead based on call data.
    Returns a fully populated LeadData object.
    """

    destination_country = structured_data.get("destination_country", "")
    destination_city = structured_data.get("destination_city", "")
    pickup_location = structured_data.get("pickup_location", "")
    pickup_time = structured_data.get("pickup_time", "")
    service_type = structured_data.get("service_type", "unknown")
    booking_confirmed = structured_data.get("booking_confirmed", False)
    phone_number = structured_data.get("phone_number", "")
    items = structured_data.get("items", "")

    # ================================
    # LEAD SCORING LOGIC
    # ================================
    lead_status = LeadStatus.cold

    # Hot — booking confirmed with full details
    if booking_confirmed and destination_country and pickup_location:
        lead_status = LeadStatus.hot

    # Warm — has destination and service but not confirmed
    elif destination_country and service_type != "unknown":
        lead_status = LeadStatus.warm

    # Cold — just inquired, no details
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
    # SENTIMENT ANALYSIS (basic)
    # ================================
    sentiment = SentimentType.neutral
    negative_words = ["angry", "frustrated", "terrible", "worst", "cancel", "refund", "upset"]
    positive_words = ["great", "perfect", "thank", "book", "confirm", "yes", "good"]

    summary_lower = summary.lower()

    if any(word in summary_lower for word in negative_words):
        sentiment = SentimentType.negative
    elif any(word in summary_lower for word in positive_words):
        sentiment = SentimentType.positive

    return LeadData(
        destination_country=destination_country,
        destination_city=destination_city,
        pickup_location=pickup_location,
        pickup_time=pickup_time,
        service_type=service_type,
        booking_confirmed=booking_confirmed,
        lead_status=lead_status,
        follow_up_required=follow_up_required,
        follow_up_time=follow_up_time,
        sentiment=sentiment,
        items=items,
        call_summary=summary,
    )