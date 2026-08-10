"""MCP tools: VERI*FACTU — registro, validacion, envio, QR y anulacion.

VERI*FACTU (Real Decreto 1007/2023, Orden HAC/1177/2024):
    XSD v1.0 (SuministroLR.xsd): specs/verifactu/xsd/
    WSDL (RegFactuSistemaFacturacion + ConsultaFactuSistemaFacturacion, same
    endpoint, "sfVerifactu" binding): specs/verifactu/schemas/SistemaFacturacion.wsdl
        Sandbox (personal cert):    https://prewww1.aeat.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP
        Sandbox (Sello cert):       https://prewww10.aeat.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP
        Production (personal cert): https://www1.agenciatributaria.gob.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP
        Production (Sello cert):    https://www10.agenciatributaria.gob.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP
    (Confirmed directly from the WSDL's soap:address entries — the www1/www10
    and prewww1/prewww10 pairs are the personal-certificate vs. Sello
    (company seal) certificate variants of the *same* operation, not a
    primary/secondary failover pair. See VERIFACTU_ENDPOINTS in _helpers.py.)

Namespaces (confirmed from XSD targetNamespace):
    _VF_LR_NS: SuministroLR.xsd   — RegFactuSistemaFacturacion root element
    _VF_SF_NS: SuministroInformacion.xsd — RegistroAlta, RegistroAnulacion, Cabecera, all inner types

Huella (hash chain) — confirmed against Veri-Factu_especificaciones_huella_hash_registros.pdf
v0.1.2 (specs/verifactu/documentation/), algorithm SHA-256, output hex uppercase (64 chars):
    RegistroAlta:      IDEmisorFactura=...&NumSerieFactura=...&FechaExpedicionFactura=...&
                        TipoFactura=...&CuotaTotal=...&ImporteTotal=...&Huella=...&
                        FechaHoraHusoGenRegistro=...
    RegistroAnulacion: IDEmisorFacturaAnulada=...&NumSerieFacturaAnulada=...&
                        FechaExpedicionFacturaAnulada=...&Huella=...&FechaHoraHusoGenRegistro=...
    (campo=valor pairs joined by "&", in this exact field order; empty Huella= for
    the genesis record. Golden vectors from the spec's worked examples are in
    test_verifactu.py.)

EncadenamientoFacturaAnteriorType (SuministroInformacion.xsd) — 4 required fields:
    IDEmisorFactura, NumSerieFactura, FechaExpedicionFactura, Huella
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any
from urllib.parse import quote_plus

import mcp.types as types
from lxml import etree
from mcp_einvoicing_core.base_server import assert_not_read_only
from mcp_einvoicing_core.confirmation import ConfirmationGate
from mcp_einvoicing_core.exceptions import EInvoicingError
from mcp_einvoicing_core.models import InvoiceDocument
from mcp_einvoicing_core.qr import generate_qr_png_base64
from mcp_einvoicing_core.signer_client import SignerClient
from mcp_einvoicing_core.xml_utils import safe_fromstring

from mcp_facturacion_electronica_es._helpers import (
    VERIFACTU_CONSULTA_ENDPOINTS,
    VERIFACTU_ENDPOINTS,
    VERIFACTU_QR_ENDPOINTS,
    aeat_env,
    err,
    fmt_amount,
    fmt_date_es,
    ok,
    parse_invoice,
)
from mcp_facturacion_electronica_es.config import aeat_settings
from mcp_facturacion_electronica_es.models.es import VerifactuInvoiceType

logger = logging.getLogger(__name__)

# ES-SC-7: Namespaces confirmed from specs/verifactu/xsd/ targetNamespace attributes
# SuministroLR.xsd: root envelope element RegFactuSistemaFacturacion
_VF_LR_NS = (
    "https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones"
    "/es/aeat/tike/cont/ws/SuministroLR.xsd"
)
# SuministroInformacion.xsd: RegistroAlta, RegistroAnulacion, Cabecera, and all inner types
_VF_SF_NS = (
    "https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones"
    "/es/aeat/tike/cont/ws/SuministroInformacion.xsd"
)
# ConsultaLR.xsd: ConsultaFactuSistemaFacturacion request root, Cabecera and
# FiltroConsulta wrappers (their leaf fields are in SuministroInformacion namespace)
_VF_CONSULTA_NS = (
    "https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones"
    "/es/aeat/tike/cont/ws/ConsultaLR.xsd"
)

_VERIFACTU_VERSION = "1.0"
# IdSistemaInformatico is TextMax2Type in SuministroInformacion.xsd — max 2 characters
_SOFTWARE_ID_CODE = "ES"


# ---------------------------------------------------------------------------
# XML builder helpers
# ---------------------------------------------------------------------------


def _el(tag: str, text: str | None = None, **attribs: str) -> etree._Element:
    """Create a namespace-qualified VeriFactu element (SuministroInformacion namespace)."""
    elem = etree.Element(f"{{{_VF_SF_NS}}}{tag}")
    if text is not None:
        elem.text = text
    for k, v in attribs.items():
        elem.set(k, v)
    return elem


def _sub(parent: etree._Element, tag: str, text: str | None = None) -> etree._Element:
    """Append a namespace-qualified child element (SuministroInformacion namespace)."""
    child = etree.SubElement(parent, f"{{{_VF_SF_NS}}}{tag}")
    if text is not None:
        child.text = text
    return child


def _build_id_factura(
    num_serie: str,
    emisor_nif: str,
    fecha_es: str,
) -> etree._Element:
    """Build the top-level <IDFactura> block for a RegistroAlta.

    Element names per IDFacturaExpedidaType (SuministroInformacion.xsd).
    """
    idf = _el("IDFactura")
    _sub(idf, "IDEmisorFactura", emisor_nif)
    _sub(idf, "NumSerieFactura", num_serie)
    _sub(idf, "FechaExpedicionFactura", fecha_es)
    return idf


def _build_id_factura_anulada(
    num_serie: str,
    emisor_nif: str,
    fecha_es: str,
) -> etree._Element:
    """Build the top-level <IDFactura> block for a RegistroAnulacion.

    Element names per IDFacturaExpedidaBajaType (SuministroInformacion.xsd) —
    distinct from RegistroAlta's IDFacturaExpedidaType, using the "*Anulada"
    suffix: IDEmisorFacturaAnulada, NumSerieFacturaAnulada,
    FechaExpedicionFacturaAnulada. A prior implementation reused
    _build_id_factura (the RegistroAlta element names) here, which is
    structurally invalid against the XSD — same root cause as the
    RegistroAnulacion huella field-name bug (see _compute_huella_anulacion).
    """
    idf = _el("IDFactura")
    _sub(idf, "IDEmisorFacturaAnulada", emisor_nif)
    _sub(idf, "NumSerieFacturaAnulada", num_serie)
    _sub(idf, "FechaExpedicionFacturaAnulada", fecha_es)
    return idf


def _compute_huella(
    emisor_nif: str,
    num_serie: str,
    fecha_es: str,
    tipo_factura: str,
    cuota_total: str,
    importe_total: str,
    fecha_hora_gen: str,
    huella_anterior: str | None,
) -> str:
    """Compute the VERI*FACTU RegistroAlta Huella (hash chain link).

    Per the confirmed AEAT keyed canonical form (ES-SC-10; see
    specs/verifactu/documentation/verifactu-technical-reference.md s1):
    SHA-256 of ``campo=valor`` pairs joined by ``&``, in this exact order.
    ``Huella`` carries the previous record's huella hex string; for the first
    (genesis) record in a chain the field is still present with an empty
    value, not omitted. Returns uppercase hexadecimal (64 characters).
    """
    parts = [
        f"IDEmisorFactura={emisor_nif}",
        f"NumSerieFactura={num_serie}",
        f"FechaExpedicionFactura={fecha_es}",
        f"TipoFactura={tipo_factura}",
        f"CuotaTotal={cuota_total}",
        f"ImporteTotal={importe_total}",
        f"Huella={huella_anterior or ''}",
        f"FechaHoraHusoGenRegistro={fecha_hora_gen}",
    ]
    raw = "&".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()


def _compute_huella_anulacion(
    emisor_nif: str,
    num_serie: str,
    fecha_es: str,
    fecha_hora_gen: str,
    huella_anterior: str | None,
) -> str:
    """Compute the Huella for a RegistroAnulacion (cancellation) record.

    Per the official AEAT huella spec (Veri-Factu_especificaciones_huella_hash_registros.pdf
    v0.1.2 s3.b, see specs/verifactu/documentation/), the RegistroAnulacion field
    set uses the "*Anulada" field names — distinct from the RegistroAlta field
    names, not a reduced copy of them:
    IDEmisorFacturaAnulada, NumSerieFacturaAnulada, FechaExpedicionFacturaAnulada,
    Huella, FechaHoraHusoGenRegistro. Verified against the AEAT worked example in
    s6.3 of that document (golden vector reproduced in test_verifactu.py).

    A prior implementation used the *alta* field names for this reduced set
    (``IDEmisorFactura``/``NumSerieFactura``/``FechaExpedicionFactura``), and
    before that, reused the full alta canonical string with
    ``TipoFactura="ANULACION"`` and ``CuotaTotal="0.00"``. Both produce a huella
    that AEAT would reject as "Aceptado con errores" (spec s7).
    """
    parts = [
        f"IDEmisorFacturaAnulada={emisor_nif}",
        f"NumSerieFacturaAnulada={num_serie}",
        f"FechaExpedicionFacturaAnulada={fecha_es}",
        f"Huella={huella_anterior or ''}",
        f"FechaHoraHusoGenRegistro={fecha_hora_gen}",
    ]
    raw = "&".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()


def _build_registro_alta(
    invoice: InvoiceDocument,
    invoice_type: str,
    software_id: str,
    software_nif: str,
    previous_hash: str | None,
    fecha_hora_gen: str,
    previous_emisor_nif: str | None = None,
    previous_num_serie: str | None = None,
    previous_fecha: str | None = None,
    clave_regimen: str = "01",
    impuesto: str = "01",
    calificacion_operacion: str = "S1",
    recargo_equivalencia_rate: Decimal | None = None,
    recargo_equivalencia_amount: Decimal | None = None,
) -> tuple[etree._Element, str]:
    """Build the RegistroAlta element and return (element, huella).

    Returns:
        (RegistroAlta element, Huella hex string)
    """
    seller_nif = invoice.seller.tax_id.identifier
    seller_name = invoice.seller.display_name
    buyer = invoice.buyer
    num_serie = invoice.number
    fecha_es = fmt_date_es(invoice.date)

    # Compute totals from vat_summary
    cuota_total = fmt_amount(sum((v.vat_amount for v in invoice.vat_summary), Decimal("0")))
    importe_total = fmt_amount(
        sum(
            (v.taxable_base + v.vat_amount for v in invoice.vat_summary),
            Decimal("0"),
        )
    )

    huella = _compute_huella(
        emisor_nif=seller_nif,
        num_serie=num_serie,
        fecha_es=fecha_es,
        tipo_factura=invoice_type,
        cuota_total=cuota_total,
        importe_total=importe_total,
        fecha_hora_gen=fecha_hora_gen,
        huella_anterior=previous_hash,
    )

    ra = _el("RegistroAlta")
    _sub(ra, "IDVersion", _VERIFACTU_VERSION)

    ra.append(_build_id_factura(num_serie, seller_nif, fecha_es))

    _sub(ra, "NombreRazonEmisor", seller_name)
    _sub(ra, "Subsanacion", "N")
    _sub(ra, "RechazoPrevio", "N")
    _sub(ra, "TipoFactura", invoice_type)

    # DescripcionOperacion
    desc = invoice.note or "Prestación de servicios / entrega de bienes"
    _sub(ra, "DescripcionOperacion", desc[:500])

    # Destinatarios
    dest_elem = _sub(ra, "Destinatarios")
    id_dest = _sub(dest_elem, "IDDestinatario")
    _sub(id_dest, "NombreRazon", buyer.display_name)
    if buyer.tax_id.country_code.upper() == "ES":
        _sub(id_dest, "NIF", buyer.tax_id.identifier)
    else:
        id_osp = _sub(id_dest, "IDOtro")
        _sub(id_osp, "CodigoPais", buyer.tax_id.country_code.upper())
        _sub(id_osp, "IDType", "07")  # passaporte/doc extranjero
        _sub(id_osp, "ID", buyer.tax_id.identifier)

    _sub(ra, "Cupon", "N")

    # Desglose IVA
    desglose = _sub(ra, "Desglose")
    desglose_iva = _sub(desglose, "DesgloseIVA")
    for vat in invoice.vat_summary:
        detail = _sub(desglose_iva, "DetalleIVA")
        _sub(detail, "Impuesto", impuesto)
        _sub(detail, "ClaveRegimen", clave_regimen)
        _sub(detail, "CalificacionOperacion", calificacion_operacion)
        _sub(detail, "TipoImpositivo", fmt_amount(vat.vat_rate))
        _sub(detail, "BaseImponibleOImporteNoSujeto", fmt_amount(vat.taxable_base))
        _sub(detail, "CuotaRepercutida", fmt_amount(vat.vat_amount))
        if recargo_equivalencia_rate is not None:
            _sub(detail, "TipoRecargoEquivalencia", fmt_amount(recargo_equivalencia_rate))
            re_amount = recargo_equivalencia_amount or (
                vat.taxable_base * recargo_equivalencia_rate / Decimal("100")
            )
            _sub(detail, "CuotaRecargoEquivalencia", fmt_amount(re_amount))

    _sub(ra, "CuotaTotal", cuota_total)
    _sub(ra, "ImporteTotal", importe_total)

    # Encadenamiento — ES-LC-4: EncadenamientoFacturaAnteriorType requires all 4 fields
    enc = _sub(ra, "Encadenamiento")
    if previous_hash:
        _sub(enc, "PrimerRegistro", "N")
        reg_ant = _sub(enc, "RegistroAnterior")
        # EncadenamientoFacturaAnteriorType (SuministroInformacion.xsd):
        # IDEmisorFactura + NumSerieFactura + FechaExpedicionFactura + Huella — all required
        _sub(reg_ant, "IDEmisorFactura", previous_emisor_nif or seller_nif)
        _sub(reg_ant, "NumSerieFactura", previous_num_serie or "")
        _sub(reg_ant, "FechaExpedicionFactura", previous_fecha or fecha_es)
        _sub(reg_ant, "Huella", previous_hash)
    else:
        _sub(enc, "PrimerRegistro", "S")

    # SistemaInformatico — IdSistemaInformatico is TextMax2Type (max 2 chars per XSD)
    si = _sub(ra, "SistemaInformatico")
    _sub(si, "NombreRazon", seller_name)
    _sub(si, "NIF", software_nif)
    _sub(si, "NombreSistemaInformatico", "mcp-facturacion-electronica-es")
    _sub(si, "IdSistemaInformatico", software_id[:2] if software_id else _SOFTWARE_ID_CODE)
    _sub(si, "Version", "0.1.0")
    _sub(si, "NumeroInstalacion", "001")
    _sub(si, "TipoUsoPosibleSoloVerifactu", "S")
    _sub(si, "TipoUsoPosibleMultiOT", "N")
    _sub(si, "IndicadorMultiplesOT", "N")

    _sub(ra, "FechaHoraHusoGenRegistro", fecha_hora_gen)
    # TipoHuella must be "01" (SHA-256) per TipoHuellaType enumeration in SuministroInformacion.xsd
    _sub(ra, "TipoHuella", "01")
    _sub(ra, "Huella", huella)

    # [NEED: AEAT XAdES profile clarification for VeriFactu record signing]
    # ES-SC-12: AEAT has not published a canonical XAdES signing profile for
    # the RegistroAlta XML itself (distinct from the SOAP envelope mTLS).
    # The record is submitted unsigned; XAdES signing deferred to v0.3.1
    # pending AEAT technical publication.

    return ra, huella


def _wrap_registro_facturacion(
    emisor_nif: str,
    emisor_name: str,
    inner: etree._Element,
) -> bytes:
    """Wrap a RegistroAlta or RegistroAnulacion in the RegFactuSistemaFacturacion envelope.

    ES-SC-7: RegFactuSistemaFacturacion is in SuministroLR namespace;
    Cabecera and inner record types are in SuministroInformacion namespace.
    """
    nsmap = {
        "sfLR": _VF_LR_NS,
        "sf": _VF_SF_NS,
    }
    root = etree.Element(f"{{{_VF_LR_NS}}}RegFactuSistemaFacturacion", nsmap=nsmap)
    # Cabecera and its children are in SuministroInformacion namespace
    cab = etree.SubElement(root, f"{{{_VF_SF_NS}}}Cabecera")
    oblig = etree.SubElement(cab, f"{{{_VF_SF_NS}}}ObligadoEmision")
    etree.SubElement(oblig, f"{{{_VF_SF_NS}}}NombreRazonSocial").text = emisor_name
    etree.SubElement(oblig, f"{{{_VF_SF_NS}}}NIF").text = emisor_nif
    # RegistroFactura wrapper (SuministroLR namespace), contains RegistroAlta/Anulacion
    reg_factura = etree.SubElement(root, f"{{{_VF_LR_NS}}}RegistroFactura")
    reg_factura.append(inner)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)


def _build_consulta_lr(
    nif: str,
    name: str,
    fiscal_year: int,
    period: str,
    num_serie_factura: str | None = None,
) -> bytes:
    """Build a ConsultaFactuSistemaFacturacion request (ConsultaLR.xsd).

    Used by es__query_verifactu_status to re-query a record's EstadoRegistro
    after a `deferred` (TiempoEsperaEnvio) result from
    es__submit_verifactu_to_aeat.

    [Inference] Element namespace qualification (Cabecera/FiltroConsulta/
    PeriodoImputacion/NumSerieFactura in the ConsultaLR namespace; their leaf
    fields in the SuministroInformacion namespace) was verified by validating
    the generated XML against the bundled specs/verifactu/xsd/ConsultaLR.xsd
    locally (2026-08-08). Not yet confirmed against a live AEAT sandbox
    acknowledgement.
    """
    nsmap = {"sfLRC": _VF_CONSULTA_NS, "sf": _VF_SF_NS}
    root = etree.Element(f"{{{_VF_CONSULTA_NS}}}ConsultaFactuSistemaFacturacion", nsmap=nsmap)

    cab = etree.SubElement(root, f"{{{_VF_CONSULTA_NS}}}Cabecera")
    etree.SubElement(cab, f"{{{_VF_SF_NS}}}IDVersion").text = _VERIFACTU_VERSION
    oblig = etree.SubElement(cab, f"{{{_VF_SF_NS}}}ObligadoEmision")
    etree.SubElement(oblig, f"{{{_VF_SF_NS}}}NombreRazon").text = name
    etree.SubElement(oblig, f"{{{_VF_SF_NS}}}NIF").text = nif

    filtro = etree.SubElement(root, f"{{{_VF_CONSULTA_NS}}}FiltroConsulta")
    periodo = etree.SubElement(filtro, f"{{{_VF_CONSULTA_NS}}}PeriodoImputacion")
    etree.SubElement(periodo, f"{{{_VF_SF_NS}}}Ejercicio").text = str(fiscal_year)
    etree.SubElement(periodo, f"{{{_VF_SF_NS}}}Periodo").text = period
    if num_serie_factura:
        etree.SubElement(filtro, f"{{{_VF_CONSULTA_NS}}}NumSerieFactura").text = num_serie_factura

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)


# ---------------------------------------------------------------------------
# Chain (re-encadenamiento) contract helpers — ES-LC-12
# ---------------------------------------------------------------------------

#: EstadoRegistroType values (RespuestaSuministro.xsd) that mean AEAT *stored*
#: the record under the Huella it was submitted with — safe to chain the next
#: record's previous_hash from. "AceptadoConErrores" still counts: per the
#: AEAT huella spec s7, a huella mismatch alone produces this status, not
#: "Incorrecto" — the record and its Huella both exist in AEAT's registry.
_CHAIN_SAFE_ESTADOS = frozenset({"Correcto", "AceptadoConErrores"})


def _extract_chain_identity(xml_bytes: bytes) -> dict[str, str] | None:
    """Extract the (emisor_nif, num_serie, fecha, huella) identity of the
    RegistroAlta/RegistroAnulacion just submitted, for use as the next
    record's previous_hash/previous_emisor_nif/previous_num_serie/
    previous_fecha — but only once the caller has confirmed AEAT accepted it
    (see _CHAIN_SAFE_ESTADOS and handle_es_submit_verifactu_to_aeat).

    Scoped to the RegistroAlta/RegistroAnulacion element's *direct* IDFactura
    and Huella children — not the same-named fields inside
    Encadenamiento/RegistroAnterior, which describe the *previous* record.
    Returns None if the XML cannot be parsed or matched (best-effort; callers
    must not fail the submission over this).
    """
    try:
        root = safe_fromstring(xml_bytes)
    except etree.XMLSyntaxError:
        return None

    anulacion = root.xpath(".//*[local-name()='RegistroAnulacion']")
    if anulacion:
        registro = anulacion[0]
        emisor_tag, serie_tag, fecha_tag = (
            "IDEmisorFacturaAnulada",
            "NumSerieFacturaAnulada",
            "FechaExpedicionFacturaAnulada",
        )
    else:
        alta = root.xpath(".//*[local-name()='RegistroAlta']")
        if not alta:
            return None
        registro = alta[0]
        emisor_tag, serie_tag, fecha_tag = (
            "IDEmisorFactura",
            "NumSerieFactura",
            "FechaExpedicionFactura",
        )

    def _direct_child_text(parent: etree._Element, path: str) -> str | None:
        elems = parent.xpath(f"./*[local-name()='IDFactura']/*[local-name()='{path}']")
        if elems and elems[0].text:
            return elems[0].text
        return None

    emisor_nif = _direct_child_text(registro, emisor_tag)
    num_serie = _direct_child_text(registro, serie_tag)
    fecha = _direct_child_text(registro, fecha_tag)
    huella_elems = registro.xpath("./*[local-name()='Huella']")
    huella = huella_elems[0].text if huella_elems and huella_elems[0].text else None

    if not all([emisor_nif, num_serie, fecha, huella]):
        return None
    return {
        "emisor_nif": emisor_nif,
        "num_serie": num_serie,
        "fecha": fecha,
        "huella": huella,
    }


def _build_chain_result(
    parsed_response: dict[str, Any],
    xml_bytes: bytes,
) -> dict[str, Any]:
    """Build the ``chain`` block returned by handle_es_submit_verifactu_to_aeat.

    Enforces the accepted-only chain contract: the identity to use as the
    *next* record's previous_hash/previous_emisor_nif/previous_num_serie/
    previous_fecha is only surfaced when this record's EstadoRegistro is
    Correcto or AceptadoConErrores. A deferred (async) result or an
    Incorrecto/missing status means the caller must not chain from this
    record — either poll es__query_verifactu_status first, or fall back to
    the last previously-accepted record's identity.
    """
    estado = parsed_response.get("EstadoRegistro")
    if parsed_response.get("status") == "deferred":
        return {
            "accepted": None,
            "safe_to_chain_from": None,
            "note": (
                "Result deferred by AEAT (TiempoEsperaEnvio) — call "
                "es__query_verifactu_status before deciding whether to chain "
                "the next record from this one."
            ),
        }
    if estado in _CHAIN_SAFE_ESTADOS:
        identity = _extract_chain_identity(xml_bytes)
        if identity is not None:
            return {"accepted": True, "safe_to_chain_from": identity}
        return {
            "accepted": True,
            "safe_to_chain_from": None,
            "note": "Accepted by AEAT, but the record identity could not be re-parsed from the submitted XML.",
        }
    return {
        "accepted": False,
        "safe_to_chain_from": None,
        "warning": (
            f"This record was not accepted by AEAT (EstadoRegistro={estado!r}). "
            "Do not use its Huella as previous_hash for the next record — chain "
            "from the last record AEAT actually accepted instead."
        ),
    }


def _parse_verifactu_response(raw: str) -> dict[str, Any]:
    """Parse an AEAT VERI*FACTU response, extract key fields without echoing raw XML.

    ES-SH-2: Raw AEAT responses must not be relayed to the LLM. Only structured
    key fields are returned: EstadoEnvio, CSV, CodigoErrorRegistro, DescripcionErrorRegistro.
    ES-LC-5: Detect TiempoEsperaEnvio deferral signal.
    """
    result: dict[str, Any] = {}
    if not raw:
        return result
    try:
        root = safe_fromstring(raw.encode())
        for field in [
            "EstadoEnvio",
            "CSV",
            "CodigoErrorRegistro",
            "DescripcionErrorRegistro",
            "EstadoRegistro",
        ]:
            elems = root.xpath(f".//*[local-name()='{field}']")
            if elems:
                result[field] = elems[0].text

        # ES-LC-5: detect TiempoEsperaEnvio deferral
        espera_elems = root.xpath(".//*[local-name()='TiempoEsperaEnvio']")
        if espera_elems and espera_elems[0].text:
            try:
                retry_seconds = int(espera_elems[0].text)
                result["status"] = "deferred"
                result["retry_after_seconds"] = retry_seconds
            except ValueError:
                pass
    except Exception as exc:
        result["parse_error"] = f"Could not parse AEAT response: {exc}"
    return result


def _parse_consulta_lr_response(raw: str) -> dict[str, Any]:
    """Parse an AEAT ConsultaLR response (RespuestaConsultaLR.xsd) without
    echoing raw XML to the LLM (ES-SH-2 pattern).

    Surfaces ResultadoConsulta plus, for each returned record, IDFactura and
    the EstadoRegistro block (EstadoRegistro: Correcto / AceptadoConErrores /
    Anulado, TimestampUltimaModificacion, CodigoErrorRegistro,
    DescripcionErrorRegistro).
    """
    result: dict[str, Any] = {}
    if not raw:
        return result
    try:
        root = safe_fromstring(raw.encode())

        resultado = root.xpath(".//*[local-name()='ResultadoConsulta']")
        if resultado:
            result["resultado_consulta"] = resultado[0].text

        registros: list[dict[str, Any]] = []
        for reg in root.xpath(
            ".//*[local-name()='RegistroRespuestaConsultaFactuSistemaFacturacion']"
        ):
            entry: dict[str, Any] = {}

            id_factura = reg.xpath("./*[local-name()='IDFactura']")
            if id_factura:
                for field in ("IDEmisorFactura", "NumSerieFactura", "FechaExpedicionFactura"):
                    vals = id_factura[0].xpath(f"./*[local-name()='{field}']")
                    if vals:
                        entry[field] = vals[0].text

            # EstadoRegistro is the direct-child wrapper block; it contains its
            # own inner EstadoRegistro leaf with the same local-name; use the
            # child axis (not //) at each step to avoid matching the wrong one.
            estado_blocks = reg.xpath("./*[local-name()='EstadoRegistro']")
            if estado_blocks:
                block = estado_blocks[0]
                for field in (
                    "TimestampUltimaModificacion",
                    "EstadoRegistro",
                    "CodigoErrorRegistro",
                    "DescripcionErrorRegistro",
                ):
                    vals = block.xpath(f"./*[local-name()='{field}']")
                    if vals:
                        entry[field] = vals[0].text

            registros.append(entry)
        if registros:
            result["registros"] = registros
    except Exception as exc:
        result["parse_error"] = f"Could not parse AEAT response: {exc}"
    return result


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TOOL_ES_GENERATE_VERIFACTU_RECORD = types.Tool(
    name="es__generate_verifactu_record",
    description=(
        "Genera un registro de factura VERI*FACTU (Orden HAC/1177/2024) con cadena SHA-256 Huella. "
        "Devuelve el XML del registro y la Huella para encadenar con el siguiente registro. "
        "Llame a es__detect_regional_regime antes para confirmar que el régimen es VERIFACTU."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "invoice": {
                "type": "object",
                "description": "Datos de la factura (date, number, seller, buyer, vat_summary, note).",
            },
            "previous_hash": {
                "type": "string",
                "description": "Huella SHA-256 del registro precedente (omitir o null para el primero).",
            },
            "previous_emisor_nif": {
                "type": "string",
                "description": "NIF del emisor del registro anterior (requerido si previous_hash está presente).",
            },
            "previous_num_serie": {
                "type": "string",
                "description": "NumSerieFactura del registro anterior (requerido si previous_hash está presente).",
            },
            "previous_fecha": {
                "type": "string",
                "description": "FechaExpedicionFactura del registro anterior en DD-MM-YYYY (requerido si previous_hash está presente).",
            },
            "software_id": {
                "type": "string",
                "description": "IDSistemaInformatico del software certificado.",
            },
            "software_nif": {
                "type": "string",
                "description": "NIF del fabricante del software.",
            },
            "invoice_type": {
                "type": "string",
                "enum": ["F1", "F2", "F3", "R1", "R2", "R3", "R4", "R5"],
                "description": "TipoFactura según HAC/1177/2024 Annex I.",
            },
        },
        "required": ["invoice", "software_id", "software_nif", "invoice_type"],
    },
)

TOOL_ES_VALIDATE_VERIFACTU_RECORD = types.Tool(
    name="es__validate_verifactu_record",
    description=(
        "Valida un registro VERI*FACTU XML. Realiza validación estructural y, si el XSD v1.0 "
        "(HAC/1177/2024) está disponible en specs/verifactu/, también validación de esquema."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "xml": {"type": "string", "description": "Registro VERI*FACTU XML en crudo."},
            "schema_version": {
                "type": "string",
                "description": "Versión del esquema XSD (por defecto: '1.0').",
                "default": "1.0",
            },
        },
        "required": ["xml"],
    },
)

TOOL_ES_SUBMIT_VERIFACTU_TO_AEAT = types.Tool(
    name="es__submit_verifactu_to_aeat",
    description=(
        "Envía un registro VERI*FACTU firmado al endpoint en tiempo real de la AEAT mediante MTLS "
        "(certificado FNMT-RCM). Requiere AEAT_ENV, AEAT_CERTIFICATE_PATH y AEAT_CERTIFICATE_PASSWORD. "
        "Si la respuesta trae parsed_response.status == 'deferred' (TiempoEsperaEnvio), espere "
        "retry_after_seconds y llame a es__query_verifactu_status para confirmar el EstadoRegistro "
        "final antes de encadenar el siguiente registro."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "xml": {"type": "string", "description": "Registro VERI*FACTU XML firmado."},
            "nif": {"type": "string", "description": "NIF del remitente."},
        },
        "required": ["xml", "nif"],
    },
)

TOOL_ES_QUERY_VERIFACTU_STATUS = types.Tool(
    name="es__query_verifactu_status",
    description=(
        "Consulta el EstadoRegistro de un registro VERI*FACTU ya enviado "
        "(ConsultaFactuSistemaFacturacion / ConsultaLR.xsd). Use esta tool tras un resultado "
        "'deferred' de es__submit_verifactu_to_aeat, esperando retry_after_seconds, para "
        "confirmar el estado final (Correcto / AceptadoConErrores / Anulado) antes de "
        "encadenar el siguiente registro. Requiere AEAT_ENV, AEAT_CERTIFICATE_PATH y "
        "AEAT_CERTIFICATE_PASSWORD, igual que es__submit_verifactu_to_aeat."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "nif": {"type": "string", "description": "NIF del obligado a la emisión (ObligadoEmision)."},
            "name": {"type": "string", "description": "Nombre/razón social del obligado a la emisión."},
            "invoice_date": {
                "type": "string",
                "description": "Fecha de la factura consultada, YYYY-MM-DD (determina PeriodoImputacion).",
            },
            "num_serie_factura": {
                "type": "string",
                "description": "NumSerieFactura a filtrar (omitir para consultar todo el período).",
            },
        },
        "required": ["nif", "name", "invoice_date"],
    },
)

TOOL_ES_GENERATE_QR_VERIFACTU = types.Tool(
    name="es__generate_qr_verifactu",
    description=(
        "Genera el código QR obligatorio VERI*FACTU (HAC/1177/2024 Art. 10) como PNG en base64. "
        "Encodes la URL de verificación de la AEAT: "
        "https://www2.agenciatributaria.gob.es/wlpl/TIKE-CONT/ValidarQR?..."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "nif": {"type": "string", "description": "NIF del emisor."},
            "invoice_number": {"type": "string", "description": "NumSerieFactura."},
            "invoice_date": {
                "type": "string",
                "description": "FechaExpedicionFactura en YYYY-MM-DD.",
            },
            "total_amount": {
                "type": "number",
                "description": "ImporteTotal de la factura (con IVA incluido).",
            },
            "size_px": {
                "type": "integer",
                "description": "Tamaño del QR en píxeles (por defecto: 200).",
                "default": 200,
            },
        },
        "required": ["nif", "invoice_number", "invoice_date", "total_amount"],
    },
)

TOOL_ES_CANCEL_VERIFACTU_RECORD = types.Tool(
    name="es__cancel_verifactu_record",
    description=(
        "Genera un registro de anulacion VERI*FACTU (TipoHuella=01) "
        "encadenado a la secuencia de huellas actual."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "original_invoice_number": {
                "type": "string",
                "description": "NumSerieFactura a anular.",
            },
            "original_invoice_date": {
                "type": "string",
                "description": "FechaExpedicionFactura original (YYYY-MM-DD).",
            },
            "issuer_nif": {"type": "string", "description": "NIF del emisor."},
            "issuer_name": {"type": "string", "description": "Nombre/razon social del emisor."},
            "previous_hash": {
                "type": "string",
                "description": "Huella del ultimo registro en la cadena.",
            },
            "previous_emisor_nif": {
                "type": "string",
                "description": "NIF del emisor del registro anterior (IDEmisorFactura en EncadenamientoFacturaAnteriorType).",
            },
            "previous_num_serie": {
                "type": "string",
                "description": "NumSerieFactura del registro anterior.",
            },
            "previous_fecha": {
                "type": "string",
                "description": "FechaExpedicionFactura del registro anterior en DD-MM-YYYY.",
            },
        },
        "required": [
            "original_invoice_number",
            "original_invoice_date",
            "issuer_nif",
            "issuer_name",
            "previous_hash",
        ],
    },
)

# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def handle_es_generate_verifactu_record(
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    try:
        invoice_data = arguments.get("invoice")
        if not invoice_data:
            return err("invoice is required", "MISSING_PARAM")

        invoice = parse_invoice(invoice_data)
        invoice_type = arguments.get("invoice_type", "F1")
        software_id = arguments.get("software_id", "")
        software_nif = arguments.get("software_nif", "")
        previous_hash: str | None = arguments.get("previous_hash") or None
        previous_emisor_nif: str | None = arguments.get("previous_emisor_nif") or None
        previous_num_serie: str | None = arguments.get("previous_num_serie") or None
        previous_fecha: str | None = arguments.get("previous_fecha") or None
        clave_regimen: str = arguments.get("clave_regimen", "01")
        impuesto: str = arguments.get("impuesto", "01")
        calificacion_operacion: str = arguments.get("calificacion_operacion", "S1")

        try:
            VerifactuInvoiceType(invoice_type)
        except ValueError:
            return err(f"Invalid invoice_type: {invoice_type!r}")

        if not software_id:
            return err("software_id is required", "MISSING_PARAM")
        if not software_nif:
            return err("software_nif is required", "MISSING_PARAM")

        # ES-LC-4: EncadenamientoFacturaAnteriorType requires IDEmisorFactura,
        # NumSerieFactura, FechaExpedicionFactura + Huella — all 4 mandatory.
        chain_warnings: list[str] = []
        if previous_hash and not all([previous_emisor_nif, previous_num_serie, previous_fecha]):
            chain_warnings.append(
                "previous_hash provided without previous_emisor_nif / previous_num_serie / "
                "previous_fecha: EncadenamientoFacturaAnteriorType requires all 4 fields "
                "(IDEmisorFactura, NumSerieFactura, FechaExpedicionFactura, Huella). "
                "Falling back to current invoice identity for missing prior-record fields — "
                "provide the previous invoice identity for a fully conformant chain."
            )

        # Timestamp: ISO 8601 with local timezone (AEAT requires timezone offset)
        now = datetime.now().astimezone()
        fecha_hora_gen = now.strftime("%Y-%m-%dT%H:%M:%S%z")
        # Insert colon in timezone: +0100 → +01:00
        if len(fecha_hora_gen) > 19 and ":" not in fecha_hora_gen[-6:]:
            fecha_hora_gen = fecha_hora_gen[:-2] + ":" + fecha_hora_gen[-2:]

        ra, huella = _build_registro_alta(
            invoice=invoice,
            invoice_type=invoice_type,
            software_id=software_id,
            software_nif=software_nif,
            previous_hash=previous_hash,
            fecha_hora_gen=fecha_hora_gen,
            previous_emisor_nif=previous_emisor_nif,
            previous_num_serie=previous_num_serie,
            previous_fecha=previous_fecha,
            clave_regimen=clave_regimen,
            impuesto=impuesto,
            calificacion_operacion=calificacion_operacion,
        )

        xml_bytes = _wrap_registro_facturacion(
            emisor_nif=invoice.seller.tax_id.identifier,
            emisor_name=invoice.seller.display_name,
            inner=ra,
        )

        logger.info(
            "VERI*FACTU record generated: %s / %s → huella=%s...",
            invoice.seller.tax_id.identifier,
            invoice.number,
            huella[:16],
        )

        result: dict[str, Any] = {
            "xml": xml_bytes.decode("utf-8"),
            "huella": huella,
            "fecha_hora_gen": fecha_hora_gen,
            "invoice_id": {
                "emisor_nif": invoice.seller.tax_id.identifier,
                "num_serie": invoice.number,
                "fecha": fmt_date_es(invoice.date),
            },
            "note": (
                "Sign with XAdES before submission — "
                "use es__sign_facturae_xades or a certified VERI*FACTU software."
            ),
        }
        if chain_warnings:
            result["chain_warnings"] = chain_warnings
        return ok(result)

    except EInvoicingError as exc:
        return err(str(exc))
    except Exception as exc:
        logger.exception("es__generate_verifactu_record failed")
        return err(str(exc))


async def handle_es_validate_verifactu_record(
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    try:
        xml_str = arguments.get("xml", "")
        if not xml_str:
            return err("xml is required", "MISSING_PARAM")

        xml_bytes = xml_str.encode() if isinstance(xml_str, str) else xml_str

        # --- Structural parse ---
        try:
            root = safe_fromstring(xml_bytes)
        except etree.XMLSyntaxError as exc:
            return ok(
                {
                    "valid": False,
                    "errors": [f"XML malformado: {exc}"],
                    "warnings": [],
                    "validation_mode": "structural",
                }
            )

        errors: list[str] = []
        warnings: list[str] = []

        def _req(tag: str) -> None:
            if not root.xpath(f".//*[local-name()='{tag}']"):
                errors.append(f"Elemento obligatorio ausente: <{tag}>")

        # RegistroAlta and RegistroAnulacion have different mandatory field
        # sets (IDFacturaExpedidaType vs IDFacturaExpedidaBajaType, and
        # RegistroAnulacion has no TipoFactura/CuotaTotal/ImporteTotal at
        # all) — applying the alta checklist unconditionally previously
        # produced false "missing element" errors on valid anulación XML.
        is_anulacion = bool(root.xpath(".//*[local-name()='RegistroAnulacion']"))
        if is_anulacion:
            required_tags = [
                "IDEmisorFacturaAnulada",
                "NumSerieFacturaAnulada",
                "FechaExpedicionFacturaAnulada",
                "FechaHoraHusoGenRegistro",
                "Huella",
            ]
        else:
            required_tags = [
                "IDEmisorFactura",
                "NumSerieFactura",
                "FechaExpedicionFactura",
                "TipoFactura",
                "CuotaTotal",
                "ImporteTotal",
                "FechaHoraHusoGenRegistro",
                "Huella",
            ]
        for tag in required_tags:
            _req(tag)

        # --- XSD validation (SuministroLR.xsd is the root schema for submissions) ---
        import pathlib  # noqa: PLC0415

        # __file__ = src/mcp_facturacion_electronica_es/tools/verifactu.py — four
        # .parent hops reach the package root where specs/ lives (a prior
        # version used three, landing on src/ and silently degrading every
        # call to structural-only validation).
        xsd_path = (
            pathlib.Path(__file__).parent.parent.parent.parent
            / "specs"
            / "verifactu"
            / "xsd"
            / "SuministroLR.xsd"
        )
        validation_mode = "structural"

        if xsd_path.exists():
            try:
                xsd_doc = etree.parse(str(xsd_path))
                schema = etree.XMLSchema(xsd_doc)
                schema.validate(root)
                for e in schema.error_log:
                    errors.append(f"[XSD] {e.message} (linea {e.line})")
                validation_mode = "xsd"
            except Exception as exc:
                warnings.append(f"XSD validation failed to run: {exc}")
        else:
            warnings.append(
                "Validacion XSD no disponible — specs/verifactu/xsd/SuministroLR.xsd "
                "no encontrado. La validacion estructural esta activa."
            )

        return ok(
            {
                "valid": len(errors) == 0,
                "errors": errors,
                "warnings": warnings,
                "validation_mode": validation_mode,
            }
        )

    except Exception as exc:
        logger.exception("es__validate_verifactu_record failed")
        return err(str(exc))


async def handle_es_submit_verifactu_to_aeat(
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    try:
        xml_str = arguments.get("xml", "")
        nif = arguments.get("nif", "")
        confirmation_token: str | None = arguments.get("confirmation_token") or None
        if not xml_str:
            return err("xml is required", "MISSING_PARAM")
        if not nif:
            return err("nif is required", "MISSING_PARAM")

        assert_not_read_only("AEAT_READ_ONLY")
        gate = ConfirmationGate.get_default()
        if not gate.is_confirmed(confirmation_token):
            env_label = aeat_env()
            return ok(
                gate.pending_response(
                    action="es__submit_verifactu_to_aeat",
                    summary=(
                        f"Submit VERI*FACTU XML to AEAT ({env_label}) for NIF {nif!r}. "
                        "This action reports the invoice to the Tax Agency and cannot be retracted."
                    ),
                    token=confirmation_token,
                )
            )

        env = aeat_env()
        base_url = VERIFACTU_ENDPOINTS[env]
        xml_bytes = xml_str.encode() if isinstance(xml_str, str) else xml_str

        if SignerClient.is_configured():
            signer = SignerClient.from_env()
            result = await signer.mtls_submit_files(
                base_url,
                [("xml", "registro.xml", xml_bytes, "application/xml")],
            )
            gate.consume(confirmation_token)
            # ES-SH-2: parse response before returning — do not echo raw AEAT response to LLM
            parsed = _parse_verifactu_response(result.get("body", ""))
            return ok(
                {
                    "status_code": result["status_code"],
                    "environment": env,
                    "parsed_response": parsed,
                    # ES-LC-12: accepted-only chain contract — see _build_chain_result
                    "chain": _build_chain_result(parsed, xml_bytes),
                    "note": "Use es__parse_aeat_response for full response parsing.",
                }
            )

        # Fallback: direct mTLS (legacy mode — cert lives in MCP process).
        from mcp_einvoicing_core.http_client import AuthMode, BaseEInvoicingClient  # noqa: PLC0415

        cert_path = aeat_settings.certificate_path
        cert_password = aeat_settings.certificate_password
        if not cert_path:
            return err(
                "AEAT_CERTIFICATE_PATH no está configurado. "
                "Arranque el servicio de firma (EINVOICING_SIGNER_SOCKET) "
                "o proporcione la ruta al certificado FNMT-RCM PKCS#12.",
                "MISSING_CONFIG",
            )
        logger.warning(
            "es__submit_verifactu_to_aeat: signer microservice not configured — "
            "cert material is in the MCP process (security risk). "
            "Set EINVOICING_SIGNER_SOCKET and EINVOICING_SIGNER_TOKEN."
        )

        client = BaseEInvoicingClient(
            base_url=base_url,
            auth_mode=AuthMode.MTLS,
            cert_path=cert_path,
            cert_password=cert_password,
        )
        response = await client._request(
            "POST",
            "",
            data=None,
            json=None,
            files={"xml": ("registro.xml", xml_bytes, "application/xml")},
        )
        # ES-SH-2: parse response before returning — do not echo raw AEAT response to LLM
        gate.consume(confirmation_token)
        parsed = _parse_verifactu_response(response.text)
        return ok(
            {
                "status_code": response.status_code,
                "environment": env,
                "parsed_response": parsed,
                # ES-LC-12: accepted-only chain contract — see _build_chain_result
                "chain": _build_chain_result(parsed, xml_bytes),
                "note": "Use es__parse_aeat_response for full response parsing.",
            }
        )

    except Exception as exc:
        logger.exception("es__submit_verifactu_to_aeat failed")
        return err(str(exc))


async def handle_es_query_verifactu_status(
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    try:
        nif = arguments.get("nif", "")
        name = arguments.get("name", "")
        invoice_date = arguments.get("invoice_date", "")
        num_serie_factura: str | None = arguments.get("num_serie_factura") or None

        for field_name, val in [("nif", nif), ("name", name), ("invoice_date", invoice_date)]:
            if not val:
                return err(f"{field_name} is required", "MISSING_PARAM")

        fiscal_year = int(invoice_date[:4])
        period = invoice_date[5:7] if len(invoice_date) >= 7 else "01"

        xml_bytes = _build_consulta_lr(
            nif=nif,
            name=name,
            fiscal_year=fiscal_year,
            period=period,
            num_serie_factura=num_serie_factura,
        )

        env = aeat_env()
        base_url = VERIFACTU_CONSULTA_ENDPOINTS[env]

        if SignerClient.is_configured():
            signer = SignerClient.from_env()
            result = await signer.mtls_submit_files(
                base_url,
                [("xml", "consulta.xml", xml_bytes, "application/xml")],
            )
            parsed = _parse_consulta_lr_response(result.get("body", ""))
            return ok(
                {
                    "status_code": result["status_code"],
                    "environment": env,
                    "parsed_response": parsed,
                }
            )

        from mcp_einvoicing_core.http_client import AuthMode, BaseEInvoicingClient  # noqa: PLC0415

        cert_path = aeat_settings.certificate_path
        cert_password = aeat_settings.certificate_password
        if not cert_path:
            return err(
                "AEAT_CERTIFICATE_PATH no está configurado. "
                "Arranque el servicio de firma (EINVOICING_SIGNER_SOCKET) "
                "o proporcione la ruta al certificado FNMT-RCM PKCS#12.",
                "MISSING_CONFIG",
            )
        logger.warning(
            "es__query_verifactu_status: signer microservice not configured. "
            "cert material is in the MCP process (security risk). "
            "Set EINVOICING_SIGNER_SOCKET and EINVOICING_SIGNER_TOKEN."
        )

        client = BaseEInvoicingClient(
            base_url=base_url,
            auth_mode=AuthMode.MTLS,
            cert_path=cert_path,
            cert_password=cert_password,
        )
        response = await client._request(
            "POST",
            "",
            data=None,
            json=None,
            files={"xml": ("consulta.xml", xml_bytes, "application/xml")},
        )
        parsed = _parse_consulta_lr_response(response.text)
        return ok(
            {
                "status_code": response.status_code,
                "environment": env,
                "parsed_response": parsed,
            }
        )

    except Exception as exc:
        logger.exception("es__query_verifactu_status failed")
        return err(str(exc))


async def handle_es_generate_qr_verifactu(
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    try:
        nif = arguments.get("nif", "")
        invoice_number = arguments.get("invoice_number", "")
        invoice_date = arguments.get("invoice_date", "")
        total_amount = arguments.get("total_amount")
        size_px = int(arguments.get("size_px", 200))

        for name, value in [
            ("nif", nif),
            ("invoice_number", invoice_number),
            ("invoice_date", invoice_date),
        ]:
            if not value:
                return err(f"{name} is required", "MISSING_PARAM")
        if total_amount is None:
            return err("total_amount is required", "MISSING_PARAM")

        # Build verification URL per DetalleEspecificacTecnCodigoQRfactura.pdf s5/s6
        # (specs/verifactu/documentation/): 4 mandatory params (nif, numserie, fecha,
        # importe), each URL-encoded individually (s4 — the doc's own worked example
        # shows a literal "&" inside numserie becoming "%26"); the "?"/"&"/"=" structural
        # characters themselves stay literal. quote_plus mirrors the doc's Java
        # URLEncoder.encode(value, "UTF-8") reference implementation (space -> "+",
        # all reserved characters including "/" percent-encoded).
        fecha_es = fmt_date_es(invoice_date)
        importe = fmt_amount(Decimal(str(total_amount)))

        qr_base_url = VERIFACTU_QR_ENDPOINTS[aeat_env()]
        query = "&".join(
            f"{key}={quote_plus(str(value), safe='')}"
            for key, value in (
                ("nif", nif),
                ("numserie", invoice_number),
                ("fecha", fecha_es),
                ("importe", importe),
            )
        )
        verification_url = f"{qr_base_url}?{query}"

        png_b64 = generate_qr_png_base64(verification_url, size_px=size_px, error_correction="M")

        logger.info("VERI*FACTU QR generated for %s / %s", nif, invoice_number)

        return ok(
            {
                "qr_png_base64": png_b64,
                "verification_url": verification_url,
                "environment": aeat_env(),
                "mandatory_legends": [
                    "Factura verificable en la sede electrónica de la AEAT",
                    "VERIFACTU",
                ],
                "size_px": size_px,
                "physical_spec": {
                    "min_size_mm": "30x40",
                    "symbology": "ISO/IEC 18004",
                    "error_correction_level": "M",
                    "source": (
                        "specs/verifactu/documentation/"
                        "DetalleEspecificacTecnCodigoQRfactura.pdf s2/s5/s6"
                    ),
                },
            }
        )

    except ImportError as exc:
        return err(
            f"qrcode[pil] no está instalado: {exc}. Instale con: pip install 'qrcode[pil]'",
            "MISSING_DEPENDENCY",
        )
    except Exception as exc:
        logger.exception("es__generate_qr_verifactu failed")
        return err(str(exc))


async def handle_es_cancel_verifactu_record(
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    try:
        num_serie = arguments.get("original_invoice_number", "")
        fecha_iso = arguments.get("original_invoice_date", "")
        issuer_nif = arguments.get("issuer_nif", "")
        issuer_name = arguments.get("issuer_name", "")
        previous_hash = arguments.get("previous_hash", "")

        for name, val in [
            ("original_invoice_number", num_serie),
            ("original_invoice_date", fecha_iso),
            ("issuer_nif", issuer_nif),
            ("issuer_name", issuer_name),
            ("previous_hash", previous_hash),
        ]:
            if not val:
                return err(f"{name} is required", "MISSING_PARAM")

        fecha_es = fmt_date_es(fecha_iso)
        now = datetime.now().astimezone()
        fecha_hora_gen = now.strftime("%Y-%m-%dT%H:%M:%S%z")
        if len(fecha_hora_gen) > 19 and ":" not in fecha_hora_gen[-6:]:
            fecha_hora_gen = fecha_hora_gen[:-2] + ":" + fecha_hora_gen[-2:]

        previous_emisor_nif: str | None = arguments.get("previous_emisor_nif") or None
        previous_num_serie_arg: str | None = arguments.get("previous_num_serie") or None
        previous_fecha_arg: str | None = arguments.get("previous_fecha") or None

        # Build RegistroAnulacion
        ra = _el("RegistroAnulacion")
        _sub(ra, "IDVersion", _VERIFACTU_VERSION)
        ra.append(_build_id_factura_anulada(num_serie, issuer_nif, fecha_es))
        _sub(ra, "NombreRazonEmisor", issuer_name)

        # ES-LC-4: EncadenamientoFacturaAnteriorType requires all 4 identity fields
        enc = _sub(ra, "Encadenamiento")
        _sub(enc, "PrimerRegistro", "N")
        reg_ant = _sub(enc, "RegistroAnterior")
        _sub(reg_ant, "IDEmisorFactura", previous_emisor_nif or issuer_nif)
        _sub(reg_ant, "NumSerieFactura", previous_num_serie_arg or num_serie)
        _sub(reg_ant, "FechaExpedicionFactura", previous_fecha_arg or fecha_es)
        _sub(reg_ant, "Huella", previous_hash)

        # SistemaInformatico — IdSistemaInformatico is TextMax2Type (max 2 chars)
        si = _sub(ra, "SistemaInformatico")
        _sub(si, "NombreRazon", issuer_name)
        _sub(si, "NIF", issuer_nif)
        _sub(si, "NombreSistemaInformatico", "mcp-facturacion-electronica-es")
        _sub(si, "IdSistemaInformatico", _SOFTWARE_ID_CODE)
        _sub(si, "Version", "0.1.0")
        _sub(si, "NumeroInstalacion", "001")
        _sub(si, "TipoUsoPosibleSoloVerifactu", "S")
        _sub(si, "TipoUsoPosibleMultiOT", "N")
        _sub(si, "IndicadorMultiplesOT", "N")

        _sub(ra, "FechaHoraHusoGenRegistro", fecha_hora_gen)

        # Huella for the anulacion record itself (ES-SC-11: dedicated field set,
        # no TipoFactura/CuotaTotal, see _compute_huella_anulacion docstring)
        huella = _compute_huella_anulacion(
            emisor_nif=issuer_nif,
            num_serie=num_serie,
            fecha_es=fecha_es,
            fecha_hora_gen=fecha_hora_gen,
            huella_anterior=previous_hash,
        )
        # TipoHuella must be "01" (SHA-256) per TipoHuellaType in SuministroInformacion.xsd
        _sub(ra, "TipoHuella", "01")
        _sub(ra, "Huella", huella)

        xml_bytes = _wrap_registro_facturacion(
            emisor_nif=issuer_nif,
            emisor_name=issuer_name,
            inner=ra,
        )

        return ok(
            {
                "xml": xml_bytes.decode("utf-8"),
                "huella": huella,
                "fecha_hora_gen": fecha_hora_gen,
                "cancelled_invoice": {
                    "emisor_nif": issuer_nif,
                    "num_serie": num_serie,
                    "fecha": fecha_es,
                },
            }
        )

    except Exception as exc:
        logger.exception("es__cancel_verifactu_record failed")
        return err(str(exc))
