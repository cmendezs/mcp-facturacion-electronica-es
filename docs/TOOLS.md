# Tool reference — `mcp_facturacion_electronica_es`

This file is generated from the MCP server's tool registry by `scripts/gen_tool_reference.py`. Do not edit it by hand; run the script instead.

**Tools:** 20

## `es__build_sii_invoice_record`

Construye un registro XML AEAT SII en formato SOAP.

Emisión FacturaExpedida o recepción FacturaRecibida, conforme a la guía
técnica SII v3.0 (abril 2024). Soporta TipoComunicacion A0 (alta),
A1 (modificación) y A4 (baja).

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `invoice` | object | yes |  | Datos de la factura. |
| `record_type` | string | yes |  | Dirección: 'issued' (expedida) o 'received' (recibida). |
| `communication_type` | string | no | `'A0'` | TipoComunicacion: A0 alta (por defecto), A1 modificación, A4 baja. |
| `clave_regimen` | string | no | `'01'` | ClaveRegimenEspecialOTrascendencia (por defecto '01'). |

## `es__cancel_verifactu_record`

Genera un registro de anulacion VERI*FACTU (TipoHuella=01).

Encadenado a la secuencia de huellas actual.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `original_invoice_number` | string | yes |  | NumSerieFactura a anular. |
| `original_invoice_date` | string | yes |  | FechaExpedicionFactura original (YYYY-MM-DD). |
| `issuer_nif` | string | yes |  | NIF del emisor. |
| `issuer_name` | string | yes |  | Nombre/razon social del emisor. |
| `previous_hash` | string | yes |  | Huella del ultimo registro en la cadena. |
| `previous_emisor_nif` | string | null | no | `None` | NIF del emisor del registro anterior (IDEmisorFactura en EncadenamientoFacturaAnteriorType). |
| `previous_num_serie` | string | null | no | `None` | NumSerieFactura del registro anterior. |
| `previous_fecha` | string | null | no | `None` | FechaExpedicionFactura del registro anterior en DD-MM-YYYY. |

## `es__check_b2b_mandate_applicability`

Determina el régimen de facturación electrónica aplicable.

VERI*FACTU, SII, TicketBAI, NaTicket, a partir del volumen de operaciones,
código de provincia y enrolamiento en SII. Aplica la lógica de exclusión
mutua del Real Decreto 254/2025.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `annual_turnover_eur` | number | yes |  | Volumen anual de operaciones IVA en EUR. |
| `tax_address_province_code` | string | yes |  | Código de provincia INE de dos dígitos. |
| `enrolled_in_sii` | boolean | no | `False` | Inscripción en el SII (por defecto: false). |
| `entity_type` | string | no | `'IS'` | Tipo de obligado: 'IS' (Sociedades) o 'IRPF'. |

## `es__detect_regional_regime`

Detecta el régimen de facturación electrónica aplicable.

A partir del código de provincia INE de dos dígitos. Devuelve VERIFACTU,
TICKETBAI, NATICKET o VERIFACTU+SII. Usar siempre antes de llamar a
cualquier otra herramienta de este servidor.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `province_code` | string | yes |  | Código de provincia INE de dos dígitos (p. ej., '28', '01', '31'). |
| `enrolled_in_sii` | boolean | no | `False` | Inscripción en el SII (por defecto: false). |

## `es__generate_b2b_einvoice_es`

Genera una factura B2B conforme a EN 16931 en formato UBL 2.1 o Facturae 3.2.2.

Según la Ley 18/2022 'Crea y Crece'. RD 238/2026 publicado; formatos
confirmados (EN 16931: CII/UBL/EDIFACT/Facturae). Orden Ministerial
(Hacienda) pendiente para la solución pública.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `invoice` | object | yes |  | Datos de la factura. |
| `format` | string | no | `'ubl'` | Formato de salida: 'ubl' (por defecto) o 'facturae'. |

## `es__generate_facturae_xml`

Genera una factura XML conforme a Facturae 3.2.2 para envío B2G al portal FACe.

