"""MCP Server for WhatsApp Web — send messages from Relay chat.

Uses pywhatkit to automate WhatsApp Web via browser.
Requires:
  - Chrome/Chromium installed
  - WhatsApp Web already scanned (QR code)
  - pip install pywhatkit

The first time you use it, a browser window will open for QR scan.
Keep the browser session active for subsequent messages.
"""

import os
import time
from datetime import datetime
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# ── Server init ───────────────────────────────────────────────

server = Server("kodama-whatsapp")

# ── Helpers ──────────────────────────────────────────────────

def _format_phone(number: str) -> str:
    """Ensure phone number starts with country code."""
    cleaned = number.replace(" ", "").replace("-", "").replace("+", "")
    # Default to Colombia (+57) if no code detected
    if not number.startswith("+"):
        return f"+57{cleaned}"
    return f"+{cleaned}"


# ── Tool definitions ─────────────────────────────────────────

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="enviar_whatsapp",
            description="Envía un mensaje de WhatsApp a un número específico. "
                        "Incluye código de país (ej: +573001234567). "
                        "Requiere Chrome y WhatsApp Web escaneado.",
            inputSchema={
                "type": "object",
                "properties": {
                    "numero": {
                        "type": "string",
                        "description": "Número telefónico con código de país (ej: +573001234567)",
                    },
                    "mensaje": {
                        "type": "string",
                        "description": "Contenido del mensaje a enviar",
                    },
                },
                "required": ["numero", "mensaje"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        if name == "enviar_whatsapp":
            result = _handle_enviar(arguments)
        else:
            raise ValueError(f"Unknown tool: {name}")
        return [TextContent(type="text", text=result)]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


# ── Tool handlers ─────────────────────────────────────────────

def _handle_enviar(args: dict) -> str:
    try:
        import pywhatkit as kit
    except ImportError:
        return (
            "⚠️ pywhatkit no está instalado. Ejecuta:\n"
            "  pip install pywhatkit\n\n"
            "También necesitas Chrome/Chromium instalado."
        )

    raw_number = args["numero"]
    message = args["mensaje"]
    phone = _format_phone(raw_number)

    try:
        kit.sendwhatmsg_instantly(
            phone,
            message,
            wait_time=15,   # seconds to wait for page load
            close_time=5,   # seconds before closing tab
        )
        return (
            f"✅ Mensaje enviado a {phone}\n"
            f"   Hora: {datetime.now().strftime('%H:%M:%S')}\n\n"
            "   💡 El navegador puede tardar unos segundos. "
            "No cierres la pestaña manualmente."
        )
    except Exception as e:
        error_msg = str(e)
        if "Could not find" in error_msg or "No Connection" in error_msg:
            return (
                "⚠️ No se pudo conectar con WhatsApp Web.\n\n"
                "Asegúrate de:\n"
                "1. Tener Chrome instalado\n"
                "2. Tener WhatsApp Web escaneado (abre https://web.whatsapp.com "
                "y escanea el QR con tu teléfono)\n"
                "3. Mantener la sesión activa"
            )
        return f"⚠️ Error al enviar WhatsApp: {error_msg[:200]}"


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
