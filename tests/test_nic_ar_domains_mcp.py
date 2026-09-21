from __future__ import annotations

from mcp_apps.nic_ar_domains import server


def test_normalize_domain_accepts_name_url_and_special_zone() -> None:
    defaulted = server._normalize_domain("Mi-Marca", default_zone="com.ar")
    from_url = server._normalize_domain(
        "https://Ejemplo.com.ar/landing", default_zone=".com.ar"
    )
    special = server._normalize_domain("fundacion.org.ar", default_zone=".com.ar")

    assert defaulted["domain"] == "mi-marca.com.ar"
    assert defaulted["default_zone_applied"] is True
    assert from_url["domain"] == "ejemplo.com.ar"
    assert from_url["default_zone_applied"] is False
    assert special["zone_requires_prior_authorization"] is True


def test_normalize_domain_rejects_nested_subdomain() -> None:
    try:
        server._normalize_domain("www.example.com.ar")
    except ValueError as exc:
        assert "nested subdomain" in str(exc)
    else:
        raise AssertionError("Nested subdomain should not be accepted as registrable.")


def test_parse_whois_output_distinguishes_available_and_registered() -> None:
    available = server._parse_whois_output(
        "libre.com.ar",
        "El dominio no se encuentra registrado en NIC Argentina",
    )
    registered = server._parse_whois_output(
        "example.com.ar",
        """
domain:\t\texample.com.ar
registrant:\t20999999999
registered:\t2025-01-01 00:00:00
expire:\t\t2027-01-01 00:00:00
nserver:\tns1.example.net ()
""",
    )

    assert available["status"] == "available"
    assert available["available"] is True
    assert registered == {
        "status": "registered",
        "available": False,
        "registered_domain": "example.com.ar",
        "registered_at": "2025-01-01 00:00:00",
        "changed_at": None,
        "expires_at": "2027-01-01 00:00:00",
        "nameservers": ["ns1.example.net"],
    }
    assert "registrant" not in registered


def test_parse_prices_html_returns_structured_ars_amounts() -> None:
    parsed = server._parse_prices_html(
        """
<p>Las disputas de dominio tienen un valor de $28.800.</p>
<div class="recuadro-domin">
  <img alt="punto com punto ar">
  <div class="alta-domin"><b>ALTA</b> $8.500</div>
  <div><b>RENOVACIÓN ANUAL</b><br>$8.500</div>
  <div><b>TRANSFERENCIA</b><br>$8.500</div>
</div>
<div class="recuadro-domin">
  <img alt=".org.ar">
  <div class="alta-domin"><b>ALTA</b> $9.000</div>
  <div><b>RENOVACIÓN ANUAL</b><br>$9.000</div>
  <div><b>TRANSFERENCIA</b><br>$9.000</div>
</div>
"""
    )

    by_zone = {item["zone"]: item for item in parsed["prices"]}
    assert by_zone[".com.ar"]["registration"] == {
        "amount_ars": 8500,
        "display": "$8.500",
    }
    assert by_zone[".org.ar"]["requires_prior_authorization"] is True
    assert parsed["dispute"] == {"amount_ars": 28800, "display": "$28.800"}


def test_registration_handoff_discovers_service_and_provider(monkeypatch) -> None:
    monkeypatch.setattr(
        server,
        "_http_get_text",
        lambda _url: "configuracionInicioTipoTramite/777",
    )
    monkeypatch.setattr(
        server,
        "_http_get_json",
        lambda _url: {
            "respuesta": [
                {"nombre": "NIC NO RESIDENTES"},
                {"nombre": "ARCA"},
            ]
        },
    )

    result = server._registration_handoff_payload("AFIP")

    assert result["ok"] is True
    assert result["service_id"] == "777"
    assert result["provider"] == "ARCA"
    assert "idTipoTramite=777" in result["registration_url"]
    assert "proveedor=ARCA" in result["registration_url"]


def test_prepare_registration_requires_all_deterministic_checks(monkeypatch) -> None:
    monkeypatch.setattr(
        server,
        "_check_domain_payload",
        lambda _domain, default_zone: {
            "ok": True,
            "status": "available",
            "available": True,
            "domain": {"domain": "example.com.ar", "zone": ".com.ar"},
        },
    )
    monkeypatch.setattr(
        server,
        "_get_prices_payload",
        lambda _zone: {
            "ok": True,
            "prices": [
                {
                    "zone": ".com.ar",
                    "registration": {"amount_ars": 8500, "display": "$8.500"},
                }
            ],
        },
    )
    monkeypatch.setattr(
        server,
        "_registration_handoff_payload",
        lambda _provider: {
            "ok": True,
            "registration_url": "https://tramitesadistancia.gob.ar/official",
        },
    )

    result = server.prepare_ar_registration("example.com.ar")

    assert result["ok"] is True
    assert result["decision"] == "ready_for_human_registration"
    assert result["human_steps"][0]["url"].startswith(
        "https://tramitesadistancia.gob.ar/"
    )
    assert result["safety"]["purchase_performed"] is False


def test_prepare_registration_stops_after_registered_whois_result(monkeypatch) -> None:
    monkeypatch.setattr(
        server,
        "_check_domain_payload",
        lambda _domain, default_zone: {
            "ok": True,
            "status": "registered",
            "available": False,
            "domain": {"domain": "example.com.ar", "zone": ".com.ar"},
        },
    )

    def unexpected_call(_value):
        raise AssertionError("Price and TAD lookups must be skipped for a registered domain.")

    monkeypatch.setattr(server, "_get_prices_payload", unexpected_call)
    monkeypatch.setattr(server, "_registration_handoff_payload", unexpected_call)

    result = server.prepare_ar_registration("example.com.ar")

    assert result["ok"] is False
    assert result["decision"] == "stop_domain_is_registered"
    assert result["fees"] is None
    assert result["handoff"] is None
    assert result["human_steps"] == []
