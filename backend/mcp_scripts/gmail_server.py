"""MCP Server for Gmail — send and read emails from Relay chat.

Credentials are read from environment variables:
  GMAIL_USER         — your Gmail address (e.g., user@gmail.com)
  GMAIL_APP_PASSWORD — Gmail App Password (not your regular password)

Requires IMAP and SMTP enabled in Gmail settings.
No extra dependencies beyond Python stdlib + the mcp package.
"""

import os
import smtplib
import imaplib
import email as email_lib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header
from datetime import datetime
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, ImageContent, EmbeddedResource

# ── Server init ───────────────────────────────────────────────

server = Server("kodama-gmail")

# ── Helpers ──────────────────────────────────────────────────

def _get_credentials():
    """Get Gmail credentials from environment."""
    user = os.environ.get("GMAIL_USER", "")
    password = os.environ.get("GMAIL_APP_PASSWORD", "")
    if not user or not password:
        raise RuntimeError(
            "GMAIL_USER and GMAIL_APP_PASSWORD must be set in .env"
        )
    return user, password


def _decode_safe(header_value: str) -> str:
    """Decode an email header safely."""
    if not header_value:
        return ""
    try:
        parts = decode_header(header_value)
        result = []
        for part, enc in parts:
            if isinstance(part, bytes):
                try:
                    result.append(part.decode(enc or "utf-8", errors="replace"))
                except (LookupError, UnicodeDecodeError):
                    result.append(part.decode("utf-8", errors="replace"))
            else:
                result.append(str(part))
        return "".join(result).replace("\ufffd", "?")
    except Exception:
        return str(header_value)[:200]


def _get_email_body(msg) -> str:
    """Extract plain text body from an email message."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and \
               part.get_content_disposition() is None:
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode("utf-8", errors="replace")[:500]
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            return payload.decode("utf-8", errors="replace")[:500]
    return "(sin contenido de texto)"


def _fetch_emails(criteria: str, max_results: int = 10) -> list[dict]:
    """Generic IMAP search helper."""
    user, password = _get_credentials()
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    try:
        mail.login(user, password)
        mail.select("INBOX")
        result, data = mail.search(None, criteria)
        if not data[0]:
            return []
        ids = data[0].split()
        selected = ids[-max_results:] if len(ids) > max_results else ids
        emails = []
        for eid in reversed(selected):
            res, msg_data = mail.fetch(eid, "(RFC822)")
            raw = msg_data[0][1]
            msg = email_lib.message_from_bytes(raw)
            emails.append({
                "from": _decode_safe(msg.get("From", "")),
                "subject": _decode_safe(msg.get("Subject", "")),
                "date": msg.get("Date", ""),
                "preview": _get_email_body(msg),
            })
        return emails
    finally:
        try:
            mail.logout()
        except Exception:
            pass


# ── Tool definitions ─────────────────────────────────────────

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="enviar_correo",
            description="Envía un correo electrónico desde tu Gmail",
            inputSchema={
                "type": "object",
                "properties": {
                    "destinatario": {
                        "type": "string",
                        "description": "Correo electrónico del destinatario",
                    },
                    "asunto": {
                        "type": "string",
                        "description": "Asunto del correo",
                    },
                    "mensaje": {
                        "type": "string",
                        "description": "Contenido del correo (texto plano o HTML)",
                    },
                },
                "required": ["destinatario", "asunto", "mensaje"],
            },
        ),
        Tool(
            name="revisar_recibidos",
            description="Revisa los correos más recientes en la bandeja de entrada",
            inputSchema={
                "type": "object",
                "properties": {
                    "limite": {
                        "type": "number",
                        "description": "Cantidad máxima de correos a mostrar (default: 10)",
                        "default": 10,
                    },
                },
            },
        ),
        Tool(
            name="revisar_no_leidos",
            description="Revisa los correos no leídos en la bandeja de entrada",
            inputSchema={
                "type": "object",
                "properties": {
                    "limite": {
                        "type": "number",
                        "description": "Cantidad máxima de correos a mostrar (default: 10)",
                        "default": 10,
                    },
                },
            },
        ),
        Tool(
            name="buscar_por_remitente",
            description="Busca correos de un remitente específico",
            inputSchema={
                "type": "object",
                "properties": {
                    "remitente": {
                        "type": "string",
                        "description": "Dirección de correo o nombre del remitente",
                    },
                    "limite": {
                        "type": "number",
                        "description": "Cantidad máxima de correos a mostrar (default: 10)",
                        "default": 10,
                    },
                },
                "required": ["remitente"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        if name == "enviar_correo":
            result = _handle_enviar(arguments)
        elif name == "revisar_recibidos":
            result = _handle_recibidos(arguments)
        elif name == "revisar_no_leidos":
            result = _handle_no_leidos(arguments)
        elif name == "buscar_por_remitente":
            result = _handle_buscar(arguments)
        else:
            raise ValueError(f"Unknown tool: {name}")

        return [TextContent(type="text", text=result)]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


# ── Tool handlers ─────────────────────────────────────────────

def _handle_enviar(args: dict) -> str:
    user, password = _get_credentials()
    to = args["destinatario"]
    subject = args["asunto"]
    body = args["mensaje"]

    msg = MIMEMultipart()
    msg["From"] = user
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "html" if "<" in body and ">" in body else "plain"))

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(user, password)
        server.send_message(msg)

    return f"✅ Correo enviado a {to} — Asunto: {subject}"


def _handle_recibidos(args: dict) -> str:
    limite = args.get("limite", 10)
    emails = _fetch_emails("ALL", max_results=int(limite))
    if not emails:
        return "📭 Bandeja de entrada vacía."
    lines = [f"📬 Últimos {len(emails)} correos recibidos:\n"]
    for i, e in enumerate(emails, 1):
        lines.append(f"{i}. **De:** {e['from']}")
        lines.append(f"   **Asunto:** {e['subject']}")
        lines.append(f"   **Fecha:** {e['date']}")
        lines.append(f"   **Vista previa:** {e['preview']}\n")
    return "\n".join(lines)


def _handle_no_leidos(args: dict) -> str:
    limite = args.get("limite", 10)
    emails = _fetch_emails("UNSEEN", max_results=int(limite))
    if not emails:
        return "📭 No hay correos no leídos."
    lines = [f"📬 {len(emails)} correos no leídos:\n"]
    for i, e in enumerate(emails, 1):
        lines.append(f"{i}. **De:** {e['from']}")
        lines.append(f"   **Asunto:** {e['subject']}")
        lines.append(f"   **Fecha:** {e['date']}")
        lines.append(f"   **Vista previa:** {e['preview']}\n")
    return "\n".join(lines)


def _handle_buscar(args: dict) -> str:
    remitente = args["remitente"]
    limite = args.get("limite", 10)
    emails = _fetch_emails(f'FROM "{remitente}"', max_results=int(limite))
    if not emails:
        return f"📭 No se encontraron correos de '{remitente}'."
    lines = [f"📬 {len(emails)} correos de {remitente}:\n"]
    for i, e in enumerate(emails, 1):
        lines.append(f"{i}. **Asunto:** {e['subject']}")
        lines.append(f"   **Fecha:** {e['date']}")
        lines.append(f"   **Preview:** {e['preview']}\n")
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
