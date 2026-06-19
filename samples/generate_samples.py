"""
Generates synthetic sample claim documents for Sprint 0/1 testing.

These are NOT meant to be realistic forms -- they're simple, clearly
labelled "key: value" documents that exercise the OCR + extraction
pipeline without needing any real (and sensitive) claim data.

Run: python3 samples/generate_samples.py
"""

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

OUT_DIR = "samples"


def draw_kv_doc(path: str, title: str, lines: list[str], pages: list[list[str]] | None = None):
    """Draws a simple top-to-bottom 'Label: Value' document.

    Each line becomes its own text draw call so the resulting PDF has
    one clean text run per fact -- this mirrors how a real OCR engine
    would emit one block per detected text line.
    """
    c = canvas.Canvas(path, pagesize=letter)
    width, height = letter

    def render_page(page_lines):
        y = height - 72
        c.setFont("Helvetica-Bold", 14)
        c.drawString(72, y, title)
        y -= 28
        c.setFont("Helvetica", 11)
        for line in page_lines:
            c.drawString(72, y, line)
            y -= 20
        c.showPage()

    if pages is None:
        render_page(lines)
    else:
        for page_lines in pages:
            render_page(page_lines)

    c.save()


def main():
    # --- Auto claim: 2 pages (declaration page + police report) ---
    draw_kv_doc(
        f"{OUT_DIR}/auto_claim_01.pdf",
        "Auto Insurance Claim - Policy Declaration",
        [],
        pages=[
            [
                "Policy Number: AUTO-2026-00981",
                "Claimant Name: Priya Nair",
                "Vehicle: 2022 Honda City",
                "VIN: 1HGCM82633A004352",
                "Coverage: Collision / Comprehensive",
            ],
            [
                "Police Report",
                "Loss Date: 2026-03-15",
                "Location: MG Road, Bengaluru",
                "Description: Rear-end collision at signal",
                "Estimated Repair Amount: USD 3200",
            ],
        ],
    )

    # --- Property claim: 2 pages (FNOL + inspection report) ---
    draw_kv_doc(
        f"{OUT_DIR}/property_claim_01.pdf",
        "Property Insurance Claim - First Notice of Loss",
        [],
        pages=[
            [
                "Policy Number: PROP-2026-04471",
                "Policyholder Name: Arjun Mehta",
                "Property Address: 14 Lakeview Apartments, Pune",
                "Loss Date: 2026-04-02",
                "Cause of Loss: Water damage from burst pipe",
            ],
            [
                "Inspection Report",
                "Inspector: R. Kulkarni",
                "Damaged Rooms: Kitchen, Hallway",
                "Replacement Cost Value (RCV): USD 8750",
                "Actual Cash Value (ACV): USD 7100",
            ],
        ],
    )

    # --- Health claim: 2 pages (pre-auth + itemised bill) ---
    draw_kv_doc(
        f"{OUT_DIR}/health_claim_01.pdf",
        "Health Insurance Claim - Pre-Authorization",
        [],
        pages=[
            [
                "Member ID: HLTH-2026-77210",
                "Patient Name: Sanya Kapoor",
                "Provider Name: Fortis Hospital",
                "Admission Date: 2026-05-10",
                "Diagnosis: Acute appendicitis",
            ],
            [
                "Itemised Bill",
                "Room Charges: USD 1200",
                "Surgery Charges: USD 4800",
                "Pharmacy: USD 350",
                "Total Billed Amount: USD 6350",
            ],
        ],
    )

    print("Generated 3 sample claim PDFs in samples/")


if __name__ == "__main__":
    main()