El documento generado está sin firmar; use es__sign_facturae_xades para firmarlo.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `invoice` | object | yes |  | InvoiceDocument con seller, buyer, vat_summary y lines. |
| `schema_version` | string | no | `'3.2.2'` | Versión del esquema Facturae (por defecto: '3.2.2'). |
| `invoice_issuer_type` | string | no | `'EU'` | EU (emisor=vendedor), EM (emisor=comprador), TE (tercero). Por defecto: 'EU'. |
| `tax_type` | string | no | `'IVA'` | Impuesto indirecto aplicable a todas las líneas de la factura (IVA: península/Baleares; IPSI: Ceuta/Melilla; IGIC: Canarias). No se admite mezclar impuestos en una misma factura. Por defecto: 'IVA'. |
| `recargo_equivalencia_rate` | number | null | no | `None` | Tipo de Recargo de Equivalencia (%), si aplica. |
| `recargo_equivalencia_amount` | number | null | no | `None` | Importe explícito del Recargo de Equivalencia. Si se omite, se calcula como base_imponible * recargo_equivalencia_rate / 100. |
| `irpf_amount` | number | null | no | `None` | Importe de retención IRPF a deducir del total de la factura. |
| `irpf_rate` | number | null | no | `None` | Tipo de retención IRPF (%), emitido en TaxesWithheld. |
| `resolution_reference` | string | null | no | `None` | ResolutionReference para facturas B2G a Administraciones Públicas. |
| `receiver_transaction_reference` | string | null | no | `None` | ReceiverTransactionReference para facturas B2G. |

## `es__generate_qr_verifactu`

Genera el código QR obligatorio VERI*FACTU (HAC/1177/2024 Art. 10) como PNG en base64.

Encodes la URL de verificación de la AEAT:
https://www2.agenciatributaria.gob.es/wlpl/TIKE-CONT/ValidarQR?...

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `nif` | string | yes |  | NIF del emisor. |
| `invoice_number` | string | yes |  | NumSerieFactura. |
| `invoice_date` | string | yes |  | FechaExpedicionFactura en YYYY-MM-DD. |
| `total_amount` | number | yes |  | ImporteTotal de la factura (con IVA incluido). |
| `size_px` | integer | no | `200` | Tamaño del QR en píxeles (por defecto: 200). |

## `es__generate_sii_correction`

Genera un registro de modificación SII (A1) o baja (A4).

Referencia la factura original mediante IDFactura.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `original_invoice` | object | yes |  | Factura original que se rectifica. |
| `correction_type` | string | yes |  | 'A1' (modificación) o 'A4' (baja). |
| `record_type` | string | yes |  | 'issued' o 'received'. |
| `corrected_invoice` | object | null | no | `None` | Datos corregidos. Omitir para una baja (A4). |

## `es__generate_verifactu_record`

Genera un registro de factura VERI*FACTU (Orden HAC/1177/2024) con cadena SHA-256 Huella.

Devuelve el XML del registro y la Huella para encadenar con el siguiente registro.
Llame a es__detect_regional_regime antes para confirmar que el régimen es VERIFACTU.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `invoice` | object | yes |  | Datos de la factura (date, number, seller, buyer, vat_summary, note). |
| `software_id` | string | yes |  | IDSistemaInformatico del software certificado. |
| `software_nif` | string | yes |  | NIF del fabricante del software. |
| `invoice_type` | string | no | `'F1'` | TipoFactura según HAC/1177/2024 Annex I (F1, F2, F3, R1, R2, R3, R4, R5). |
| `previous_hash` | string | null | no | `None` | Huella SHA-256 del registro precedente (omitir para el primero). |
| `previous_emisor_nif` | string | null | no | `None` | NIF del emisor del registro anterior (requerido si previous_hash está presente). |
| `previous_num_serie` | string | null | no | `None` | NumSerieFactura del registro anterior (requerido si previous_hash está presente). |
| `previous_fecha` | string | null | no | `None` | FechaExpedicionFactura del registro anterior en DD-MM-YYYY (requerido si previous_hash está presente). |
| `clave_regimen` | string | no | `'01'` | ClaveRegimenEspecialOTrascendencia (por defecto '01'). |
| `impuesto` | string | no | `'01'` | Código de impuesto (por defecto '01' IVA). |
| `calificacion_operacion` | string | no | `'S1'` | CalificacionOperacion (por defecto 'S1'). |

