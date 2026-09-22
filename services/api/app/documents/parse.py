"""Parsing uploaded documents into pages with provenance.

Doc 07 M5: *"Chunk with source and page retained"* and *"handle parse failures,
scanned PDFs without OCR, size limits — **visibly, never silently**."*

Provenance is not metadata here, it is the product. Proposal Studio's grounding
rule (doc 01 M8) is that every price cites the document and page it came from,
so a parser that loses the page number quietly breaks the highest-liability
module in the system. Every `Page` therefore carries its number from the moment
it is read.

**A scanned PDF is the failure worth naming.** It parses perfectly and yields no
text. Treated as success it becomes an indexed document with no content — the
user uploaded their price list, saw a tick, and Proposal Studio will later say
it cannot find a price. `ParseOutcome.NO_TEXT_LAYER` exists so that lands as a
visible state at upload instead.
"""

from __future__ import annotations

import csv
import io
import os
import warnings
import zipfile
from dataclasses import dataclass, field
from enum import StrEnum

from anyio import CapacityLimiter, to_thread
from defusedxml import defuse_stdlib

from app.documents.limits import MAX_FILE_BYTES as MAX_FILE_BYTES
from app.documents.limits import MB

# One number, defined in `limits.py` with the other two. It lived here at 50 MB
# — `doc/01` M1's figure — after `doc/11` settled on 25, and a second definition
# is how they came to disagree in the first place.

# `.docx`/`.pptx`/`.xlsx` are zip archives of XML, parsed by `python-docx`,
# `python-pptx` and `openpyxl` with the stdlib's `xml.etree` — which has no
# built-in defence against a billion-laughs entity expansion or an
# external-entity fetch (L-05). Patched process-wide, once, at import: every
# caller of `xml.etree.ElementTree` in this process is covered without
# touching three vendored parsers.
#
# `defuse_stdlib` imports its own deprecated `cElementTree` compatibility
# shim along the way, and emits `DeprecationWarning` doing it — a warning its
# own `catch_warnings()` wrapper does not actually suppress. Harmless (the
# shim is never used; only `ElementTree` is), but `filterwarnings = ["error"]`
# in this project's pytest config turns it into a collection error for every
# module that imports this one. Silenced here, narrowly, rather than loosened
# project-wide.
with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    defuse_stdlib()

# Below this, a "successful" parse is almost certainly an image-only document.
MIN_TEXT_CHARS_PER_PAGE = 20

# A zip-based upload (`.docx`/`.pptx`/`.xlsx`) can claim a tiny compressed size
# and expand to gigabytes on decompression — the classic zip-bomb, and
# `MAX_FILE_BYTES` alone does not catch it because that limit is checked
# against the *compressed* upload. Bounded here, on the sum of every member's
# *uncompressed* size, before any parser reads a byte of content.
MAX_ZIP_UNCOMPRESSED_BYTES = 10 * MAX_FILE_BYTES


class DocumentKind(StrEnum):
    PDF = "pdf"
    DOCX = "docx"
    PPTX = "pptx"
    XLSX = "xlsx"
    CSV = "csv"
    TXT = "txt"


class ParseOutcome(StrEnum):
    OK = "ok"
    TOO_LARGE = "too_large"
    UNSUPPORTED_TYPE = "unsupported_type"
    CORRUPT = "corrupt"
    ENCRYPTED = "encrypted"
    NO_TEXT_LAYER = "no_text_layer"
    EMPTY = "empty"


# What the user is told. Each names the problem *and* what to do, because a
# failure the user cannot act on is only marginally better than a silent one.
OUTCOME_MESSAGE: dict[ParseOutcome, str] = {
    ParseOutcome.OK: "",
    ParseOutcome.TOO_LARGE: (
        f"This file is over {MAX_FILE_BYTES // MB} MB. Split it and upload the parts."
    ),
    ParseOutcome.UNSUPPORTED_TYPE: (
        "Only PDF, Word, PowerPoint, Excel, CSV and text files can be read. "
        "Images and scans are not read at all, so there is no point converting one."
    ),
    ParseOutcome.CORRUPT: "This file could not be opened. It may be damaged.",
    ParseOutcome.ENCRYPTED: "This file is password-protected. Remove the password and re-upload.",
    ParseOutcome.NO_TEXT_LAYER: (
        "This looks like a scan. There is no text to read, so nothing was indexed — "
        "re-save it with text, or use a searchable PDF."
    ),
    ParseOutcome.EMPTY: "This file contains no text.",
}

EXTENSION_KIND: dict[str, DocumentKind] = {
    ".pdf": DocumentKind.PDF,
    ".docx": DocumentKind.DOCX,
    ".pptx": DocumentKind.PPTX,
    ".xlsx": DocumentKind.XLSX,
    ".xlsm": DocumentKind.XLSX,
    ".csv": DocumentKind.CSV,
    ".txt": DocumentKind.TXT,
    ".md": DocumentKind.TXT,
}


