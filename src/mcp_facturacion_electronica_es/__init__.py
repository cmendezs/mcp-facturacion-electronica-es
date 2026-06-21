"""mcp-facturacion-electronica-es — MCP server for Spanish electronic invoicing.

Covers AEAT-scope systems: VERI*FACTU, Facturae/FACe, SII, and Crea y Crece B2B.
TicketBAI (Basque Country) and NaTicket (Navarre) are out of scope.

Standards:
    VERI*FACTU: Royal Decree 1007/2023, Order HAC/1177/2024
    Facturae:   Facturae 3.2.2 + XAdES-EPES (Ley 25/2013)
    SII:        AEAT SII technical guide v3.0 (RD 596/2016)
    B2B:        EN 16931 / UBL 2.1 (Ley 18/2022 Crea y Crece)
"""

__version__ = "0.2.0"
__author__ = "cmendezs"
