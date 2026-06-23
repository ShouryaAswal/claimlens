"""
tests/test_directory_discovery.py
-------------------------------------
Tests for discover_files()/ingest_claim_folder() -- the part of this round's
work that lets the pipeline handle a realistic nested claim folder (the
manager's "robust ingestion pipeline" requirement) rather than only a flat
list of file paths.
"""

from __future__ import annotations

from agents.ingestion.dispatcher import discover_files, ingest, ingest_claim_folder
from core.schemas import SourceFormat


def _make_claim_folder(tmp_path):
    import fitz
    from PIL import Image, ImageDraw

    claim_dir = tmp_path / "CLM-TEST-001"
    fnol_dir = claim_dir / "fnol"
    evidence_dir = claim_dir / "evidence"
    correspondence_dir = claim_dir / "correspondence"
    for d in (fnol_dir, evidence_dir, correspondence_dir):
        d.mkdir(parents=True)

    # FNOL PDF
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Policy Number: TEST-001", fontsize=12)
    doc.save(str(fnol_dir / "notice_of_loss.pdf"))
    doc.close()

    # Evidence photo
    img = Image.new("RGB", (300, 100), "white")
    ImageDraw.Draw(img).text((10, 10), "Damage photo", fill="black")
    img.save(evidence_dir / "photo1.png")

    # Correspondence HTML
    (correspondence_dir / "note.html").write_text(
        "<html><body><p>Adjuster note: pending review.</p></body></html>",
        encoding="utf-8",
    )

    # A file type we don't support, to prove it's silently skipped not crashed on
    (claim_dir / "readme.txt").write_text("not a supported format", encoding="utf-8")

    # A link manifest
    (claim_dir / "claim_links.txt").write_text(
        "# comment line, should be ignored\n"
        "not_a_url_should_warn_not_crash\n",
        encoding="utf-8",
    )

    return claim_dir


def test_discover_files_walks_nested_subdirectories(tmp_path):
    claim_dir = _make_claim_folder(tmp_path)
    found = discover_files(str(claim_dir))

    found_names = {p.split("/")[-1] for p in found}
    assert "notice_of_loss.pdf" in found_names
    assert "photo1.png" in found_names
    assert "note.html" in found_names
    assert "readme.txt" not in found_names          # unsupported extension, skipped
    assert "claim_links.txt" not in found_names      # manifest consumed, not returned as a file itself


def test_discover_files_reads_link_manifest_for_valid_urls(tmp_path):
    claim_dir = tmp_path / "CLM-TEST-002"
    claim_dir.mkdir()
    (claim_dir / "claim_links.txt").write_text(
        "# a real link to the portal\n"
        "https://example-claims-portal.test/doc1.pdf\n"
        "http://example-claims-portal.test/doc2.pdf\n"
        "ftp://not-supported.test/doc3.pdf\n",   # not http(s) -- should be ignored, not crash
        encoding="utf-8",
    )
    found = discover_files(str(claim_dir))
    assert "https://example-claims-portal.test/doc1.pdf" in found
    assert "http://example-claims-portal.test/doc2.pdf" in found
    assert not any("ftp://" in f for f in found)


def test_discover_files_missing_directory_raises(tmp_path):
    import pytest
    with pytest.raises(FileNotFoundError):
        discover_files(str(tmp_path / "does_not_exist"))


def test_ingest_claim_folder_processes_everything_found(tmp_path):
    claim_dir = _make_claim_folder(tmp_path)
    records = ingest_claim_folder(str(claim_dir))

    # 3 real files (pdf, png, html) -- the unsupported .txt and the
    # manifest itself are not separate DocumentRecords.
    assert len(records) == 3
    formats = {r.source_format for r in records}
    assert formats == {SourceFormat.PDF, SourceFormat.IMAGE, SourceFormat.HTML}

    pdf_record = next(r for r in records if r.source_format == SourceFormat.PDF)
    assert "TEST-001" in pdf_record.full_text


def test_local_html_file_ingestion(tmp_path):
    html_path = tmp_path / "saved_email.html"
    html_path.write_text(
        "<html><body>"
        "<h1>Re: Claim Update</h1>"
        "<p>Policy Number: AUTO-2026-00981</p>"
        "<script>tracking_pixel();</script>"
        "</body></html>",
        encoding="utf-8",
    )
    record = ingest(str(html_path))
    assert record.source_format == SourceFormat.HTML
    assert record.page_count is None
    assert "AUTO-2026-00981" in record.full_text
    assert "tracking_pixel" not in record.full_text


def test_block_ids_are_globally_unique_across_multiple_images_in_one_claim(tmp_path):
    """Regression test for a real bug caught while building Sprint 3:
    image_parser numbers blocks 'img_b001', 'img_b002', ... starting from 1
    for EVERY image independently. Two images in the same claim folder
    therefore produce colliding block_ids unless the dispatcher namespaces
    them by doc_id. A collision here means claim.get_block(block_id) can
    silently return the WRONG document's block -- exactly the kind of
    invisible wrong-evidence bug Sprint 3's verification work exists to
    catch, not cause."""
    from PIL import Image, ImageDraw

    claim_dir = tmp_path / "CLM-COLLISION-TEST"
    claim_dir.mkdir()
    for name, text in [("photo_a.png", "Alpha document text"), ("photo_b.png", "Beta document text")]:
        img = Image.new("RGB", (300, 100), "white")
        ImageDraw.Draw(img).text((10, 10), text, fill="black")
        img.save(claim_dir / name)

    records = ingest_claim_folder(str(claim_dir))
    all_block_ids = [b.block_id for r in records for b in r.blocks]
    assert len(all_block_ids) == len(set(all_block_ids)), (
        "block_ids collided across two different images in the same claim folder"
    )
