from __future__ import annotations

from pathlib import Path

import pypdfium2 as pdfium
from pypdfium2._helpers.misc import PdfiumError


class InvalidPDFError(ValueError):
    pass


class EncryptedPDFError(ValueError):
    pass


def inspect_pdf(path: Path, max_pages: int) -> int:
    try:
        document = pdfium.PdfDocument(path)
    except PdfiumError as exc:
        code = getattr(exc, "err_code", exc.args[1] if len(exc.args) > 1 else None)
        if code == pdfium.raw.FPDF_ERR_PASSWORD or "password" in str(exc).lower():
            raise EncryptedPDFError("Encrypted PDFs are not supported") from exc
        raise InvalidPDFError("The uploaded PDF is corrupt or invalid") from exc
    try:
        pages = len(document)
    finally:
        document.close()
    if pages < 1:
        raise InvalidPDFError("The uploaded PDF has no pages")
    if pages > max_pages:
        raise InvalidPDFError(f"PDF exceeds the configured {max_pages}-page limit")
    return pages


def render_page(pdf_path: Path, page_number: int, destination: Path) -> None:
    document = pdfium.PdfDocument(pdf_path)
    page = document[page_number - 1]
    bitmap = None
    image = None
    try:
        width, height = page.get_size()
        scale = min(150 / 72, 2400 / max(width, height))
        bitmap = page.render(scale=scale)
        image = bitmap.to_pil().convert("RGB")
        destination.parent.mkdir(parents=True, exist_ok=True)
        image.save(destination, "JPEG", quality=90)
    finally:
        if image is not None:
            image.close()
        if bitmap is not None:
            bitmap.close()
        page.close()
        document.close()
