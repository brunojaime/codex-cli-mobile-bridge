from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from html import unescape
import json
import os
import re
import socket
from typing import Any
from urllib.parse import quote_plus, urlsplit

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations


WHOIS_HOST = "whois.nic.ar"
WHOIS_PORT = 43
WHOIS_INFO_URL = "https://nic.ar/es/whois/info"
FEES_URL = "https://nic.ar/dominios/aranceles"
DOMAIN_SEARCH_URL = "https://nic.ar/buscar-dominio"
REGISTRATION_SERVICE_URL = (
    "https://www.argentina.gob.ar/servicio/registrar-un-dominio-de-internet"
)
TAD_BASE_URL = "https://tramitesadistancia.gob.ar"

_KNOWN_ZONES = (
    ".senasa.ar",
    ".musica.ar",
    ".mutual.ar",
    ".com.ar",
    ".coop.ar",
    ".gob.ar",
    ".int.ar",
    ".mil.ar",
    ".net.ar",
    ".org.ar",
    ".seg.ar",
    ".tur.ar",
    ".bet.ar",
    ".ar",
)
_SPECIAL_ZONES = frozenset(
    {
        ".bet.ar",
        ".coop.ar",
        ".gob.ar",
        ".int.ar",
        ".mil.ar",
        ".musica.ar",
        ".mutual.ar",
        ".org.ar",
        ".seg.ar",
        ".senasa.ar",
        ".tur.ar",
    }
)
_NOT_REGISTERED_MARKER = "el dominio no se encuentra registrado en nic argentina"
_MAX_WHOIS_BYTES = 256_000
_HTTP_TIMEOUT_SECONDS = 15.0
_WHOIS_TIMEOUT_SECONDS = 10.0
_USER_AGENT = (
    os.environ.get("NIC_AR_HTTP_USER_AGENT", "").strip()
    or "CodexMobileBridge-NICArDomains/1.0"
)

_READ_ONLY_NETWORK = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)

mcp = FastMCP(
    "NIC Argentina Domains",
    instructions=(
        "Use deterministic official NIC Argentina and TAD lookups to check .ar "
        "availability, obtain current fees, and prepare a registration handoff. "
        "Never request, store, or submit fiscal credentials or payment details. "
        "The user must authenticate, confirm, and pay in the official TAD flow."
    ),
    json_response=True,
    log_level="WARNING",
)


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _normalize_zone(value: str) -> str:
    zone = value.strip().lower()
    if not zone:
        raise ValueError("The domain zone cannot be empty.")
    if not zone.startswith("."):
        zone = f".{zone}"
    if zone not in _KNOWN_ZONES:
        raise ValueError(
            f"Unsupported NIC Argentina zone `{zone}`. Use one of: "
            + ", ".join(_KNOWN_ZONES)
        )
    return zone


def _normalize_domain(value: str, *, default_zone: str = ".com.ar") -> dict[str, Any]:
    original = value.strip()
    if not original:
        raise ValueError("The domain cannot be empty.")

    candidate = original
    if "://" in candidate:
        candidate = urlsplit(candidate).hostname or ""
    else:
        candidate = candidate.split("/", 1)[0]
        if "@" in candidate:
            candidate = candidate.rsplit("@", 1)[-1]
        if ":" in candidate:
            candidate = candidate.split(":", 1)[0]

    candidate = candidate.strip().strip(".").lower()
    default_zone_applied = "." not in candidate
    if default_zone_applied:
        candidate = f"{candidate}{_normalize_zone(default_zone)}"

    try:
        ascii_domain = candidate.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError("The domain cannot be represented as a valid IDN.") from exc

    if len(ascii_domain) > 253:
        raise ValueError("The normalized domain exceeds the DNS length limit.")
    if not ascii_domain.endswith(".ar"):
        raise ValueError("Only domains ending in `.ar` are supported.")

    zone = next((item for item in _KNOWN_ZONES if ascii_domain.endswith(item)), None)
    if zone is None:
        raise ValueError("The domain does not use a supported NIC Argentina zone.")

    registrable_label = ascii_domain[: -len(zone)].rstrip(".")
    if not registrable_label or "." in registrable_label:
        raise ValueError(
            "Provide a registrable domain, not a nested subdomain such as `www.example.com.ar`."
        )
    if len(registrable_label) > 63:
        raise ValueError("The registrable label exceeds the DNS length limit.")
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", registrable_label):
        raise ValueError(
            "The registrable label must contain letters, numbers, or internal hyphens."
        )

    return {
        "input": original,
        "domain": ascii_domain,
        "unicode_domain": candidate,
        "label": registrable_label,
        "zone": zone,
        "default_zone_applied": default_zone_applied,
        "zone_requires_prior_authorization": zone in _SPECIAL_ZONES,
        "short_direct_ar_requires_approval": zone == ".ar" and len(registrable_label) < 4,
    }


