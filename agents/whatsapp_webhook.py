"""WhatsApp Webhook & Smart Debounce Message Bundler Router.
Integrates SmartSalesAssistant with Meta WhatsApp Cloud API and other WhatsApp providers.

Handles:
1. Webhook Verification (GET /webhook/whatsapp)
2. Asynchronous Incoming Message Ingestion (POST /webhook/whatsapp)
3. 7-10 Second Debounce Buffering (Groups rapid sequential messages)
4. Outbound Reply Dispatch to WhatsApp API
"""

import os
import json
import asyncio
import logging
import urllib.request
from typing import Dict, Any, Optional

from agents.smart_sales_assistant import SmartSalesAssistant, MESSAGE_BUFFER_SECONDS

logger = logging.getLogger(__name__)

WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "be_smart_with_ai_token")
WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")

# Initialize shared sales assistant
sales_bot = SmartSalesAssistant(buffer_seconds=MESSAGE_BUFFER_SECONDS)


def send_whatsapp_message(to_phone: str, text_message: str) -> bool:
    """Dispatches outbound text reply via Meta WhatsApp Cloud API."""
    token = os.getenv("WHATSAPP_ACCESS_TOKEN", WHATSAPP_ACCESS_TOKEN).strip()
    phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID", WHATSAPP_PHONE_NUMBER_ID).strip()

    if not token or not phone_id:
        logger.warning(
            f"[WhatsApp Outbound] WHATSAPP_ACCESS_TOKEN or WHATSAPP_PHONE_NUMBER_ID missing. "
            f"Simulating delivery to {to_phone}: {text_message[:60]}..."
        )
        return False

    url = f"https://graph.facebook.com/v21.0/{phone_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_phone,
        "type": "text",
        "text": {"preview_url": False, "body": text_message}
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status in [200, 201]:
                logger.info(f"[WhatsApp Outbound] Successfully dispatched message to {to_phone}")
                return True
    except Exception as e:
        logger.error(f"[WhatsApp Outbound Error]: {e}")
    return False


async def handle_outbound_sales_reply(result: Dict[str, Any]):
    """Callback fired after the 7-10s debounce window bundles messages and AI produces the output."""
    phone = result.get("lead_data", {}).get("phone") if result.get("lead_data") else None
    if not phone:
        # Extract from session_id: sales_<phone>
        sid = result.get("session_id", "")
        phone = sid.replace("sales_", "") if sid.startswith("sales_") else None

    output_text = result.get("output", "")
    if phone and output_text:
        await asyncio.to_thread(send_whatsapp_message, to_phone=phone, text_message=output_text)


def create_whatsapp_router():
    """Factory creating a FastAPI APIRouter with WhatsApp Webhook and Debouncer endpoints."""
    try:
        from fastapi import APIRouter, Request, HTTPException
        from fastapi.responses import PlainTextResponse, JSONResponse
    except ImportError:
        logger.warning("FastAPI not installed in current env; APIRouter cannot be created.")
        return None

    router = APIRouter(prefix="/webhook", tags=["WhatsApp Webhook"])

    @router.get("/whatsapp")
    async def verify_webhook(request: Request):
        """Meta WhatsApp Cloud API Webhook Verification."""
        params = request.query_params
        mode = params.get("hub.mode")
        token = params.get("hub.verify_token")
        challenge = params.get("hub.challenge")

        if mode and token:
            if mode == "subscribe" and token == WHATSAPP_VERIFY_TOKEN:
                logger.info("[WhatsApp Webhook] Verification successful!")
                return PlainTextResponse(challenge)
            else:
                raise HTTPException(status_code=403, detail="Verification token mismatch")
        return PlainTextResponse("WhatsApp Webhook Endpoint Active")

    @router.post("/whatsapp")
    async def receive_whatsapp_event(request: Request):
        """Receives incoming messages, immediately buffers them (7-10s debounce), and returns 200 OK."""
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"status": "invalid_json"}, status_code=400)

        entries = body.get("entry", [])
        for entry in entries:
            for change in entry.get("changes", []):
                value = change.get("value", {})
                contacts = value.get("contacts", [])
                sender_name = contacts[0].get("profile", {}).get("name") if contacts else None
                messages = value.get("messages", [])

                for msg in messages:
                    sender_id = msg.get("from")  # Sender WhatsApp phone number
                    msg_type = msg.get("type")

                    if msg_type == "text":
                        text_body = msg.get("text", {}).get("body", "")
                        if sender_id and text_body:
                            # Forward to the smart debounce message bundler
                            await sales_bot.receive_message(
                                sender_id=sender_id,
                                message=text_body,
                                sender_name=sender_name,
                                callback=handle_outbound_sales_reply
                            )

        # Meta expects 200 OK within 3 seconds
        return JSONResponse({"status": "received_and_buffered"})

    return router


def create_whatsapp_app():
    """Factory creating a FastAPI app with WhatsApp Webhook and Debouncer endpoints."""
    try:
        from fastapi import FastAPI
    except ImportError:
        logger.warning("FastAPI not installed in current env; provide standalone router definition.")
        return None

    app = FastAPI(title="Be Smart With AI - WhatsApp Webhook Service")
    router = create_whatsapp_router()
    if router:
        app.include_router(router)
    return app
