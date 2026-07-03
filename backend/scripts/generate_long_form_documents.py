"""
scripts/generate_long_form_documents.py
----------------------------------------
Generates realistic, LONG (22-30 page) synthetic claim documents styled
after real-world insurance/adjuster paperwork -- dense tables, fax/scan
transmission banners, checkbox grids, running logs -- rather than the
sparse "Adjuster note #N" placeholder pages in
`samples/long_supplement_22pages.pdf`.

The visual language (fax banner across the top: date/time, fax number,
sender, page count; TO/FROM/SUBJECT block; boxed region/division-style
grids; dense bordered tables) is deliberately modeled on how real
1990s-2010s era faxed/scanned business documents look -- the same
"too clean" problem `generate_realistic_scans.py` addresses for single
page docs, but here for genuinely long multi-page packets, which is what
actually stresses the ingestion pipeline's page-count warnings, table-
extraction, and OCR-fallback paths in a way a 2-page sample can't.

Three long documents, one per LOB, each mapped to real gaps in the
existing sample data:

  auto/     claim_correspondence_log_25pages     -- 25pp adjuster call log +
             subrogation status + reserve worksheet, cycling templates
             (this is what a real claim file's "activity log" export
             looks like -- dozens of dated entries, not narrative prose).
  property/ inspection_report_28pages            -- 28pp room-by-room
             inspection with moisture readings, cause-of-loss checkbox
             grid, and a multi-page itemized contractor estimate.
  health/   itemized_billing_ledger_30pages       -- 30pp UB-04-style
             charge ledger (CPT/ICD/charge/allowed/paid rows) plus EOB
             summary pages -- real hospital bills for a multi-day
             admission run exactly this long.

Each document is produced in two forms:
  *_pXX.pdf            -- clean, digital text layer (fitz-drawn vector text)
  *_pXX_scanned.pdf     -- the SAME pages, rasterized and run through the
                           Augraphy pipeline (heavy tier, matching
                           generate_realistic_scans.py's settings) and
                           reassembled into one multi-page PDF with NO text
                           layer -- forces the OCR-fallback path across a
                           genuinely long document instead of a 1-page stub.

Finally, three new claim-folder scenarios are added under
samples/claim_folders/ (additive -- does not touch or delete the nine
folders generate_sample_claims.py builds):

  {lob}_long_document/   all mandatory docs for that LOB (reusing the
                          exact builder functions from
                          generate_sample_claims.py, so gate-check/triage
                          still see a complete, clean claim) PLUS the long
                          document nested under supplemental/, exercising
                          the "long multi-page PDF in a real folder
                          structure" case end to end.

Usage:
    python scripts/generate_long_form_documents.py

Idempotent for the files/folders it owns -- re-running overwrites its own
outputs but leaves everything else in samples/ untouched.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import fitz  # PyMuPDF
import numpy as np
from augraphy import (
    AugraphyPipeline,
    BadPhotoCopy,
    Folding,
    Geometric,
    InkBleed,
    Jpeg,
    LightingGradient,
    NoiseTexturize,
)
from PIL import Image

from core.config import SAMPLES_DIR
from scripts.generate_sample_claims import (
    build_auto_complete_clean,
    build_health_complete_clean,
    build_property_complete_clean,
)

LONG_FORM_DIR = SAMPLES_DIR / "long_form"
CLAIM_FOLDERS_DIR = SAMPLES_DIR / "claim_folders"

PAGE_W, PAGE_H = 612, 792  # US Letter, points
MARGIN = 36

# ---------------------------------------------------------------------------
# Low-level drawing helpers -- shared "look" across all three documents
# ---------------------------------------------------------------------------


def _fax_header(page: fitz.Page, *, timestamp: str, fax_number: str, sender: str, page_no: int) -> None:
    """Top-of-page transmission banner, e.g.:
    06/17/26 09:41   FAX 312 555 0148   MERIDIAN MUTUAL CLAIMS         [017]
    Mirrors the real fax-cover-sheet convention of stamping every
    transmitted page with timestamp / origin / running page counter."""
    y = 20
    page.insert_text((MARGIN, y), timestamp, fontsize=8, fontname="cour")
    page.insert_text((MARGIN + 90, y), f"FAX {fax_number}", fontsize=8, fontname="cour")
    page.insert_text((MARGIN + 230, y), sender, fontsize=8, fontname="cour")
    page.insert_text((PAGE_W - MARGIN - 30, y), f"[{page_no:03d}]", fontsize=8, fontname="cour")
    page.draw_line((MARGIN, y + 8), (PAGE_W - MARGIN, y + 8), width=0.75, color=(0, 0, 0))


def _to_from_subject(page: fitz.Page, *, to: str, frm: str, subject: str, y: int = 40) -> int:
    labels = [("TO:", to), ("FROM:", frm), ("SUBJECT:", subject)]
    for label, value in labels:
        page.insert_text((MARGIN, y), label, fontsize=9, fontname="cobo")
        page.insert_text((MARGIN + 70, y), value, fontsize=9, fontname="cour")
        y += 16
    page.draw_line((MARGIN, y + 2), (PAGE_W - MARGIN, y + 2), width=1.0, color=(0, 0, 0))
    return y + 16


def _section_banner(page: fitz.Page, text: str, y: int) -> int:
    """A shaded section-title bar, matching the blocked-out gray banners
    ("REGION:", "DISTRIBUTION") common on real internal report forms."""
    rect = fitz.Rect(MARGIN, y, PAGE_W - MARGIN, y + 16)
    page.draw_rect(rect, color=(0, 0, 0), fill=(0.85, 0.85, 0.85), width=0.5)
    page.insert_text((MARGIN + 4, y + 11), text, fontsize=9, fontname="cobo")
    return y + 24


def _table(
    page: fitz.Page,
    x: int,
    y: int,
    col_widths: list[int],
    headers: list[str],
    rows: list[list[str]],
    row_h: int = 14,
    font_size: int = 7.5,
) -> int:
    """Bordered grid table with a shaded header row -- the workhorse
    layout element of the reference document (account/volume grids)."""
    total_w = sum(col_widths)
    header_rect = fitz.Rect(x, y, x + total_w, y + row_h)
    page.draw_rect(header_rect, color=(0, 0, 0), fill=(0.8, 0.8, 0.8), width=0.5)
    cx = x
    for w, h in zip(col_widths, headers):
        page.insert_text((cx + 2, y + row_h - 4), h, fontsize=font_size, fontname="cobo")
        cx += w
    y += row_h

    for row in rows:
        row_rect = fitz.Rect(x, y, x + total_w, y + row_h)
        page.draw_rect(row_rect, color=(0, 0, 0), width=0.5)
        cx = x
        for w, val in zip(col_widths, row):
            page.insert_text((cx + 2, y + row_h - 4), str(val), fontsize=font_size, fontname="cour")
            cx += w
        # vertical rules
        cx = x
        for w in col_widths[:-1]:
            cx += w
            page.draw_line((cx, y), (cx, y + row_h), width=0.4, color=(0, 0, 0))
        y += row_h
    return y


def _checkbox_grid(page: fitz.Page, x: int, y: int, items: list[str], checked: set[str], cols: int = 2) -> int:
    """A row of bracketed checkboxes, e.g. '[X] Wind  [ ] Fire  [ ] Water'."""
    col_w = (PAGE_W - 2 * MARGIN) // cols
    for i, item in enumerate(items):
        row, col = divmod(i, cols)
        cx = x + col * col_w
        cy = y + row * 14
        mark = "X" if item in checked else " "
        page.insert_text((cx, cy), f"[{mark}] {item}", fontsize=8, fontname="cour")
    rows_used = (len(items) + cols - 1) // cols
    return y + rows_used * 14 + 6


def _footer(page: fitz.Page, page_no: int, total_pages: int, doc_ref: str) -> None:
    y = PAGE_H - 24
    page.draw_line((MARGIN, y - 6), (PAGE_W - MARGIN, y - 6), width=0.5, color=(0, 0, 0))
    page.insert_text((MARGIN, y), doc_ref, fontsize=7, fontname="cour")
    page.insert_text((PAGE_W - MARGIN - 80, y), f"Page {page_no} of {total_pages}", fontsize=7, fontname="cour")


# ---------------------------------------------------------------------------
# AUTO: 25-page claim correspondence log + subrogation status + reserve log
# ---------------------------------------------------------------------------


def build_auto_long_document(path: Path, n_pages: int = 25) -> None:
    doc = fitz.open()
    policy = "AUTO-7734-9021"
    claimant = "Maria Gonzalez"
    claim_no = "CLM-2026-30114"
    contacts = ["Maria Gonzalez (Insured)", "Thomas Reid (Other Party)", "Patrick Uyeda (Witness)",
                "Springfield Auto Body (Repair Shop)", "Reid's Carrier - Adjuster Lin Park"]
    methods = ["Phone", "Email", "Voicemail", "Portal Upload", "Fax"]
    day = 14

    for p in range(1, n_pages + 1):
        page = doc.new_page(width=PAGE_W, height=PAGE_H)
        month, dd = (3, day) if day <= 31 else (4, day - 31)
        timestamp = f"{month:02d}/{dd:02d}/26 {9 + (p % 8):02d}:{(p * 7) % 60:02d}"
        _fax_header(page, timestamp=timestamp, fax_number="312 555 0148",
                    sender="MERIDIAN MUTUAL CLAIMS DEPT", page_no=p)
        y = _to_from_subject(
            page,
            to="Claim File",
            frm=f"Adjuster D. Whitfield, Ext. 4471",
            subject=f"Claim {claim_no} - Policy {policy} - Activity Log & Reserve Worksheet",
            y=42,
        )

        if p == 1:
            y = _section_banner(page, "CLAIM SUMMARY", y)
            y = _table(
                page, MARGIN, y, [140, 300],
                ["FIELD", "VALUE"],
                [
                    ["Policy Number", policy],
                    ["Claimant", claimant],
                    ["Date of Loss", "03/14/2026"],
                    ["Loss Location", "5th Ave & Cedar St, Springfield, IL"],
                    ["Vehicle", "2023 Honda Accord, VIN 1HGCM82633A004352"],
                    ["Initial Reserve", "$4,500.00"],
                ],
                row_h=16,
            )
            y += 10

        y = _section_banner(page, f"ADJUSTER ACTIVITY LOG - ENTRIES {((p - 1) * 6) + 1}-{p * 6}", y)
        rows = []
        for i in range(6):
            idx = (p - 1) * 6 + i
            contact = contacts[idx % len(contacts)]
            method = methods[idx % len(methods)]
            note = [
                "Left voicemail requesting updated repair timeline.",
                "Confirmed rental vehicle extension through end of repairs.",
                "Received signed liability statement from witness.",
                "Reviewed uploaded repair shop supplement invoice.",
                "Followed up with other carrier re: liability acceptance.",
                "No answer, retrying contact tomorrow AM.",
            ][idx % 6]
            rows.append([f"03/{14 + (idx // 4):02d}/26", f"{9 + (idx % 8):02d}:{(idx * 11) % 60:02d}",
                         contact[:24], method, note[:34]])
        y = _table(page, MARGIN, y, [45, 40, 130, 65, 160],
                   ["DATE", "TIME", "CONTACT", "METHOD", "NOTE"], rows, row_h=13, font_size=6.8)
        y += 10

        if p % 4 == 0:
            y = _section_banner(page, "SUBROGATION / REPAIR NETWORK STATUS", y)
            shop_rows = [
                ["Springfield Auto Body", "IN PROGRESS", "6"],
                ["North Shore Collision", "COMPLETE", "0"],
                ["Cedar St. Body Works", "AWAITING PARTS", "3"],
                ["Lakeview Auto Repair", "PENDING ESTIMATE", "9"],
            ]
            y = _table(page, MARGIN, y, [180, 130, 90],
                       ["REPAIR SHOP", "STATUS", "VEHICLES IN QUEUE"], shop_rows, row_h=14)
            y += 10
            y = _section_banner(page, "LOSS CAUSE VERIFICATION", y)
            y = _checkbox_grid(
                page, MARGIN, y,
                ["Rear-End Collision", "Weather-Related", "Theft", "Vandalism", "Single Vehicle", "Hit and Run"],
                checked={"Rear-End Collision"}, cols=2,
            )

        if p % 6 == 0:
            y = _section_banner(page, "RESERVE WORKSHEET", y)
            reserve_rows = [
                ["Bodily Injury", "$0.00", "$0.00"],
                ["Property Damage", "$4,250.00", "$4,250.00"],
                ["Rental Reimbursement", "$650.00", "$480.00"],
                ["Subrogation Recovery (est.)", "-$2,125.00", "$0.00"],
            ]
            y = _table(page, MARGIN, y, [220, 90, 90],
                       ["RESERVE CATEGORY", "SET", "PAID TO DATE"], reserve_rows, row_h=14)

        _footer(page, p, n_pages, f"{claim_no} / Activity Log")
        day += 1

    doc.save(str(path))
    doc.close()


# ---------------------------------------------------------------------------
# PROPERTY: 28-page room-by-room inspection + itemized contractor estimate
# ---------------------------------------------------------------------------


def build_property_long_document(path: Path, n_pages: int = 28) -> None:
    doc = fitz.open()
    policy = "PROP-2026-88231"
    claimant = "James Okafor"
    claim_no = "CLM-2026-41207"
    rooms = ["Living Room", "Kitchen", "Primary Bedroom", "Bedroom 2", "Bathroom", "Basement -- Utility",
             "Basement -- Storage", "Attic", "Garage", "Exterior -- Roof", "Exterior -- Siding", "Crawl Space"]
    damage_types = ["Water intrusion", "Drywall staining", "Mold growth (visible)", "Flooring buckling",
                    "Insulation saturation", "Structural warping", "Ceiling sag", "Electrical exposure risk"]

    for p in range(1, n_pages + 1):
        page = doc.new_page(width=PAGE_W, height=PAGE_H)
        timestamp = f"06/{10 + (p % 18):02d}/26 {8 + (p % 9):02d}:{(p * 13) % 60:02d}"
        _fax_header(page, timestamp=timestamp, fax_number="847 555 2210",
                    sender="RIVERTON RESTORATION & INSPECTION CO", page_no=p)
        y = _to_from_subject(
            page,
            to="Claims Adjuster - Meridian Mutual",
            frm="Field Inspector K. Alders, Lic. #IL-4471",
            subject=f"Claim {claim_no} - Policy {policy} - Property Loss Inspection Report",
            y=42,
        )

        if p == 1:
            y = _section_banner(page, "PROPERTY & LOSS SUMMARY", y)
            y = _table(
                page, MARGIN, y, [140, 300],
                ["FIELD", "VALUE"],
                [
                    ["Policy Number", policy],
                    ["Insured", claimant],
                    ["Property Address", "142 Birchwood Lane, Riverton"],
                    ["Date of Loss", "06/10/2026"],
                    ["Cause of Loss", "Wind-driven rain / roof penetration"],
                    ["Probable Total Loss", "$41,850.00"],
                ],
                row_h=16,
            )
            y += 8
            y = _section_banner(page, "CAUSE OF LOSS VERIFICATION", y)
            y = _checkbox_grid(
                page, MARGIN, y,
                ["Wind", "Hail", "Fire", "Water - Plumbing", "Water - Weather", "Theft", "Vandalism", "Other"],
                checked={"Wind", "Water - Weather"}, cols=2,
            )
            y += 6

        room = rooms[(p - 1) % len(rooms)]
        y = _section_banner(page, f"ROOM INSPECTION -- {room.upper()}", y)
        moisture = 18 + ((p * 7) % 40)
        y = _table(
            page, MARGIN, y, [140, 300],
            ["FIELD", "READING"],
            [
                ["Room / Area", room],
                ["Moisture Reading", f"{moisture}%"],
                ["Damage Type", damage_types[(p - 1) % len(damage_types)]],
                ["Photo Reference", f"IMG-{2000 + p}.jpg through IMG-{2000 + p + 2}.jpg"],
                ["Recommended Action", "Remove and replace affected material; dry out and monitor 72 hrs."],
            ],
            row_h=15,
        )
        y += 10

        if p >= 3:
            y = _section_banner(page, "ITEMIZED CONTRACTOR ESTIMATE -- CONTINUED", y)
            line_items = [
                ["Drywall removal & replacement", "45 sq ft", "$6.20", f"${45 * 6.2:,.2f}"],
                ["Insulation replacement", "60 sq ft", "$2.85", f"${60 * 2.85:,.2f}"],
                ["Flooring - subfloor repair", "30 sq ft", "$9.10", f"${30 * 9.1:,.2f}"],
                ["Mold remediation labor", "4 hrs", "$85.00", "$340.00"],
                ["Dehumidifier rental (per day)", "3 days", "$45.00", "$135.00"],
                ["Paint & finish", "45 sq ft", "$1.75", f"${45 * 1.75:,.2f}"],
            ]
            y = _table(page, MARGIN, y, [220, 60, 60, 80],
                       ["LINE ITEM", "QTY", "UNIT COST", "TOTAL"], line_items, row_h=14, font_size=7)

        _footer(page, p, n_pages, f"{claim_no} / Inspection Report")

    doc.save(str(path))
    doc.close()


# ---------------------------------------------------------------------------
# HEALTH: 30-page UB-04-style itemized billing ledger + EOB detail
# ---------------------------------------------------------------------------


def build_health_long_document(path: Path, n_pages: int = 30) -> None:
    doc = fitz.open()
    patient = "Renee Ashworth"
    member_id = "HLX-1180-4423"
    claim_no = "CLM-2026-55902"
    cpt_pool = [
        ("99223", "Initial hospital care, high complexity", 640.00),
        ("44970", "Laparoscopic appendectomy", 4820.00),
        ("00840", "Anesthesia, intraperitoneal procedures", 1120.00),
        ("85025", "Complete blood count w/ differential", 42.00),
        ("80053", "Comprehensive metabolic panel", 58.00),
        ("71046", "Chest X-ray, 2 views", 96.00),
        ("36415", "Venipuncture", 12.00),
        ("99232", "Subsequent hospital care", 165.00),
        ("J1170", "Hydromorphone injection", 24.00),
        ("99283", "Emergency dept visit, moderate complexity", 480.00),
    ]

    for p in range(1, n_pages + 1):
        page = doc.new_page(width=PAGE_W, height=PAGE_H)
        timestamp = f"07/{11 + (p % 15):02d}/26 {7 + (p % 10):02d}:{(p * 17) % 60:02d}"
        _fax_header(page, timestamp=timestamp, fax_number="630 555 7719",
                    sender="NORTHGATE SURGICAL CENTER BILLING", page_no=p)
        y = _to_from_subject(
            page,
            to="Healthlex Insurance - Claims Processing",
            frm="Northgate Surgical Center, Patient Financial Services",
            subject=f"Claim {claim_no} - Member {member_id} - Itemized Billing Ledger",
            y=42,
        )

        if p == 1:
            y = _section_banner(page, "PATIENT & CLAIM SUMMARY", y)
            y = _table(
                page, MARGIN, y, [140, 300],
                ["FIELD", "VALUE"],
                [
                    ["Patient Name", patient],
                    ["Member ID", member_id],
                    ["Admission Date", "07/11/2026"],
                    ["Discharge Date", "07/12/2026"],
                    ["Primary Diagnosis (ICD-10)", "K35.80 - Unspecified acute appendicitis"],
                    ["Total Billed Amount", "$22,875.00"],
                ],
                row_h=16,
            )
            y += 8
            y = _section_banner(page, "COVERAGE TYPE VERIFICATION", y)
            y = _checkbox_grid(
                page, MARGIN, y,
                ["In-Network", "Out-of-Network", "Emergency", "Elective", "Inpatient", "Outpatient"],
                checked={"In-Network", "Inpatient"}, cols=2,
            )
            y += 6

        y = _section_banner(page, f"CHARGE LINE ITEMS -- PAGE {p}", y)
        rows = []
        for i in range(9):
            idx = (p - 1) * 9 + i
            code, desc, base = cpt_pool[idx % len(cpt_pool)]
            billed = base + (idx % 5) * 3.5
            allowed = billed * 0.63
            paid = allowed * 0.9
            rows.append([code, desc[:30], f"${billed:,.2f}", f"${allowed:,.2f}", f"${paid:,.2f}"])
        y = _table(page, MARGIN, y, [45, 190, 65, 65, 65],
                   ["CPT", "DESCRIPTION", "BILLED", "ALLOWED", "PAID"], rows, row_h=13, font_size=6.8)
        y += 10

        if p % 5 == 0:
            y = _section_banner(page, "EXPLANATION OF BENEFITS (EOB) SUMMARY", y)
            eob_rows = [
                ["Total Billed to Date", f"${(p * 700):,.2f}"],
                ["Total Allowed to Date", f"${(p * 700 * 0.63):,.2f}"],
                ["Total Paid to Date", f"${(p * 700 * 0.63 * 0.9):,.2f}"],
                ["Patient Responsibility to Date", f"${(p * 700 * 0.63 * 0.1):,.2f}"],
            ]
            y = _table(page, MARGIN, y, [260, 120], ["CATEGORY", "AMOUNT"], eob_rows, row_h=14)

        _footer(page, p, n_pages, f"{claim_no} / Billing Ledger")

    doc.save(str(path))
    doc.close()


# ---------------------------------------------------------------------------
# Scan degradation -- reassemble degraded pages into ONE multi-page PDF
# ---------------------------------------------------------------------------


def _heavy_pipeline() -> AugraphyPipeline:
    """A believable "office scanner/fax copy" look -- visible paper
    texture, mild ink bleed, slight skew, some lighting unevenness --
    without going so far the text becomes unreadable. NOTE: BadPhotoCopy
    is intentionally NOT used here -- its worley-noise generator hits an
    environment-dependent numba/numpy compiler bug (unrelated to this
    script's own logic) on some setups. If your environment doesn't hit
    that and you want a rougher look, add
    BadPhotoCopy(noise_iteration=(1, 2), p=0.3) back into post_phase."""
    return AugraphyPipeline(
        ink_phase=[InkBleed(intensity_range=(0.1, 0.2), severity=(0.1, 0.15), p=0.5)],
        paper_phase=[
            Folding(fold_count=1, fold_noise=0.02, p=0.25),
            LightingGradient(p=0.35),
        ],
        post_phase=[
            Geometric(rotate_range=(-2, 2), p=1),
            NoiseTexturize(sigma_range=(2, 4), p=0.6),
            Jpeg(quality_range=(55, 75), p=1),
        ],
    )


def make_scanned_companion(src_pdf: Path, out_pdf: Path, zoom: float = 1.6) -> None:
    """Rasterizes every page of src_pdf, runs each through the (toned-down)
    heavy Augraphy pipeline, and reassembles the degraded images into a
    single multi-page PDF with no text layer -- forcing full OCR across a
    genuinely long document, while staying human-legible.

    Saved as JPEG (not PNG) before re-embedding: the noise-texture and
    ink-bleed effects are high-entropy and compress terribly under
    lossless PNG (a 25-30 page doc balloons to 100MB+), whereas a real
    faxed/scanned document is itself lossy to begin with -- JPEG at
    moderate-high quality is both realistic and keeps file size sane."""
    pipeline = _heavy_pipeline()
    src = fitz.open(str(src_pdf))
    out = fitz.open()
    for page in src:
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        arr = np.array(img)
        degraded = pipeline(arr.copy())
        deg_img = Image.fromarray(degraded)
        buf = io.BytesIO()
        deg_img.save(buf, format="JPEG", quality=78, optimize=True)
        new_page = out.new_page(width=deg_img.width * 72 / (96 * zoom), height=deg_img.height * 72 / (96 * zoom))
        new_page.insert_image(new_page.rect, stream=buf.getvalue())
    out.save(str(out_pdf), garbage=4, deflate=True)
    out.close()
    src.close()


# ---------------------------------------------------------------------------
# Claim-folder assembly (additive -- doesn't touch the existing 9 folders)
# ---------------------------------------------------------------------------


def _assemble_long_document_folder(lob_folder_name: str, mandatory_builder, long_pdf: Path, scanned_pdf: Path) -> Path:
    root = CLAIM_FOLDERS_DIR / lob_folder_name
    if root.exists():
        import shutil
        shutil.rmtree(root)
    mandatory_builder(root)  # reuses the exact *_complete_clean() builder -> all mandatory docs present
    supplemental = root / "supplemental"
    supplemental.mkdir(parents=True, exist_ok=True)
    import shutil as _sh
    _sh.copy(long_pdf, supplemental / long_pdf.name)
    _sh.copy(scanned_pdf, supplemental / scanned_pdf.name)
    return root


def _update_readme(new_rows: list[tuple[str, str, str]]) -> None:
    readme = CLAIM_FOLDERS_DIR / "README.md"
    marker = "\n<!-- long-form-scenarios -->\n"
    base = readme.read_text() if readme.exists() else ""
    base = base.split(marker)[0].rstrip() + "\n"
    extra_lines = [
        marker.strip(),
        "",
        "Three additional folders (added by `scripts/generate_long_form_documents.py`) "
        "cover the manager's \"20-30 page realistic document\" requirement specifically -- "
        "each bundles a complete, clean claim (reusing the same mandatory-doc builders "
        "above) plus a long (22-30pp), densely-tabulated supplemental document under "
        "`supplemental/`, in both a clean digital-text version and an Augraphy-degraded, "
        "no-text-layer \"scanned\" version (heavy tier: folding, ink bleed, lighting "
        "gradient, bad-photocopy noise, low-quality JPEG) to exercise the OCR-fallback "
        "path across a genuinely long document.\n",
        "| Folder | LOB | Supplemental document |",
        "|---|---|---|",
    ]
    for folder, lob, desc in new_rows:
        extra_lines.append(f"| `{folder}/` | {lob} | {desc} |")
    text = base + "\n".join(extra_lines) + "\n"
    readme.write_text(text)


def main() -> None:
    LONG_FORM_DIR.mkdir(parents=True, exist_ok=True)

    print("Building long-form clean PDFs...")
    auto_pdf = LONG_FORM_DIR / "auto_claim_correspondence_log_25pages.pdf"
    property_pdf = LONG_FORM_DIR / "property_inspection_report_28pages.pdf"
    health_pdf = LONG_FORM_DIR / "health_itemized_billing_ledger_30pages.pdf"
    build_auto_long_document(auto_pdf, n_pages=25)
    build_property_long_document(property_pdf, n_pages=28)
    build_health_long_document(health_pdf, n_pages=30)
    for f in (auto_pdf, property_pdf, health_pdf):
        print(f"  wrote {f.relative_to(PROJECT_ROOT)}")

    print("Degrading to scanned companions via Augraphy (heavy tier)...")
    auto_scanned = LONG_FORM_DIR / "auto_claim_correspondence_log_25pages_scanned.pdf"
    property_scanned = LONG_FORM_DIR / "property_inspection_report_28pages_scanned.pdf"
    health_scanned = LONG_FORM_DIR / "health_itemized_billing_ledger_30pages_scanned.pdf"
    make_scanned_companion(auto_pdf, auto_scanned)
    make_scanned_companion(property_pdf, property_scanned)
    make_scanned_companion(health_pdf, health_scanned)
    for f in (auto_scanned, property_scanned, health_scanned):
        print(f"  wrote {f.relative_to(PROJECT_ROOT)}")

    print("Assembling long-document claim folders...")
    rows = []
    root = _assemble_long_document_folder("auto_long_document", build_auto_complete_clean, auto_pdf, auto_scanned)
    print(f"  built {root.relative_to(PROJECT_ROOT)}")
    rows.append(("auto_long_document", "Auto", "25pp adjuster activity log / subrogation status / reserve worksheet"))

    root = _assemble_long_document_folder("property_long_document", build_property_complete_clean, property_pdf, property_scanned)
    print(f"  built {root.relative_to(PROJECT_ROOT)}")
    rows.append(("property_long_document", "Property", "28pp room-by-room inspection + itemized contractor estimate"))

    root = _assemble_long_document_folder("health_long_document", build_health_complete_clean, health_pdf, health_scanned)
    print(f"  built {root.relative_to(PROJECT_ROOT)}")
    rows.append(("health_long_document", "Health", "30pp UB-04-style itemized billing ledger + EOB summaries"))

    _update_readme(rows)
    print(f"  updated {(CLAIM_FOLDERS_DIR / 'README.md').relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()