def _query_whois(domain: str) -> str:
    chunks: list[bytes] = []
    received = 0
    with socket.create_connection(
        (WHOIS_HOST, WHOIS_PORT), timeout=_WHOIS_TIMEOUT_SECONDS
    ) as connection:
        connection.settimeout(_WHOIS_TIMEOUT_SECONDS)
        connection.sendall(f"{domain}\r\n".encode("ascii"))
        while received < _MAX_WHOIS_BYTES:
            chunk = connection.recv(min(8192, _MAX_WHOIS_BYTES - received))
            if not chunk:
                break
            chunks.append(chunk)
            received += len(chunk)
    return b"".join(chunks).decode("utf-8", errors="replace")


def _parse_whois_output(domain: str, output: str) -> dict[str, Any]:
    if _NOT_REGISTERED_MARKER in output.casefold():
        return {
            "status": "available",
            "available": True,
            "registered_domain": None,
            "registered_at": None,
            "changed_at": None,
            "expires_at": None,
            "nameservers": [],
        }

    fields: dict[str, list[str]] = {}
    for line in output.splitlines():
        if line.startswith("%") or ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        key = key.strip().lower()
        value = raw_value.strip()
        if key in {"domain", "registered", "changed", "expire", "nserver"} and value:
            fields.setdefault(key, []).append(value)

    registered_domains = fields.get("domain", [])
    if domain.casefold() in {item.casefold() for item in registered_domains}:
        return {
            "status": "registered",
            "available": False,
            "registered_domain": registered_domains[0],
            "registered_at": (fields.get("registered") or [None])[0],
            "changed_at": (fields.get("changed") or [None])[0],
            "expires_at": (fields.get("expire") or [None])[0],
            "nameservers": [
                item.split(" ", 1)[0].rstrip(".").lower()
                for item in fields.get("nserver", [])
            ],
        }

    return {
        "status": "unknown",
        "available": None,
        "registered_domain": None,
        "registered_at": None,
        "changed_at": None,
        "expires_at": None,
        "nameservers": [],
    }


def _check_domain_payload(domain: str, *, default_zone: str) -> dict[str, Any]:
    checked_at = _now_iso()
    try:
        normalized = _normalize_domain(domain, default_zone=default_zone)
    except ValueError as exc:
        return {
            "ok": False,
            "status": "invalid",
            "available": None,
            "error": {"code": "invalid_domain", "message": str(exc)},
            "checked_at": checked_at,
            "source": {"protocol": "WHOIS", "url": WHOIS_INFO_URL},
        }

    try:
        parsed = _parse_whois_output(
            normalized["domain"], _query_whois(normalized["domain"])
        )
    except (OSError, TimeoutError) as exc:
        return {
            "ok": False,
            "status": "unknown",
            "available": None,
            "domain": normalized,
            "error": {
                "code": "whois_unavailable",
                "message": "NIC Argentina WHOIS could not be reached reliably.",
                "detail": type(exc).__name__,
            },
            "checked_at": checked_at,
            "source": {"protocol": "WHOIS", "url": WHOIS_INFO_URL},
        }

    return {
        "ok": parsed["status"] in {"available", "registered"},
        "domain": normalized,
        **parsed,
        "checked_at": checked_at,
        "source": {"protocol": "WHOIS", "host": WHOIS_HOST, "url": WHOIS_INFO_URL},
        "notice": (
            "WHOIS is authoritative for the observed registration state, but availability "
            "can change until the user completes and pays the TAD registration."
        ),
    }


def _http_get_text(url: str) -> str:
    with httpx.Client(
        follow_redirects=True,
        timeout=_HTTP_TIMEOUT_SECONDS,
        headers={"User-Agent": _USER_AGENT},
    ) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.text


def _http_get_json(url: str) -> dict[str, Any]:
    with httpx.Client(
        follow_redirects=True,
        timeout=_HTTP_TIMEOUT_SECONDS,
        headers={"User-Agent": _USER_AGENT},
    ) as client:
        response = client.get(url)
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("The official endpoint returned an unexpected JSON shape.")
    return payload