## `es__get_compliance_status`

Devuelve los plazos de mandato vigentes y el sistema operativo para un perfil de empresa.

Refleja el RD-ley 15/2025 — sujeto a cambios por legislación posterior.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `entity_type` | string | yes |  | Tipo de obligado tributario: 'IS' o 'IRPF'. |
| `province_code` | string | yes |  | Código de provincia INE de dos dígitos. |
| `annual_turnover_eur` | number | null | no | `None` | Volumen anual de operaciones IVA en EUR (para umbral SII > €6M). |
| `enrolled_in_sii` | boolean | no | `False` | Inscripción en el SII. |

## `es__get_face_invoice_status`

Consulta el estado de tramitación de una factura en FACe.

Códigos: 1200 Registrada, 2400 Reconocida, 3100 Rechazada, 4100 Pagada.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `invoice_id` | string | yes |  | Número de registro FACe. |

## `es__parse_aeat_response`

Analiza y normaliza una respuesta XML de la AEAT (VERI*FACTU o SII) a JSON estructurado.

Extrae EstadoEnvio, CSV (código seguro de verificación) y detalle de errores.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `xml` | string | yes |  | Respuesta XML de la AEAT en crudo. |
| `response_type` | string | no | `'verifactu'` | Tipo de respuesta a analizar (por defecto: 'verifactu'). |

## `es__query_sii_status`

Consulta el estado de facturas en el SII mediante ConsultaFactInformadasEmitidas/Recibidas (SOAP).

ES-LC-2: reemplaza el REST GET no funcional por el envelope SOAP correcto.
Filtra por ejercicio, periodo y, opcionalmente, por NIF del emisor y
numero de factura.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `nif_titular` | string | yes |  | NIF del titular SII (obligado tributario). |
| `nombre_titular` | string | yes |  | Nombre o razon social del titular. |
| `fiscal_year` | integer | yes |  | Ejercicio fiscal (YYYY). |
| `period` | string | yes |  | Periodo de liquidacion: '01'..'12' para mensual, o '0A' para anual. |
| `record_type` | string | no | `'issued'` | Tipo de registro: 'issued' (expedidas) o 'received' (recibidas). |
| `invoice_number` | string | null | no | `None` | NumSerieFacturaEmisor para filtrar por factura concreta (opcional). |
| `emisor_nif` | string | null | no | `None` | NIF del emisor para filtrar (opcional, solo para received). |

## `es__query_verifactu_status`

Consulta el EstadoRegistro de un registro VERI*FACTU ya enviado.

(ConsultaFactuSistemaFacturacion / ConsultaLR.xsd). Use esta tool tras un
resultado 'deferred' de es__submit_verifactu_to_aeat, esperando
retry_after_seconds, para confirmar el estado final (Correcto /
AceptadoConErrores / Anulado) antes de encadenar el siguiente registro.
Requiere AEAT_ENV, AEAT_CERTIFICATE_PATH y AEAT_CERTIFICATE_PASSWORD, igual
que es__submit_verifactu_to_aeat.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `nif` | string | yes |  | NIF del obligado a la emisión (ObligadoEmision). |
| `name` | string | yes |  | Nombre/razón social del obligado a la emisión. |
| `invoice_date` | string | yes |  | Fecha de la factura consultada, YYYY-MM-DD (determina PeriodoImputacion). |
| `num_serie_factura` | string | null | no | `None` | NumSerieFactura a filtrar (omitir para consultar todo el período). |

## `es__sign_facturae_xades`

Aplica una firma digital XAdES-EPES (ETSI EN 319 132-1) a un documento Facturae XML.

Usa el certificado PKCS#12 indicado para firmar con SHA-256 + RSA. La
política de firma por defecto es la de Facturae (Orden EHA/962/2007).

