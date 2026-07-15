from pathlib import Path

import pypdfium2 as pdfium
import pytest

from paddlocr_vl.utils.pdf_utils import (
    EncryptedPDFError,
    InvalidPDFError,
    inspect_pdf,
)


def test_inspect_pdf_rejects_corrupt_and_over_page_limit(tmp_path: Path) -> None:
    corrupt = tmp_path / "bad.pdf"
    corrupt.write_bytes(b"not a pdf")
    with pytest.raises(InvalidPDFError, match="corrupt"):
        inspect_pdf(corrupt, 100)
    with pytest.raises(InvalidPDFError, match="page limit"):
        inspect_pdf(Path("test.pdf"), 2)


def test_inspect_pdf_rejects_encrypted(monkeypatch, tmp_path: Path) -> None:
    def encrypted(_):
        raise pdfium.PdfiumError("password required", pdfium.raw.FPDF_ERR_PASSWORD)

    monkeypatch.setattr(pdfium, "PdfDocument", encrypted)
    with pytest.raises(EncryptedPDFError):
        inspect_pdf(tmp_path / "encrypted.pdf", 100)