def _strip_html(value: str) -> str:
    return " ".join(
        unescape(re.sub(r"<[^>]+>", " ", value)).replace("\xa0", " ").split()
    )


def _zone_from_alt(alt: str) -> str | None:
    cleaned = " ".join(unescape(alt).casefold().split()).strip(" .")
    if cleaned == "ar":
        return ".ar"
    labels = [item for item in cleaned.replace(".", " ").split() if item != "punto"]
    candidate = "." + ".".join(labels)
    return candidate if candidate in _KNOWN_ZONES else None


def _parse_amount_ars(value: str) -> int | None:
    digits = re.sub(r"\D", "", value)
    if not digits:
        return None
    amount = int(digits)
    return amount if amount > 0 else None


def _parse_prices_html(document: str) -> dict[str, Any]:
    card_starts = [
        match.start()
        for match in re.finditer(r'<div\s+class="recuadro-domin">', document)
    ]
    prices: list[dict[str, Any]] = []
    for index, start in enumerate(card_starts):
        end = card_starts[index + 1] if index + 1 < len(card_starts) else len(document)
        card = document[start:end]
        alt_match = re.search(
            r'<img\b[^>]*\balt="([^"]+)"', card, flags=re.IGNORECASE
        )
        if alt_match is None:
            continue
        zone = _zone_from_alt(alt_match.group(1))
        if zone is None:
            continue
        plain = _strip_html(card)
        operations: dict[str, dict[str, Any]] = {}
        for label, key in (
            ("ALTA", "registration"),
            ("RENOVACIÓN ANUAL", "annual_renewal"),
            ("TRANSFERENCIA", "transfer"),
        ):
            match = re.search(
                rf"{label}\s+(\$\s*[\d.,]+)", plain, flags=re.IGNORECASE
            )
            if match is None:
                continue
            amount = _parse_amount_ars(match.group(1))
            if amount is not None:
                operations[key] = {
                    "amount_ars": amount,
                    "display": f"${amount:,.0f}".replace(",", "."),
                }
        if "registration" in operations:
            prices.append(
                {
                    "zone": zone,
                    "requires_prior_authorization": zone in _SPECIAL_ZONES,
                    **operations,
                }
            )

    dispute_match = re.search(
        r"disputas?\s+de\s+dominio\s+tienen\s+un\s+valor\s+de\s+(\$\s*[\d.,]+)",
        _strip_html(document),
        flags=re.IGNORECASE,
    )
    dispute_amount = (
        _parse_amount_ars(dispute_match.group(1)) if dispute_match is not None else None
    )
    return {
        "currency": "ARS",
        "prices": sorted(prices, key=lambda item: _KNOWN_ZONES.index(item["zone"])),
        "dispute": (
            {
                "amount_ars": dispute_amount,
                "display": f"${dispute_amount:,.0f}".replace(",", "."),
            }
            if dispute_amount is not None
            else None
        ),
    }


def _get_prices_payload(zone: str | None) -> dict[str, Any]:
    fetched_at = _now_iso()
    normalized_zone: str | None = None
    if zone is not None and zone.strip():
        try:
            normalized_zone = _normalize_zone(zone)
        except ValueError as exc:
            return {
                "ok": False,
                "error": {"code": "invalid_zone", "message": str(exc)},
                "fetched_at": fetched_at,
                "source_url": FEES_URL,
            }
    try:
        parsed = _parse_prices_html(_http_get_text(FEES_URL))
    except (httpx.HTTPError, ValueError) as exc:
        return {
            "ok": False,
            "error": {
                "code": "fees_unavailable",
                "message": "The current official NIC Argentina fees could not be read.",
                "detail": type(exc).__name__,
            },
            "fetched_at": fetched_at,
            "source_url": FEES_URL,
        }
    if not parsed["prices"]:
        return {
            "ok": False,
            "error": {
                "code": "fees_parse_failed",
                "message": "NIC Argentina responded, but its fee table format was not recognized.",
            },
            "fetched_at": fetched_at,
            "source_url": FEES_URL,
        }

    selected = parsed["prices"]
    if normalized_zone is not None:
        selected = [item for item in selected if item["zone"] == normalized_zone]
        if not selected:
            return {
                "ok": False,
                "error": {
                    "code": "zone_fee_not_found",
                    "message": f"No current official price was found for `{normalized_zone}`.",
                },
                "fetched_at": fetched_at,
                "source_url": FEES_URL,
            }
    return {
        "ok": True,
        "currency": parsed["currency"],
        "prices": selected,
        "dispute": parsed["dispute"],
        "fetched_at": fetched_at,
        "source_url": FEES_URL,
        "notice": "Fees are live observations from the official page and may change later.",
    }


