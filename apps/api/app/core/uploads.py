"""Sprint 24 hardening — architecture/09-security-testing-ops.md §1's
threat table: "file type/size allow-list" for malicious file upload.
Every upload endpoint previously called `file.file.read()` directly,
with no cap — an unauthenticated-adjacent (any authenticated org
member) DoS vector via a single huge upload. `read_upload_within_limit`
is the one place that bound now lives, used by every upload endpoint
(documents, document versions, dataset imports) rather than each
re-implementing its own check.

File *type* allow-listing (the other half of that threat-table line)
is intentionally not implemented here: an `UploadFile.content_type` is
client-supplied and trivially spoofable, so a real allow-list needs
magic-byte sniffing per accepted type — more work than this sprint's
scope, and not implementing a check that only checks the untrusted
header would be worse than no check (false confidence). Documented as
a known gap in STATUS.md rather than partially solved here.
"""

from fastapi import HTTPException, UploadFile, status

from app.core.config import get_settings


def read_upload_within_limit(file: UploadFile) -> bytes:
    limit = get_settings().max_upload_size_bytes
    content = file.file.read(limit + 1)
    if len(content) > limit:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"File exceeds the {limit // (1024 * 1024)}MB upload limit",
        )
    return content
