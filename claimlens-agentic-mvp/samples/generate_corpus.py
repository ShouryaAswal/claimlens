"""
Generates the Sprint 0+ synthetic test corpus: 24 multi-page claim
packets (8 Auto + 8 Property + 8 Health), each 15-22 pages, built from
several stitched sub-documents the way a real claim folder looks when
exported as one PDF (FNOL + declaration + report + itemised
estimate/bill + correspondence + adjuster notes).

Two kinds of "noise" are deliberately injected and recorded in the
manifest, because a pipeline that only ever sees perfect documents
hasn't actually been tested:
  - missing_required_field: one schema field is silently omitted from
    the rendered text for ~30% of claims (tests Sprint 4's "missing
    required field" triage rule).
  - date_inconsistency: the itemised estimate/bill is dated BEFORE the
    report/admission document it's based on, for ~20% of claims
    (tests the timeline-consistency idea from the design deck).

Run: python3 samples/generate_corpus.py
Output: samples/corpus/<lob>/<claim_id>.pdf  +  outputs/corpus_manifest.json
"""

import json
import random
from pathlib import Path

from samples.corpus_data import (
    ADJUSTERS, AUTO_PARTS_LABOR, CITIES, CONTENTS_ITEMS, CONTRACTORS,
    CAUSES_OF_LOSS_PROPERTY, CPT_CODES, HOSPITALS, ICD10_CODES, INSPECTORS,
    OFFICERS, ROOMS, VEHICLE_MAKES_MODELS, random_address, random_date,
    random_name, random_policy_number, random_vin,
)
from samples.pdf_writer import SimplePDFWriter

OUT_DIR = Path("samples/corpus")
MANIFEST_PATH = Path("outputs/corpus_manifest.json")
CLAIMS_PER_LOB = 8
MIN_PAGES, MAX_PAGES = 15, 22


def _maybe_drop(rng, fields: dict, drop_probability: float) -> list:
    """Randomly omit exactly one field's value (manifest still records
    the true value as ground truth; the rendered doc just won't show
    it). Returns the list of dropped field names."""
    if rng.random() < drop_probability:
        field_to_drop = rng.choice(list(fields.keys()))
        return [field_to_drop]
    return []