def _registration_handoff_payload(provider: str) -> dict[str, Any]:
    fetched_at = _now_iso()
    requested_provider = provider.strip().upper() or "ARCA"
    if requested_provider == "AFIP":
        requested_provider = "ARCA"
    try:
        service_page = _http_get_text(REGISTRATION_SERVICE_URL)
        service_match = re.search(
            r"(?:configuracionInicioTipoTramite/|id_tipo_tramite=)(\d+)",
            service_page,
        )
        if service_match is None:
            raise ValueError("Registration service ID was not found.")
        service_id = service_match.group(1)
        config_url = (
            f"{TAD_BASE_URL}/tad2-rest/tipoTramite/"
            f"configuracionInicioTipoTramite/{service_id}"
        )
        config = _http_get_json(config_url)
        options = config.get("respuesta")
        if not isinstance(options, list):
            raise ValueError("Authentication provider list was not found.")
        providers = [
            item.get("nombre")
            for item in options
            if isinstance(item, dict) and isinstance(item.get("nombre"), str)
        ]
        provider_lookup = {item.upper(): item for item in providers}
        selected_provider = provider_lookup.get(requested_provider)
        if selected_provider is None:
            raise ValueError(
                "The requested authentication provider is not currently offered by TAD."
            )
        registration_url = (
            f"{TAD_BASE_URL}/tramitesadistancia/redireccion"
            f"?accion=INICIAR_TRAMITE&idTipoTramite={service_id}"
            f"&proveedor={quote_plus(selected_provider)}"
        )
    except (httpx.HTTPError, ValueError) as exc:
        return {
            "ok": False,
            "registration_url": REGISTRATION_SERVICE_URL,
            "fallback_url": DOMAIN_SEARCH_URL,
            "error": {
                "code": "tad_handoff_unavailable",
                "message": (
                    "The current direct TAD handoff could not be verified. Use the official "
                    "registration service page instead."
                ),
                "detail": type(exc).__name__,
            },
            "fetched_at": fetched_at,
            "source_url": REGISTRATION_SERVICE_URL,
        }

    return {
        "ok": True,
        "registration_url": registration_url,
        "fallback_url": DOMAIN_SEARCH_URL,
        "service_id": service_id,
        "provider": selected_provider,
        "available_providers": providers,
        "fetched_at": fetched_at,
        "source_url": REGISTRATION_SERVICE_URL,
        "verified_against_tad": True,
    }


def _workflow_manifest() -> dict[str, Any]:
    return {
        "app_id": "nic-ar-domains",
        "purpose": (
            "Prepare .ar domain registrations while keeping fiscal login, legal "
            "confirmation, and payment under direct human control."
        ),
        "recommended_tool": "prepare_ar_registration",
        "tools": [
            "check_ar_domain",
            "get_nic_ar_prices",
            "prepare_ar_registration",
        ],
        "deterministic_tasks": [
            "normalize and validate a registrable .ar domain",
            "query NIC Argentina WHOIS",
            "read the current official fee table",
            "discover the current TAD registration service ID and ARCA handoff URL",
        ],
        "human_only_tasks": [
            "enter fiscal credentials on the official site",
            "choose the represented person or organization",
            "confirm the sworn registration data",
            "select a payment method and pay",
        ],
        "credentials_stored": False,
        "purchase_or_payment_performed": False,
    }


