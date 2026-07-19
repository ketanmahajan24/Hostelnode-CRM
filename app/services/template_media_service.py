"""
Shared logic for building the WhatsApp `components` payload a template needs
when it has a media header (IMAGE/VIDEO/DOCUMENT).

BUG BEING FIXED (see conversation history): WhatsApp requires header media to
be supplied on EVERY send of a template that has a media header — the
approved template only stores the header's *type*, not a permanent copy of
the file. Every send path in this app (campaigns, bulk-send, follow-up
nudges, one-off chat sends) must call build_template_components() and pass
the result through, or Meta rejects the whole message even though the
template itself shows APPROVED.

This was previously implemented independently (and inconsistently) in
campaigns.py alone, and depended on a `header_type` field that nothing ever
set — so it silently no-op'd. This module is the single shared version;
`sync_templates` in templates_router.py is responsible for populating
`header_type` from Meta's component data on every sync.
"""
from typing import Optional, List

# Meta's actual per-type limits for template header media.
MEDIA_RULES = {
    "IMAGE": {"extensions": {".jpg", ".jpeg", ".png"}, "max_bytes": 5 * 1024 * 1024},
    "VIDEO": {"extensions": {".mp4", ".3gp"}, "max_bytes": 16 * 1024 * 1024},
    "DOCUMENT": {"extensions": {".pdf"}, "max_bytes": 100 * 1024 * 1024},
}


def validate_upload(header_type: str, filename: str, size_bytes: int) -> Optional[str]:
    """Returns an error message string if invalid, or None if OK."""
    rules = MEDIA_RULES.get(header_type.upper())
    if not rules:
        return f"Unsupported header type '{header_type}'."

    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in rules["extensions"]:
        return f"{header_type} header needs one of {sorted(rules['extensions'])}, got '{ext}'."

    if size_bytes > rules["max_bytes"]:
        max_mb = rules["max_bytes"] / (1024 * 1024)
        return f"File is too large for a {header_type} header — Meta's limit is {max_mb:.0f}MB."

    return None


def needs_header_media(template_doc: dict) -> bool:
    header_type = (template_doc.get("header_type") or "").upper()
    return header_type in ("IMAGE", "VIDEO", "DOCUMENT")


def build_template_components(template_doc: Optional[dict]) -> Optional[List[dict]]:
    """
    Returns the `components` array required when a template's header is
    IMAGE/VIDEO/DOCUMENT. Returns None if the template has no media header
    (plain text/no header templates don't need this).
    Raises ValueError if a media header is required but no media reference
    has been configured on the template doc — this is deliberately loud
    rather than silently sending a broken message.
    """
    if not template_doc or not needs_header_media(template_doc):
        return None

    header_type = template_doc["header_type"].upper()
    media_id = template_doc.get("header_media_id")
    media_url = template_doc.get("header_image_url") or template_doc.get("header_media_url")

    if not media_id and not media_url:
        raise ValueError(
            f"Template '{template_doc.get('name')}' has a {header_type} header "
            f"but no header image URL is set. Set one on the Templates page."
        )

    media_key = header_type.lower()  # "image" | "video" | "document"
    media_obj = {"id": media_id} if media_id else {"link": media_url}

    return [{
        "type": "header",
        "parameters": [{"type": media_key, media_key: media_obj}],
    }]
