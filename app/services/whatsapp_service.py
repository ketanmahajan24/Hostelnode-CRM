"""
Thin async client around the Meta WhatsApp Cloud API.
Docs: https://developers.facebook.com/docs/whatsapp/cloud-api
"""
import httpx
from typing import Optional, List, Any
from app.config import settings


class WhatsAppAPIError(Exception):
    def __init__(self, message: str, payload: Optional[dict] = None):
        super().__init__(message)
        self.payload = payload


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.wa_token}",
        "Content-Type": "application/json",
    }


async def _post(path: str, json_body: dict) -> dict:
    url = f"{settings.graph_base_url}/{path}"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, headers=_headers(), json=json_body)
    data = resp.json()
    if resp.status_code >= 400:
        raise WhatsAppAPIError(
            data.get("error", {}).get("message", "WhatsApp API error"), data
        )
    return data


async def send_text_message(to: str, body: str, reply_to_wamid: Optional[str] = None) -> dict:
    payload: dict[str, Any] = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": body, "preview_url": True},
    }
    if reply_to_wamid:
        payload["context"] = {"message_id": reply_to_wamid}
    return await _post("messages", payload)


async def send_media_message(to: str, media_type: str, link_or_id: str, id_based: bool,
                              caption: Optional[str] = None, filename: Optional[str] = None) -> dict:
    """media_type: image | video | audio | document. link_or_id is either a public URL or an uploaded media id."""
    media_obj: dict[str, Any] = {"id": link_or_id} if id_based else {"link": link_or_id}
    if caption and media_type in ("image", "video", "document"):
        media_obj["caption"] = caption
    if filename and media_type == "document":
        media_obj["filename"] = filename

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": media_type,
        media_type: media_obj,
    }
    return await _post("messages", payload)


async def send_location_message(to: str, latitude: float, longitude: float,
                                 name: Optional[str] = None, address: Optional[str] = None) -> dict:
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "location",
        "location": {
            "latitude": latitude,
            "longitude": longitude,
            **({"name": name} if name else {}),
            **({"address": address} if address else {}),
        },
    }
    return await _post("messages", payload)


async def send_template_message(to: str, template_name: str, language: str = "en_US",
                                 components: Optional[List[dict]] = None) -> dict:
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language},
            **({"components": components} if components else {}),
        },
    }
    return await _post("messages", payload)


async def mark_message_as_read(wamid: str) -> dict:
    payload = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": wamid,
    }
    return await _post("messages", payload)


async def upload_media(file_path: str, mime_type: str) -> str:
    """Uploads local media to Meta and returns the media id (used for outbound re-send)."""
    url = f"{settings.graph_base_url}/media"
    async with httpx.AsyncClient(timeout=60) as client:
        with open(file_path, "rb") as f:
            files = {"file": (file_path, f, mime_type)}
            data = {"messaging_product": "whatsapp"}
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {settings.wa_token}"},
                files=files,
                data=data,
            )
    result = resp.json()
    if resp.status_code >= 400:
        raise WhatsAppAPIError(result.get("error", {}).get("message", "Upload failed"), result)
    return result["id"]


async def get_media_url(media_id: str) -> dict:
    """Returns Meta's temporary CDN URL + mime type for a given inbound media id."""
    url = f"{settings.graph_base_url.rsplit('/', 1)[0]}/{media_id}"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers=_headers())
    return resp.json()


async def download_media_bytes(media_url: str) -> bytes:
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(media_url, headers={"Authorization": f"Bearer {settings.wa_token}"})
    resp.raise_for_status()
    return resp.content


async def fetch_approved_templates() -> List[dict]:
    """Pulls the list of approved message templates from the WABA."""
    url = (
        f"https://graph.facebook.com/{settings.wa_api_version}/"
        f"{settings.wa_business_account_id}/message_templates?limit=100"
    )
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers=_headers())
    data = resp.json()
    if resp.status_code >= 400:
        raise WhatsAppAPIError(data.get("error", {}).get("message", "Failed to fetch templates"), data)
    return data.get("data", [])