@mcp.tool(
    title="Get NIC Argentina Domain Workflow",
    description=(
        "Return a small static manifest describing which registration work is automated "
        "and which steps always remain under human control."
    ),
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def get_domain_workflow() -> dict[str, Any]:
    return _workflow_manifest()


@mcp.tool(
    title="Check .ar Domain Availability",
    description=(
        "Normalize one registrable .ar domain and query the official NIC Argentina WHOIS "
        "service. Returns available, registered, invalid, or unknown without exposing "
        "registrant personal data. If only a name is supplied, default_zone is appended."
    ),
    annotations=_READ_ONLY_NETWORK,
)
def check_ar_domain(domain: str, default_zone: str = ".com.ar") -> dict[str, Any]:
    return _check_domain_payload(domain, default_zone=default_zone)


@mcp.tool(
    title="Get Current NIC Argentina Fees",
    description=(
        "Read and parse the current official NIC Argentina fee page. Pass a zone such as "
        "`.com.ar` for one price or omit it for all published zones. Never rely on a fee "
        "remembered by the model when this tool is available."
    ),
    annotations=_READ_ONLY_NETWORK,
)
def get_nic_ar_prices(zone: str | None = None) -> dict[str, Any]:
    return _get_prices_payload(zone)


@mcp.tool(
    title="Prepare NIC Argentina Registration",
    description=(
        "Perform the complete read-only preflight for a requested .ar domain: normalize it, "
        "check official WHOIS availability, fetch its current official fee, discover the "
        "current TAD service, and return the verified ARCA handoff URL plus the exact human "
        "steps. This tool never logs in, confirms, buys, or pays."
    ),
    annotations=_READ_ONLY_NETWORK,
)
def prepare_ar_registration(
    domain: str,
    default_zone: str = ".com.ar",
    provider: str = "ARCA",
) -> dict[str, Any]:
    availability = _check_domain_payload(domain, default_zone=default_zone)
    normalized = availability.get("domain")
    zone = normalized.get("zone") if isinstance(normalized, dict) else None
    available = availability.get("available") is True
    if availability.get("status") == "registered":
        decision = "stop_domain_is_registered"
    elif availability.get("status") in {"invalid", "unknown"}:
        decision = "stop_and_resolve_availability"
    else:
        decision = "continue_preflight"

    safety = {
        "requires_human_login": True,
        "requires_human_confirmation": True,
        "requires_human_payment": True,
        "credentials_requested_or_stored": False,
        "purchase_performed": False,
    }
    important = (
        "Availability is a point-in-time observation. The domain is not reserved until "
        "the official TAD registration and payment are completed."
    )
    if not available or not isinstance(zone, str):
        return {
            "ok": False,
            "decision": decision,
            "ready_for_human_handoff": False,
            "availability": availability,
            "fees": None,
            "handoff": None,
            "human_steps": [],
            "safety": safety,
            "important": important,
        }

    with ThreadPoolExecutor(max_workers=2) as executor:
        fees_future = executor.submit(_get_prices_payload, zone)
        handoff_future = executor.submit(_registration_handoff_payload, provider)
        fees = fees_future.result()
        handoff = handoff_future.result()

    fee_ready = fees.get("ok") is True
    handoff_ready = handoff.get("ok") is True
    ready = fee_ready and handoff_ready
    if not fee_ready:
        decision = "stop_and_verify_current_fee"
    elif not handoff_ready:
        decision = "use_official_service_page_fallback"
    else:
        decision = "ready_for_human_registration"

    human_steps: list[dict[str, Any]] = []
    if available:
        human_steps = [
            {"order": 1, "action": "open_official_tad_registration", "url": handoff.get("registration_url")},
            {
                "order": 2,
                "action": "authenticate_with_arca",
                "instruction": "Enter CUIT/CUIL and Clave Fiscal only on the official ARCA/TAD page.",
            },
            {
                "order": 3,
                "action": "choose_identity",
                "instruction": "Choose whether to act personally or for an authorized organization.",
            },
            {
                "order": 4,
                "action": "confirm_domain",
                "domain_to_enter": normalized.get("domain") if isinstance(normalized, dict) else None,
                "instruction": "Confirm the domain and registration data in TAD.",
            },
            {
                "order": 5,
                "action": "pay_in_tad",
                "instruction": "Choose the official payment method and complete payment yourself.",
            },
        ]

    return {
        "ok": ready,
        "decision": decision,
        "ready_for_human_handoff": ready,
        "availability": availability,
        "fees": fees,
        "handoff": handoff,
        "human_steps": human_steps,
        "safety": safety,
        "important": important,
    }


@mcp.resource(
    "nicar://workflow",
    name="NIC Argentina Registration Workflow",
    description="Static safety and responsibility boundaries for .ar registration.",
    mime_type="application/json",
)
def workflow_resource() -> str:
    return json.dumps(_workflow_manifest(), indent=2, sort_keys=True)


@mcp.prompt(
    name="prepare-nic-ar-registration",
    title="Prepare a NIC Argentina Registration",
    description="Use the deterministic preflight before handing registration to the user.",
)
def prepare_registration_prompt(domain: str) -> str:
    return (
        f"Call `prepare_ar_registration` once for `{domain}`. Summarize the observed "
        "availability and current fee, then give the user the returned official TAD URL. "
        "Do not request fiscal credentials and do not claim that the domain was purchased."
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
