"""FastAPI app. Stateless by design -- see ADR.md §1."""

from __future__ import annotations

import asyncio
import csv
import io
import json
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from . import config
from .comparison import compare_abv, fuzzy_match, overall_status, verify_warning_statement
from .extraction import ExtractionError, extract_label_fields
from .schemas import (
    ApplicationData,
    FieldResultOut,
    VerificationResult,
)

# Global cap across ALL in-flight requests, not per-batch -- see ADR.md §7.
_extraction_semaphore = asyncio.Semaphore(config.MAX_CONCURRENT_EXTRACTIONS)

# Shared client, opened once in lifespan for a warm connection pool -- see ADR.md §8.
_http_client: httpx.AsyncClient | None = None

# CSV columns for the batch endpoint. `filename` keys each row to an image so
# files and rows need not be in the same order -- see ADR.md §12.
CSV_REQUIRED_COLUMNS = ("filename", "brand_name", "class_type", "abv", "net_contents", "name_address")
_CSV_OPTIONAL_BLANKABLE = ("beverage_type", "is_imported", "country_of_origin")
_APP_FIELDS = set(ApplicationData.model_fields)  # valid keys; anything else in the CSV is ignored


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Open the shared HTTP client once at startup, not per-request (ADR.md §8)."""
    global _http_client
    async with httpx.AsyncClient() as client:
        _http_client = client
        yield


app = FastAPI(title="TTB Label Verification Prototype", lifespan=lifespan)

# Prototype-scope CORS: wide open for the reviewer -- see README security trade-offs.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _error_result(filename: str, message: str) -> VerificationResult:
    return VerificationResult(filename=filename, overall_status="error", fields=[], error=message)


def _sniff_image_type(data: bytes) -> str | None:
    """Identify the real image format from magic bytes, not the spoofable header."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    return None


def _validate_upload(filename: str, data: bytes) -> None:
    """Enforce the same constraints TTB's own COLAs Online system uses."""
    if _sniff_image_type(data) not in config.ALLOWED_IMAGE_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"{filename}: file content is not a valid JPEG or PNG image",
        )
    if len(data) > config.MAX_IMAGE_SIZE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"{filename}: exceeds {config.MAX_IMAGE_SIZE_BYTES / 1_000_000:.1f}MB limit",
        )


def parse_application_csv(text: str) -> dict[str, dict]:
    """Parse the batch CSV into {filename: row}, keyed so images match by name
    regardless of order (ADR.md §12).

    Raises ValueError only on a structurally unusable CSV (no header, or a
    missing required column). A single bad *value* is left for per-row
    validation at verify time -- so it becomes one `error` row, never a
    whole-batch failure. Blank optional cells are dropped so the model's
    defaults apply; unknown columns are ignored.
    """
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("CSV has no header row")
    headers = {(h or "").strip() for h in reader.fieldnames}
    missing = [c for c in CSV_REQUIRED_COLUMNS if c not in headers]
    if missing:
        raise ValueError(f"CSV is missing required column(s): {', '.join(missing)}")

    rows: dict[str, dict] = {}
    for raw in reader:
        cleaned = {(k or "").strip(): (v or "").strip() for k, v in raw.items() if k}
        name = cleaned.pop("filename", "")
        if not name:
            continue
        cleaned = {k: v for k, v in cleaned.items() if k in _APP_FIELDS}
        for opt in _CSV_OPTIONAL_BLANKABLE:
            if cleaned.get(opt, "") == "":
                cleaned.pop(opt, None)
        rows[name] = cleaned
    return rows


async def _verify_one(
    filename: str, image_bytes: bytes, application_data: ApplicationData
) -> VerificationResult:
    """Verify already-read image bytes. Takes bytes, not an UploadFile, because
    the batch path must read its uploads before the response starts -- see
    verify_batch."""
    _validate_upload(filename, image_bytes)

    # Sniffed type, not the unverified client header (validated above, so non-None).
    media_type = _sniff_image_type(image_bytes)

    try:
        async with _extraction_semaphore:
            extracted = await extract_label_fields(image_bytes, media_type, _http_client)
    except ExtractionError as e:
        return _error_result(filename, str(e))

    results = [
        fuzzy_match("brand_name", application_data.brand_name, extracted.brand_name),
        fuzzy_match("class_type", application_data.class_type, extracted.class_type),
        fuzzy_match("net_contents", application_data.net_contents, extracted.net_contents),
        fuzzy_match("name_address", application_data.name_address, extracted.name_address),
        compare_abv(
            application_data.abv,
            extracted.abv,
            is_wine=(application_data.beverage_type == "wine"),
        ),
        verify_warning_statement(extracted.warning_text, extracted.warning_all_caps_bold),
    ]

    # Country of origin is imports-only, so compared only when the applicant filled it
    # in (blank = not applicable). Other type-conditional fields are out of scope -- ADR.md §11.
    if application_data.country_of_origin.strip():
        results.append(
            fuzzy_match("country_of_origin", application_data.country_of_origin, extracted.country_of_origin)
        )

    return VerificationResult(
        filename=filename,
        overall_status=overall_status(results),
        fields=[FieldResultOut(**vars(r)) for r in results],
    )