def build_auto_claim(rng: random.Random, claim_id: str, target_pages: int) -> dict:
    policy_number = random_policy_number(rng, "AUTO")
    claimant = random_name(rng)
    make, model = rng.choice(VEHICLE_MAKES_MODELS)
    vin = random_vin(rng)
    loss_date = random_date(rng)
    estimate_date = random_date(rng)
    claim_amount = rng.randint(800, 15000)
    city = rng.choice(CITIES)

    fields = {
        "policy_number": policy_number,
        "claimant_name": claimant,
        "loss_date": loss_date,
        "claim_amount": str(claim_amount),
        "vehicle_vin": vin,
    }
    dropped = _maybe_drop(rng, fields, drop_probability=0.3)
    date_inconsistent = rng.random() < 0.2
    if date_inconsistent:
        # Estimate dated BEFORE the loss it's supposed to follow.
        estimate_date = random_date(rng, month_range=(1, 2))
        loss_date = random_date(rng, month_range=(4, 6))
        fields["loss_date"] = loss_date

    path = OUT_DIR / "auto" / f"{claim_id}.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    w = SimplePDFWriter(str(path))

    # --- Sub-doc 1: FNOL / cover sheet ---
    w.add_title("Auto Insurance Claim - First Notice of Loss")
    w.add_lines([
        f"Claim ID: {claim_id}",
        f"Policy Number: {policy_number}" if "policy_number" not in dropped else "Policy Number: [PENDING VERIFICATION]",
        f"Claimant Name: {claimant}" if "claimant_name" not in dropped else "Claimant Name: [SEE ATTACHED]",
        f"Contact City: {city}",
        f"Loss Date: {loss_date}" if "loss_date" not in dropped else "Loss Date: [TO BE CONFIRMED]",
        "Reported By: Policyholder (phone intake)",
        "Brief Description: Vehicle collision, third-party involved.",
    ])
    w.new_page()

    # --- Sub-doc 2: Policy declaration ---
    w.add_title("Policy Declaration Page")
    w.add_lines([
        f"Policy Number: {policy_number}",
        f"Vehicle: {make} {model}",
        f"VIN: {vin}" if "vehicle_vin" not in dropped else "VIN: [REFER TO RC BOOK]",
        "Coverage: Collision / Comprehensive",
        "Deductible: USD 250",
        "Policy Period: 2026-01-01 to 2026-12-31",
    ])
    w.new_page()

    # --- Sub-doc 3: Police report narrative ---
    w.add_title("Police Report")
    w.add_lines([
        f"Reporting Officer: {rng.choice(OFFICERS)}",
        f"Location: {rng.choice(['MG Road', 'Outer Ring Road', 'Anna Salai', 'FC Road'])}, {city}",
        f"Date of Incident: {loss_date}",
    ])
    w.add_subheading("Narrative")
    w.add_paragraph(
        f"On the date of loss, the insured vehicle ({make} {model}) was travelling when it was "
        f"struck by a third-party vehicle at an intersection. The collision caused visible damage "
        f"to the front and side panels. Both parties exchanged insurance details at the scene. "
        f"No injuries were reported by either party. A tow truck was called to remove the vehicle "
        f"from the roadway. Traffic signal was confirmed functional at the time of the incident "
        f"by the attending officer."
    )
    w.add_paragraph(
        f"Witness statements were collected from two bystanders present at the scene. Photographs "
        f"of the damage and the intersection were taken for the case file. The third-party driver "
        f"was issued a citation for failure to yield right of way."
    )
    w.new_page()

    # --- Sub-doc 4: Adjuster inspection notes ---
    w.add_title("Adjuster Inspection Notes")
    w.add_lines([f"Inspecting Adjuster: {rng.choice(ADJUSTERS)}", f"Inspection Date: {estimate_date}"])
    w.add_subheading("Damaged Components Observed")
    damaged = rng.sample([p for p, _ in AUTO_PARTS_LABOR], k=min(5, len(AUTO_PARTS_LABOR)))
    w.add_lines([f"- {d}" for d in damaged])
    w.new_page()

    # --- Sub-doc 5: Itemised repair estimate (page-count lever) ---
    w.add_title("Repair Estimate")
    w.add_lines([f"Estimate Date: {estimate_date}", "Body Shop: AutoFix Garage Pvt. Ltd.", ""])
    w.add_subheading("Line Items")
    running_total = 0
    line_no = 0
    while w.page_count < target_pages - 1:
        item, cost = rng.choice(AUTO_PARTS_LABOR)
        line_no += 1
        running_total += cost
        w.add_line(f"{line_no:03d}  {item:<35} USD {cost:>8,}")
    w.add_line("")
    w.add_line(f"TOTAL ESTIMATE: USD {claim_amount if 'claim_amount' not in dropped else running_total:,}")
    w.new_page()

    # --- Sub-doc 6: Correspondence ---
    w.add_title("Correspondence - Claim Acknowledgement")
    w.add_paragraph(
        f"Dear {claimant if 'claimant_name' not in dropped else 'Policyholder'}, this letter "
        f"confirms receipt of your claim under policy {policy_number}. Your claim has been "
        f"assigned to {rng.choice(ADJUSTERS)} for review. We will be in touch within 5 business "
        f"days regarding the next steps for your repair estimate."
    )

    # --- Sub-doc 7: Closing notes ---
    w.add_subheading("Adjuster Closing Notes")
    w.add_paragraph(
        "Claim reviewed and estimate found consistent with reported damage. Recommend approval "
        "for straight-through processing pending final documentation check."
    )

    w.save()

    return {
        "claim_id": claim_id,
        "claim_type": "auto",
        "file": str(path),
        "page_count": w.page_count,
        "ground_truth": fields,
        "missing_fields": dropped,
        "date_inconsistency": date_inconsistent,
    }


