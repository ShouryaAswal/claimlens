"""
Static configuration for ClaimLens.

Centralising this here means Sprint 2 (LLM extraction) and Sprint 4
(triage) just import these instead of hard-coding strings everywhere.
"""

# Confidence below this -> flagged for human review (matches the
# enterprise design doc's "Confidence-Based Routing" rule).
CONFIDENCE_THRESHOLD = 0.7

# Per-claim-type field schema. Sprint 2's LLM Extraction Agent will be
# prompted with exactly these field names + descriptions.
CLAIM_FIELD_SCHEMAS = {
    "auto": {
        "policy_number": "Policy ID for the auto policy",
        "claimant_name": "Full legal name of the driver/claimant",
        "loss_date": "Date of the accident",
        "claim_amount": "Total repair/rental estimate amount, in USD",
        "vehicle_vin": "Vehicle Identification Number",
    },
    "property": {
        "policy_number": "Policy ID for the property policy",
        "policyholder_name": "Full legal name of the policyholder",
        "loss_date": "Date of loss / damage",
        "claim_amount": "Replacement cost or ACV claimed, in USD",
        "property_address": "Address of the damaged property",
    },
    "health": {
        "policy_number": "Member / policy ID",
        "patient_name": "Full legal name of the patient",
        "admission_date": "Date of hospital admission",
        "claim_amount": "Total billed amount, in USD",
        "provider_name": "Name of the treating hospital / provider",
    },
}

# Sprint 4 rule-based triage weights (slide "Triage Logic for MVP")
TRIAGE_RULES = {
    "missing_required_field": 25,
    "field_has_no_evidence": 20,
    "low_confidence": 15,
    "claim_amount_above_threshold": 15,
    "document_type_unknown": 20,
}

CLAIM_AMOUNT_HIGH_RISK_THRESHOLD = 25000  # USD

TRIAGE_ROUTES = {
    (0, 25): "STP Candidate",
    (26, 60): "Needs Human Review",
    (61, 10_000): "Incomplete / High Risk",
}