@app.post("/verify", response_model=VerificationResult)
async def verify_single(file: UploadFile = File(...), application_data: str = Form(...)):
    """Verify one label image against its application data."""
    try:
        app_data = ApplicationData(**json.loads(application_data))
    except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"invalid application_data: {e}") from e

    return await _verify_one(file.filename or "unknown", await file.read(), app_data)


@app.post("/verify/batch")
async def verify_batch(files: list[UploadFile] = File(...), data_csv: UploadFile = File(...)):
    """Verify a batch of labels (up to MAX_BATCH_SIZE images).

    Streams newline-delimited JSON so the client can show real progress: a
    `meta` line with the total, one `result` line per label as it finishes
    (completion order), then a final `summary` line. Matching is by filename
    (case-insensitive); a missing, extra, or failed item becomes a per-item
    `error` row rather than failing the batch -- only a structurally unusable
    CSV is a 400. See ADR.md §12, §13.
    """
    if len(files) > config.MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"batch of {len(files)} exceeds max of {config.MAX_BATCH_SIZE}",
        )

    try:
        text = (await data_csv.read()).decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise HTTPException(status_code=400, detail=f"CSV is not valid UTF-8: {e}") from e
    try:
        rows_by_name = parse_application_csv(text)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    # Match images to CSV rows by filename, case-insensitively, so
    # "Old_Tom.PNG" still pairs with a CSV row of "old_tom.png" (ADR.md §12).
    def _key(name: str) -> str:
        return (name or "unknown").strip().casefold()

    # Read every upload NOW, while the form is still open. FastAPI closes the
    # form -- and with it every UploadFile's spooled temp file -- as soon as this
    # handler returns, which is *before* Starlette iterates the body below. Read
    # lazily inside _stream() and every read raises "I/O operation on closed
    # file", killing the stream right after the meta line.
    images_by_key = {_key(f.filename or "unknown"): (f.filename or "unknown", await f.read()) for f in files}
    rows_by_key = {_key(name): (name, row) for name, row in rows_by_name.items()}
    keys = list(dict.fromkeys([*images_by_key, *rows_by_key]))

    async def _handle(key: str) -> VerificationResult:
        image = images_by_key.get(key)
        entry = rows_by_key.get(key)
        # Prefer the image's own filename for display, else the CSV's.
        display = (image[0] if image else None) or (entry[0] if entry else key)
        if image is None:
            return _error_result(display, "no image uploaded for this CSV row")
        if entry is None:
            return _error_result(display, "no application-data row in the CSV for this image")
        try:
            app_data = ApplicationData(**entry[1])
        except (ValidationError, ValueError, TypeError) as e:
            return _error_result(display, f"invalid application data: {e}")
        try:
            return await _verify_one(display, image[1], app_data)
        except HTTPException as e:
            return _error_result(display, str(e.detail))
        except Exception as e:  # noqa: BLE001 -- one bad item must never kill the stream
            return _error_result(display, f"unexpected error: {e}")

    async def _stream():
        # meta first so the client knows the denominator (images + any
        # CSV-only rows), then one line per result as it completes, then a
        # summary. Results stream in completion order, not file order.
        yield json.dumps({"type": "meta", "total": len(keys)}) + "\n"
        counts = {"pass": 0, "review": 0, "fail": 0, "error": 0}
        tasks = [asyncio.create_task(_handle(k)) for k in keys]
        for coro in asyncio.as_completed(tasks):
            result = await coro
            counts[result.overall_status] = counts.get(result.overall_status, 0) + 1
            yield json.dumps({"type": "result", "result": result.model_dump()}) + "\n"
        yield json.dumps({
            "type": "summary",
            "total": len(keys),
            "passed": counts["pass"],
            "review": counts["review"],
            "failed": counts["fail"],
            "errored": counts["error"],
        }) + "\n"

    return StreamingResponse(_stream(), media_type="application/x-ndjson")


@app.get("/health")
async def health():
    """Health check, and the keep-alive/warmup target -- see ADR.md §9."""
    return {"status": "ok"}