HUMAN-IN-THE-LOOP: llame sin confirmation_token para recibir un resumen de
confirmación y un token; muéstrelo al usuario y vuelva a llamar con
confirmation_token para aplicar la firma real.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `xml` | string | yes |  | XML Facturae sin firmar. |
| `cert_path` | string | null | no | `None` | Ruta al certificado PKCS#12 (.p12 / .pfx). La contraseña se lee de AEAT_CERTIFICATE_PASSWORD (nunca como argumento de la tool). |
| `signature_policy_id` | string | null | no | `None` | OID/URI de la política de firma. Por defecto: política Facturae (Orden EHA/962/2007). |
| `signature_policy_hash` | string | null | no | `None` | SHA-256 base64 del documento de política de firma. |
| `confirmation_token` | string | null | no | `None` | Token de la respuesta awaiting_confirmation previa. |

## `es__submit_sii_batch`

Envía un lote de facturas (máximo 10.000 registros) al endpoint SOAP SII de la AEAT.

Requiere AEAT_ENV, AEAT_CERTIFICATE_PATH y AEAT_CERTIFICATE_PASSWORD (MTLS).

HUMAN-IN-THE-LOOP: llame sin confirmation_token para recibir un resumen de
confirmación y un token; muéstrelo al usuario y vuelva a llamar con
confirmation_token para ejecutar el envío real.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `records` | array[string] | yes |  | Lista de SOAP envelopes XML de es__build_sii_invoice_record. |
| `record_type` | string | yes |  | 'issued' o 'received'. |
| `fiscal_year` | integer | yes |  | Ejercicio fiscal (YYYY). |
| `confirmation_token` | string | null | no | `None` | Token de la respuesta awaiting_confirmation previa. |

## `es__submit_to_face`

Envía un XML Facturae firmado con XAdES a FACe a través de la API REST B2B de FACe v2.

FACe = Punto General de Entrada de Facturas Electrónicas. Autenticación JWS
(RS256 + x5c) per FACe-manual-api-integradores.pdf s2.3: requiere FACE_ENV
y AEAT_CERTIFICATE_PATH (+ AEAT_CERTIFICATE_PASSWORD).

HUMAN-IN-THE-LOOP: llame sin confirmation_token para recibir un resumen de
confirmación y un token; muéstrelo al usuario y vuelva a llamar con
confirmation_token para ejecutar el envío real.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `xml` | string | yes |  | XML Facturae con firma XAdES. |
| `administrative_unit` | string | yes |  | Código UnidadTramitadora de FACe. |
| `accounting_office` | string | yes |  | Código OficinasContables de FACe. |
| `management_body` | string | yes |  | Código OrganoGestor de FACe. |
| `confirmation_token` | string | null | no | `None` | Token de la respuesta awaiting_confirmation previa. |

## `es__submit_verifactu_to_aeat`

Envía un registro VERI*FACTU firmado al endpoint en tiempo real de la AEAT mediante MTLS.

Usa el certificado FNMT-RCM. Requiere AEAT_ENV, AEAT_CERTIFICATE_PATH y
AEAT_CERTIFICATE_PASSWORD. Si la respuesta trae parsed_response.status ==
'deferred' (TiempoEsperaEnvio), espere retry_after_seconds y llame a
es__query_verifactu_status para confirmar el EstadoRegistro final antes de
encadenar el siguiente registro.

HUMAN-IN-THE-LOOP: llame sin confirmation_token para recibir un resumen de
confirmación y un token; muéstrelo al usuario y vuelva a llamar con
confirmation_token para ejecutar el envío real.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `xml` | string | yes |  | Registro VERI*FACTU XML firmado. |
| `nif` | string | yes |  | NIF del remitente. |
| `confirmation_token` | string | null | no | `None` | Token de la respuesta awaiting_confirmation previa. |

## `es__validate_facturae_schema`

Valida un XML Facturae contra el XSD oficial 3.2.2.

Realiza validación estructural y, si el XSD está disponible en
specs/facturae/, también validación de esquema completa.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `xml` | string | yes |  | XML Facturae a validar. |
| `schema_version` | string | no | `'3.2.2'` | Versión del esquema (por defecto: '3.2.2'). |

## `es__validate_verifactu_record`

Valida un registro VERI*FACTU XML.

Realiza validación estructural y, si el XSD v1.0 (HAC/1177/2024) está
disponible en specs/verifactu/, también validación de esquema.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `xml` | string | yes |  | Registro VERI*FACTU XML en crudo. |
| `schema_version` | string | no | `'1.0'` | Versión del esquema XSD (por defecto: '1.0'). |