@dataclass(frozen=True, slots=True)
class Page:
    """One page, slide, sheet or section — the unit a citation points at."""

    number: int
    text: str
    label: str | None = None
    """A human-meaningful name where the format has one: a sheet name, a slide
    title. "page 4" is far less useful than "Rate Card 2026" in a citation."""


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    kind: DocumentKind | None
    outcome: ParseOutcome
    pages: tuple[Page, ...] = field(default=())
    page_count: int = 0
    char_count: int = 0

    @property
    def succeeded(self) -> bool:
        return self.outcome is ParseOutcome.OK

    @property
    def message(self) -> str:
        return OUTCOME_MESSAGE[self.outcome]


def kind_for_filename(filename: str) -> DocumentKind | None:
    lowered = filename.lower()
    for extension, kind in EXTENSION_KIND.items():
        if lowered.endswith(extension):
            return kind
    return None


def _fail(kind: DocumentKind | None, outcome: ParseOutcome) -> ParsedDocument:
    return ParsedDocument(kind=kind, outcome=outcome)


_ZIP_KINDS = frozenset({DocumentKind.DOCX, DocumentKind.PPTX, DocumentKind.XLSX})


def _zip_bomb(data: bytes) -> bool:
    """True if a zip-based upload's members would decompress past the cap.

    Checked against the archive's own declared sizes, never by inflating it —
    inflating first to measure is the attack. `bad_file` also catches a
    truncated or hand-edited central directory, which is corruption `_fail`
    already has a named outcome for.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if archive.testzip() is not None:
                return True
            total = sum(member.file_size for member in archive.infolist())
    except zipfile.BadZipFile:
        return True
    return total > MAX_ZIP_UNCOMPRESSED_BYTES


def parse_document(data: bytes, *, filename: str) -> ParsedDocument:
    """Parse into pages, or return a named failure. Never raises."""
    if len(data) > MAX_FILE_BYTES:
        return _fail(kind_for_filename(filename), ParseOutcome.TOO_LARGE)

    kind = kind_for_filename(filename)
    if kind is None:
        return _fail(None, ParseOutcome.UNSUPPORTED_TYPE)

    if not data:
        return _fail(kind, ParseOutcome.EMPTY)

    if kind in _ZIP_KINDS and _zip_bomb(data):
        return _fail(kind, ParseOutcome.CORRUPT)

    try:
        pages = _PARSERS[kind](data)
    except _EncryptedError:
        return _fail(kind, ParseOutcome.ENCRYPTED)
    except Exception:
        # Deliberately broad. A malformed file is a user-visible outcome, not a
        # 500 — and the parsers raise a wide variety of library-specific errors.
        return _fail(kind, ParseOutcome.CORRUPT)

    total_chars = sum(len(p.text.strip()) for p in pages)

    if not pages or total_chars == 0:
        # PDFs are the common case here; a Word file with no text is simply
        # empty, which is a different thing to say.
        outcome = ParseOutcome.NO_TEXT_LAYER if kind is DocumentKind.PDF else ParseOutcome.EMPTY
        return ParsedDocument(kind=kind, outcome=outcome, page_count=len(pages))

    if kind is DocumentKind.PDF and total_chars < MIN_TEXT_CHARS_PER_PAGE * len(pages):
        # Scanned PDFs frequently yield a handful of stray characters rather
        # than nothing at all, which would otherwise pass as a real parse.
        return ParsedDocument(
            kind=kind,
            outcome=ParseOutcome.NO_TEXT_LAYER,
            page_count=len(pages),
            char_count=total_chars,
        )

    return ParsedDocument(
        kind=kind,
        outcome=ParseOutcome.OK,
        pages=tuple(pages),
        page_count=len(pages),
        char_count=total_chars,
    )


# **The shared thread pool.** Mirrors `app.auth.passwords._HASHING_LIMITER`
# exactly, and for the identical reason: `to_thread.run_sync` with no limiter
# draws on anyio's process-wide default (40 tokens), so a burst of uploads
# would not only serialise themselves, it would starve every other blocking
# call in the process — including argon2's own limiter's neighbours. Sized to
# cores rather than a round number: parsing is CPU-bound and one core is left
# for the event loop.
_PARSE_LIMITER = CapacityLimiter(max(2, (os.cpu_count() or 2) - 1))


async def parse_document_async(data: bytes, *, filename: str) -> ParsedDocument:
    """`parse_document`, off the event loop (L-05).

    `parse_document` is synchronous and can hold a core for as long as
    openpyxl or pypdf takes to walk a large file — a blocking call inside the
    `async def` upload handler that was stalling every other request on the
    process while one document parsed. Offloaded through the same
    `CapacityLimiter` pattern as password hashing, so a burst of uploads
    queues on a bounded pool rather than exhausting anyio's shared default.
    """
    return await to_thread.run_sync(
        lambda: parse_document(data, filename=filename), limiter=_PARSE_LIMITER
    )


class _EncryptedError(Exception):
    pass


def _parse_pdf(data: bytes) -> list[Page]:
    from pypdf import PdfReader
    from pypdf.errors import FileNotDecryptedError

    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        try:
            # An empty-password PDF is encrypted but readable.
            if reader.decrypt("") == 0:
                raise _EncryptedError
        except FileNotDecryptedError as exc:
            raise _EncryptedError from exc

    return [
        Page(number=index + 1, text=(page.extract_text() or ""))
        for index, page in enumerate(reader.pages)
    ]


def _parse_docx(data: bytes) -> list[Page]:
    from docx import Document

    document = Document(io.BytesIO(data))
    paragraphs = [p.text for p in document.paragraphs if p.text.strip()]

    for table in document.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                paragraphs.append(" | ".join(cells))

    # Word has no page concept before rendering, so the document is one logical
    # page. Claiming page numbers we cannot know would make citations wrong in
    # a way nobody could detect.
    return [Page(number=1, text="\n".join(paragraphs), label="document")]


def _parse_pptx(data: bytes) -> list[Page]:
    from pptx import Presentation

    presentation = Presentation(io.BytesIO(data))
    pages: list[Page] = []

    for index, slide in enumerate(presentation.slides):
        parts = [
            shape.text_frame.text
            for shape in slide.shapes
            if shape.has_text_frame and shape.text_frame.text.strip()
        ]
        title = None
        if slide.shapes.title is not None and slide.shapes.title.text.strip():
            title = slide.shapes.title.text.strip()[:120]
        pages.append(Page(number=index + 1, text="\n".join(parts), label=title))

    return pages


def _parse_xlsx(data: bytes) -> list[Page]:
    from openpyxl import load_workbook

    # `data_only` reads computed values rather than formulas: a price list
    # citation should quote the price, not `=B2*1.05`.
    workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    pages: list[Page] = []

    for index, sheet in enumerate(workbook.worksheets):
        rows: list[str] = []
        for row in sheet.iter_rows(values_only=True):
            cells = [str(c).strip() for c in row if c is not None and str(c).strip()]
            if cells:
                rows.append(" | ".join(cells))
        pages.append(Page(number=index + 1, text="\n".join(rows), label=sheet.title))

    workbook.close()
    return pages


# Rows per page. A citation points at a page, so one page of ten thousand rows
# cites as "page 1" and tells a founder checking a number nothing at all. Small
# enough to be a useful pointer, large enough that a page keeps related rows
# together.
CSV_ROWS_PER_PAGE = 200


def _parse_csv(data: bytes) -> list[Page]:
    """Rows rendered so each value keeps its header.

    **Not `_parse_txt` with a different extension.** Decoded as plain text a CSV
    is one page of comma soup: `Muscat Trading, 4500` retrieves badly and cites
    worse, because a chunk is shown to a human on its own and has to mean
    something there. `Customer: Muscat Trading | Amount: 4500` does.

    Two encoding details are load-bearing rather than pedantic, and both come
    from the tool most likely to have written the file. Excel on Windows emits a
    **UTF-8 BOM**, which unstripped corrupts the first header — silently, since
    the file parses and only one column is wrong. And Excel in this region
    writes **semicolons**, which read as commas give one column whose name is
    every header: no error, no retrieval.
    """
    text = data.decode("utf-8-sig", errors="replace")
    if "\x00" in text:
        # Decoded, but not text. Better named as corrupt than indexed as
        # replacement characters, which would retrieve as noise.
        raise ValueError("not text")

    sample = text[:4096]
    try:
        dialect: type[csv.Dialect] | csv.Dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel

    rows = [row for row in csv.reader(io.StringIO(text), dialect) if any(c.strip() for c in row)]
    if not rows:
        return []

    # A header row is used when there is one to use. Not every export has one,
    # and refusing those would make the product fussier than the tooling its
    # customers already run.
    header = [c.strip() for c in rows[0]]
    looks_like_header = all(h and not h.replace(".", "", 1).isdigit() for h in header)

    # A header row alone is an export with no data in it. Rendering it as one
    # row would index the column names as though they were a fact, which is the
    # kind of content-free chunk that dilutes every retrieval it appears in.
    if looks_like_header and len(rows) == 1:
        return []

    has_header = looks_like_header and len(rows) > 1
    body = rows[1:] if has_header else rows

    def render(row: list[str]) -> str:
        cells = [c.strip() for c in row]
        if not has_header:
            return " | ".join(c for c in cells if c)
        pairs = zip(header, cells, strict=False)
        return " | ".join(f"{name}: {value}" for name, value in pairs if value)

    pages: list[Page] = []
    for start in range(0, len(body), CSV_ROWS_PER_PAGE):
        block = body[start : start + CSV_ROWS_PER_PAGE]
        number = len(pages) + 1
        pages.append(
            Page(
                number=number,
                text="\n".join(render(row) for row in block),
                label=f"rows {start + 1}-{start + len(block)}",
            )
        )
    return pages


def _parse_txt(data: bytes) -> list[Page]:
    return [Page(number=1, text=data.decode("utf-8", errors="replace"), label="document")]


_PARSERS = {
    DocumentKind.PDF: _parse_pdf,
    DocumentKind.DOCX: _parse_docx,
    DocumentKind.PPTX: _parse_pptx,
    DocumentKind.XLSX: _parse_xlsx,
    DocumentKind.CSV: _parse_csv,
    DocumentKind.TXT: _parse_txt,
}