def build_property_claim(rng: random.Random, claim_id: str, target_pages: int) -> dict:
    policy_number = random_policy_number(rng, "PROP")
    policyholder = random_name(rng)
    address = random_address(rng)
    loss_date = random_date(rng)
    inspection_date = random_date(rng)
    cause = rng.choice(CAUSES_OF_LOSS_PROPERTY)
    claim_amount = rng.randint(2000, 60000)

    fields = {
        "policy_number": policy_number,
        "policyholder_name": policyholder,
        "loss_date": loss_date,
        "claim_amount": str(claim_amount),
        "property_address": address,
    }
    dropped = _maybe_drop(rng, fields, drop_probability=0.3)
    date_inconsistent = rng.random() < 0.2
    if date_inconsistent:
        inspection_date = random_date(rng, month_range=(1, 2))
        loss_date = random_date(rng, month_range=(4, 6))
        fields["loss_date"] = loss_date

    path = OUT_DIR / "property" / f"{claim_id}.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    w = SimplePDFWriter(str(path))

    w.add_title("Property Insurance Claim - First Notice of Loss")
    w.add_lines([
        f"Claim ID: {claim_id}",
        f"Policy Number: {policy_number}" if "policy_number" not in dropped else "Policy Number: [PENDING]",
        f"Policyholder Name: {policyholder}" if "policyholder_name" not in dropped else "Policyholder Name: [SEE DEED]",
        f"Property Address: {address}" if "property_address" not in dropped else "Property Address: [ON FILE]",
        f"Loss Date: {loss_date}" if "loss_date" not in dropped else "Loss Date: [UNCONFIRMED]",
        f"Cause of Loss: {cause}",
    ])
    w.new_page()

    w.add_title("Policy Declaration Page")
    w.add_lines([
        f"Policy Number: {policy_number}",
        "Dwelling Coverage: USD 250,000",
        "Personal Property Coverage: USD 100,000",
        "Deductible: USD 1,000",
        "Policy Period: 2026-01-01 to 2026-12-31",
    ])
    w.new_page()

    w.add_title("Inspection Report")
    w.add_lines([f"Inspector: {rng.choice(INSPECTORS)}", f"Inspection Date: {inspection_date}"])
    w.add_subheading("Damaged Rooms")
    damaged_rooms = rng.sample(ROOMS, k=min(3, len(ROOMS)))
    w.add_lines([f"- {r}" for r in damaged_rooms])
    w.add_subheading("Narrative")
    w.add_paragraph(
        f"Inspection of the property revealed {cause.lower()} affecting {', '.join(damaged_rooms)}. "
        f"Structural integrity of the affected rooms was assessed and found stable, though "
        f"finishing materials including flooring, drywall, and cabinetry sustained significant "
        f"damage requiring replacement. Moisture readings were taken in adjacent rooms to confirm "
        f"no further spread. Photographs were taken of all affected areas for the claim file."
    )
    w.new_page()

    w.add_title("Contents Inventory")
    w.add_lines([f"Inventory Date: {inspection_date}", ""])
    line_no = 0
    while w.page_count < target_pages - 2:
        item, value = rng.choice(CONTENTS_ITEMS)
        line_no += 1
        w.add_line(f"{line_no:03d}  {item:<30} Replacement Value: USD {value:>7,}")
    w.new_page()

    w.add_title("Contractor Repair Estimate")
    w.add_lines([f"Contractor: {rng.choice(CONTRACTORS)}", f"Estimate Date: {inspection_date}", ""])
    w.add_lines([
        f"Replacement Cost Value (RCV): USD {claim_amount:,}",
        f"Actual Cash Value (ACV): USD {int(claim_amount * 0.8):,}",
    ])
    w.new_page()

    w.add_title("Correspondence - Claim Status Update")
    w.add_paragraph(
        f"Dear {policyholder if 'policyholder_name' not in dropped else 'Policyholder'}, we have "
        f"completed our inspection of the property at {address if 'property_address' not in dropped else 'the insured location'}. "
        f"Your contractor estimate is under review and we expect to issue a settlement decision shortly."
    )
    w.add_subheading("Adjuster Closing Notes")
    w.add_paragraph(
        "Estimate reviewed against inspection findings; line items consistent with reported damage."
    )

    w.save()

    return {
        "claim_id": claim_id,
        "claim_type": "property",
        "file": str(path),
        "page_count": w.page_count,
        "ground_truth": fields,
        "missing_fields": dropped,
        "date_inconsistency": date_inconsistent,
    }


