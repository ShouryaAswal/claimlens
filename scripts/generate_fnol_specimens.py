"""
scripts/generate_fnol_specimens.py
--------------------------------------
Recreates the field structure of REAL, currently-in-use government insurance
claim forms as test PDFs -- not invented mockups. The field labels, section
structure, and certification language below are reproduced from the actual
live forms (verified via direct fetch on 2026-06-21):

  - FEMA Form 086-0-09, "Proof of Loss" (National Flood Insurance Program)
    https://www.fema.gov/sites/default/files/2020-07/FEMA-Form_086-0-09_proof-of-loss.pdf
    U.S. federal government work -> public domain (17 U.S.C. SS105).

  - NY DMV Form MV-104, "Report of Motor Vehicle Crash"
    https://dmv.ny.gov/forms/mv104.pdf
    New York State government form, distributed for public use in filing
    required crash reports.

  - Massachusetts Motor Vehicle Crash Operator Report
    https://www.mass.gov/doc/motor-vehicle-crash-operator-report/download
    Massachusetts state government form, distributed for public use.

We do NOT redistribute the original PDF files themselves (we couldn't fetch
their raw bytes through this environment's tooling anyway -- see
REAL_DATA_SOURCES.md for exactly what was and wasn't retrievable). What's
reproduced here is the authentic field/section structure as plain text,
laid out fresh -- not a scan or copy of the original page images, fonts, or
graphic design.

Run: python3 scripts/generate_fnol_specimens.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import fitz  # PyMuPDF

from core.config import SAMPLES_DIR

OUT_DIR = SAMPLES_DIR / "real_world" / "fnol_specimens"


def _write_page(page: fitz.Page, lines: list[str], start_y: int = 40, line_h: int = 15) -> None:
    y = start_y
    for line in lines:
        size = 13 if line.isupper() and len(line) < 60 else 10
        page.insert_text((45, y), line, fontsize=size)
        y += line_h if size == 10 else line_h + 4


def make_fema_proof_of_loss(path: Path) -> None:
    """Field structure reproduced from FEMA Form 086-0-09 (public domain
    U.S. federal government work)."""
    doc = fitz.open()
    page = doc.new_page()
    _write_page(page, [
        "DEPARTMENT OF HOMELAND SECURITY",
        "Federal Emergency Management Agency",
        "OMB Control Number: 1660-0005",
        "",
        "PROOF OF LOSS",
        "Filing:  [ ] Initial   [ ] Additional",
        "",
        "Name(s) of Insured: Marcus Webb",
        "Policy Number: NFIP-2026-771042",
        "Date & Time of Loss: 2026-06-10 / Late afternoon",
        "",
        "Address of Insured Property: 142 Birchwood Lane",
        "City: Riverton   State: -   ZIP: -",
        "",
        "Is there a mortgage interest or additional interest in the property: [X] No  [ ] Yes",
        "",
        "Mailing Address: 142 Birchwood Lane, Riverton",
        "Best Contact Number: (555) 019-2231",
        "E-mail Address: m.webb@example-mail.test",
        "",
        "Occupancy: [X] Owner Occupied  [ ] Tenant Occupied",
        "Occupancy Type: [X] Single Family  [ ] 2-4 Family  [ ] Other Residential",
        "",
        "Description of flood causing loss (source of flood waters i.e. river, lake, or ocean/gulf):",
        "Heavy rainfall caused the adjacent creek to overflow into the crawl space and",
        "first-floor utility room over a 6 hour period.",
        "",
        "Other Insurance that may cover any of this loss: [X] None",
        "",
        "                              Building Coverage    Contents Coverage",
        "Amount of coverage at time of loss:        $250,000.00          $60,000.00",
        "Replacement Cost Value (RCV):               $19,800.00           $3,200.00",
        "Actual Cash Value (ACV) of Repairs:         $16,500.00           $2,100.00",
        "Subtract Deductible:                         $1,250.00             $500.00",
        "NET AMOUNT CLAIMED:                         $15,250.00           $1,600.00",
        "",
        "I have attached specifications of damaged buildings and detailed repair estimates.",
        "If claiming damage to contents, I have attached a detailed inventory of damaged",
        "personal property.",
        "",
        "I declare under penalty of perjury under the laws of the United States of America",
        "that the foregoing is true and correct.",
        "",
        "Signature of Insured: ___________________   Date: 2026-06-14",
        "",
        "FEMA FORM 086-0-09 (04/17)                                    Page 1 of 2",
    ])
    doc.save(str(path))
    doc.close()


def make_ny_dmv_mv104(path: Path) -> None:
    """Field structure reproduced from NY DMV Form MV-104, "Report of Motor
    Vehicle Crash" (New York State government form, public crash-reporting
    form)."""
    doc = fitz.open()
    page = doc.new_page()
    _write_page(page, [
        "STATE OF NEW YORK DEPARTMENT OF MOTOR VEHICLES",
        "MV-104: REPORT OF MOTOR VEHICLE CRASH",
        "Use only for crashes that happen in New York State. Print or type. Use black ink.",
        "",
        "Date of Crash: 2026-06-12   Time: 5:45 PM",
        "County: -   Locality: Springfield",
        "",
        "Check box if crash exceeds $1,000 threshold for property damage: [X]",
        "Crash Diagram Code: 2",
        "",
        "PART A -- DRIVER / REGISTRANT (Unit 1)",
        "Driver Name (as on license): Priya Nair",
        "Driver License Number: D1234567   State of License: NY",
        "Registrant Name: Priya Nair",
        "State of Reg.: NY   Vehicle Year/Make: 2022 Honda",
        "",
        "PART B -- DRIVER / REGISTRANT (Unit 2)",
        "Driver Name (as on license): Marcus Webb",
        "Driver License Number: D9981203   State of License: NY",
        "Registrant Name: Marcus Webb",
        "State of Reg.: NY   Vehicle Year/Make: 2019 Ford",
        "",
        "Briefly describe how the crash happened:",
        "Unit 1 was stopped at a red light when struck from behind by Unit 2.",
        "",
        "Injuries: [ ] K-Fatal [ ] A-Severe [X] B-Minor lacerations/abrasions [ ] N-Not Injured",
        "",
        "THIS FORM MUST BE SIGNED BY THE DRIVER OR REPRESENTATIVE.",
        "Signature: ___________________   Date: 2026-06-12",
        "",
        "Send original to: CRASH RECORDS CENTER, 6 EMPIRE STATE PLAZA, ALBANY, NY 12220-0925",
    ])
    doc.save(str(path))
    doc.close()


def make_ma_crash_operator_report(path: Path) -> None:
    """Field structure reproduced from the Massachusetts Motor Vehicle Crash
    Operator Report (Commonwealth of Massachusetts government form)."""
    doc = fitz.open()
    page = doc.new_page()
    _write_page(page, [
        "COMMONWEALTH OF MASSACHUSETTS",
        "MOTOR VEHICLE CRASH OPERATOR REPORT",
        "",
        "B3. Driver's License Number: S4471829   B4. License State: MA",
        "B11. Your Full Name (Last, First, Middle): Cho, Aaliyah, R",
        "B13. Insurance Company: Meridian Mutual Insurance",
        "B14. Vehicle Registration #: 7TX-2291   B16. Reg. State: MA",
        "B17. Vehicle Year: 2021   B18. Vehicle Make: Toyota",
        "B22. What Was Your Vehicle Doing Prior to the Crash?: Parked, unoccupied",
        "B24. Was your vehicle towed?: No",
        "B25. Vehicle Damaged Area: Rear quarter panel",
        "",
        "H. Witness Information",
        "H1. Witness Name (Last, First, Middle): Okafor, Daniel, T",
        "H2. Street Address: 88 Maple Court, Springfield",
        "",
        "I. Property Damage Information (Other than Vehicles)",
        "I1. Owner Name: -",
        "I4. Property and Damage Description: None reported",
        "",
        "J. Description of What Happened:",
        "Reporting party's parked vehicle was struck by a passing vehicle that did not",
        "stop; damage limited to rear quarter panel and tail light assembly.",
        "",
        "Signature: ___________________   Date: 2026-06-12",
    ])
    doc.save(str(path))
    doc.close()


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    make_fema_proof_of_loss(OUT_DIR / "fema_proof_of_loss_specimen.pdf")
    make_ny_dmv_mv104(OUT_DIR / "ny_dmv_mv104_specimen.pdf")
    make_ma_crash_operator_report(OUT_DIR / "ma_crash_operator_report_specimen.pdf")
    print(f"Generated FNOL specimens in: {OUT_DIR}")
    for f in sorted(OUT_DIR.iterdir()):
        print(f"  - {f.name}")


if __name__ == "__main__":
    main()