def build_health_claim(rng: random.Random, claim_id: str, target_pages: int) -> dict:
    policy_number = random_policy_number(rng, "HLTH")
    patient = random_name(rng)
    provider = rng.choice(HOSPITALS)
    admission_date = random_date(rng)
    bill_date = random_date(rng)
    diagnosis_code, diagnosis_desc = rng.choice(ICD10_CODES)
    claim_amount = rng.randint(500, 50000)

    fields = {
        "policy_number": policy_number,
        "patient_name": patient,
        "admission_date": admission_date,
        "claim_amount": str(claim_amount),
        "provider_name": provider,
    }
    dropped = _maybe_drop(rng, fields, drop_probability=0.3)
    date_inconsistent = rng.random() < 0.2
    if date_inconsistent:
        bill_date = random_date(rng, month_range=(1, 2))
        admission_date = random_date(rng, month_range=(4, 6))
        fields["admission_date"] = admission_date

    path = OUT_DIR / "health" / f"{claim_id}.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    w = SimplePDFWriter(str(path))

    w.add_title("Health Insurance Claim - Pre-Authorization Request")
    w.add_lines([
        f"Claim ID: {claim_id}",
        f"Member ID / Policy Number: {policy_number}" if "policy_number" not in dropped else "Member ID: [VERIFY WITH HR]",
        f"Patient Name: {patient}" if "patient_name" not in dropped else "Patient Name: [REDACTED FOR PRE-AUTH]",
        f"Provider Name: {provider}" if "provider_name" not in dropped else "Provider Name: [NETWORK HOSPITAL]",
        f"Requested Admission Date: {admission_date}" if "admission_date" not in dropped else "Requested Admission Date: [PENDING]",
        f"Diagnosis: {diagnosis_code} - {diagnosis_desc}",
    ])
    w.new_page()

    w.add_title("Admission Notice")
    w.add_lines([
        f"Admission Date: {admission_date}",
        f"Attending Physician: Dr. {rng.choice(['S. Bhatt', 'A. Krishnan', 'M. Iyer', 'R. Sengupta'])}",
        f"Ward: {rng.choice(['General Ward', 'ICU', 'Surgical Ward', 'Day Care'])}",
    ])
    w.new_page()

    w.add_title("Discharge Summary")
    w.add_lines([f"Diagnosis: {diagnosis_code} - {diagnosis_desc}"])
    w.add_subheading("Clinical Course")
    w.add_paragraph(
        f"Patient was admitted with {diagnosis_desc.lower()} and underwent evaluation including "
        f"relevant laboratory and imaging investigations. Treatment was initiated per standard "
        f"protocol and the patient demonstrated steady clinical improvement over the course of "
        f"admission. Vital signs remained stable throughout the stay. Patient was discharged in "
        f"satisfactory condition with follow-up instructions and a prescribed medication regimen."
    )
    w.add_paragraph(
        "Discharge instructions include rest, prescribed medication as directed, and a follow-up "
        "outpatient consultation scheduled within two weeks of discharge."
    )
    w.new_page()

    w.add_title("Itemised Hospital Bill")
    w.add_lines([f"Bill Date: {bill_date}", f"Provider: {provider}", ""])
    w.add_subheading("Charges (CPT/HCPCS coded)")
    line_no = 0
    running_total = 0
    while w.page_count < target_pages - 1:
        code, desc, cost = rng.choice(CPT_CODES)
        line_no += 1
        running_total += cost
        w.add_line(f"{line_no:03d}  [{code}] {desc:<38} USD {cost:>7,}")
    w.add_line("")
    w.add_line(f"TOTAL BILLED AMOUNT: USD {claim_amount if 'claim_amount' not in dropped else running_total:,}")
    w.new_page()

    w.add_title("Explanation of Benefits (EOB)")
    w.add_lines([
        f"Total Billed: USD {claim_amount:,}",
        f"In-Network Discount: USD {int(claim_amount * 0.15):,}",
        f"Co-pay (Patient Responsibility): USD {int(claim_amount * 0.1):,}",
        f"Amount Payable by Insurer: USD {int(claim_amount * 0.75):,}",
    ])
    w.add_subheading("Provider Correspondence")
    w.add_paragraph(
        f"This letter confirms that {provider} has submitted the itemised bill for {patient if 'patient_name' not in dropped else 'the above-named patient'} "
        f"for processing. Please remit payment per the EOB terms within 30 days."
    )

    w.save()

    return {
        "claim_id": claim_id,
        "claim_type": "health",
        "file": str(path),
        "page_count": w.page_count,
        "ground_truth": fields,
        "missing_fields": dropped,
        "date_inconsistency": date_inconsistent,
    }


def main():
    rng = random.Random(42)  # reproducible corpus
    manifest = []

    builders = {
        "auto": build_auto_claim,
        "property": build_property_claim,
        "health": build_health_claim,
    }

    for lob, builder in builders.items():
        for i in range(1, CLAIMS_PER_LOB + 1):
            claim_id = f"{lob.upper()}-{i:03d}"
            target_pages = rng.randint(MIN_PAGES, MAX_PAGES)
            entry = builder(rng, claim_id, target_pages)
            manifest.append(entry)
            print(f"{entry['file']}: {entry['page_count']} pages "
                  f"(missing={entry['missing_fields']}, date_issue={entry['date_inconsistency']})")

    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST_PATH, "w") as f:
        json.dump(manifest, f, indent=2)

    pages = [m["page_count"] for m in manifest]
    print(f"\nGenerated {len(manifest)} claim packets.")
    print(f"Page counts: min={min(pages)}, max={max(pages)}, avg={sum(pages)/len(pages):.1f}")
    print(f"Manifest written to {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
