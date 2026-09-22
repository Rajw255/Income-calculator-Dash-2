"""
INCOME CALCULATOR — EXPORT
============================
Builds the two downloads for the Income Calculator page: a CSV (inputs
used + the full year-by-year projection) and a one-page PDF (inputs +
the milestone-year table). Kept separate from report_export.py, which
is the (currently unused) full-dashboard export.
"""

import io
from datetime import date

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from formatting import format_inr, format_count, format_pct
from income_projection import ProjectionInputs

NAVY = colors.HexColor("#0B3D66")


def _input_rows(p: ProjectionInputs) -> list:
    """Ordered (label, value) pairs describing exactly what was entered."""
    rows = [
        ("Starting Clients", str(p.starting_clients)),
        ("Starting AUM", format_inr(p.starting_aum)),
        ("New Clients / Month", str(p.new_clients_per_month)),
        ("SIP / Client / Month", format_inr(p.sip_per_client_month)),
        ("SIP Step-up % p.a.", f"{p.sip_stepup_pct}%"),
        ("Annual Lumpsum / Client", format_inr(p.annual_lumpsum_per_client)),
        ("Lumpsum Step-up % p.a.", f"{p.lumpsum_stepup_pct}%"),
        ("Annual Redemption %", f"{p.annual_redemption_pct}%"),
        ("Active Years", str(p.active_years)),
        ("Trail Rate % p.a.", f"{p.trail_rate_pct}%"),
        ("Market CAGR % p.a.", f"{p.market_cagr_pct}%"),
        ("Life Insurance", "On (40% commission)" if p.life.enabled else "Off"),
        ("Health Insurance", "On (30% commission)" if p.health.enabled else "Off"),
        ("PMS", "On (1% commission)" if p.pms.enabled else "Off"),
        ("Demat & Broking", "On (₹210/client/mo)" if p.demat.enabled else "Off"),
    ]
    return rows


def _results_dataframe(projection: list) -> pd.DataFrame:
    rows = []
    for r in projection:
        row = {
            "Year": r["year"], "Clients": r["clients"],
            "SIP Contrib.": round(r["sip_contrib"]), "Step-up Inflows": round(r["stepup_inflow"]),
            "Lumpsum / Yr": round(r["lumpsum"]), "Mkt. Gains": round(r["mkt_gains"]),
            "Total AUM": round(r["total_aum"]), "SIP Book /Mo": round(r["sip_book_mo"]),
            "Trail / Yr": round(r["trail_yr"]),
        }
        for name, val in r["cross_sell"].items():
            row[f"{name} / Yr"] = round(val)
        row["Demat / Yr"] = round(r["demat_yr"])
        row["Total Income"] = round(r["total_income"])
        row["Uplift %"] = r["uplift_pct"]
        rows.append(row)
    return pd.DataFrame(rows)


def build_csv_bytes(p: ProjectionInputs, projection: list) -> bytes:
    """One CSV: an 'Inputs' block, then the full year-by-year results table."""
    buf = io.StringIO()
    buf.write("Partner Income Calculator — Inputs\n")
    for label, value in _input_rows(p):
        buf.write(f"{label},{value}\n")
    buf.write("\n")
    buf.write(f"{p.active_years}-Year Projection\n")
    _results_dataframe(projection).to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


def build_pdf_bytes(p: ProjectionInputs, projection: list, milestones: list) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=1.5 * cm, bottomMargin=1.5 * cm,
                             leftMargin=1.8 * cm, rightMargin=1.8 * cm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("TitleNavy", parent=styles["Title"], textColor=NAVY, fontSize=18)
    h2_style = ParagraphStyle("H2Navy", parent=styles["Heading2"], textColor=NAVY, spaceBefore=14)
    body_style = styles["BodyText"]

    story = [
        Paragraph("Partner Income Calculator", title_style),
        Paragraph(f"Generated {date.today():%d %b %Y}", body_style),
        Spacer(1, 10),
    ]

    story.append(Paragraph("Inputs Used", h2_style))
    input_rows = _input_rows(p)
    half = (len(input_rows) + 1) // 2
    left, right = input_rows[:half], input_rows[half:]
    combined = []
    for i in range(max(len(left), len(right))):
        l = left[i] if i < len(left) else ("", "")
        r = right[i] if i < len(right) else ("", "")
        combined.append([l[0], l[1], r[0], r[1]])
    input_table = Table(combined, colWidths=[4 * cm, 3.3 * cm, 4 * cm, 3.3 * cm])
    input_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dddddd")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f5f7fa")),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#f5f7fa")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(input_table)

    story.append(Paragraph(f"{p.active_years}-Year Income Projection — Milestones", h2_style))
    header = ["Year", "Clients", "Total AUM", "Trail /Yr", "Cross-sell /Yr", "Demat /Yr", "Total Income"]
    table_rows = [header]
    for y in milestones:
        r = projection[y - 1]
        table_rows.append([
            str(y), format_count(r["clients"]), format_inr(r["total_aum"]),
            format_inr(r["trail_yr"]), format_inr(r["cross_sell_total"]) if r["cross_sell_total"] else "—",
            format_inr(r["demat_yr"]) if r["demat_yr"] else "—", format_inr(r["total_income"]),
        ])
    result_table = Table(table_rows, colWidths=[1.6 * cm, 2.2 * cm, 2.6 * cm, 2.4 * cm, 2.8 * cm, 2.4 * cm, 2.6 * cm])
    result_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f7fa")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(result_table)
    story.append(Spacer(1, 10))
    story.append(Paragraph("Illustrative projections. Actual returns depend on market conditions and client activity.", body_style))

    doc.build(story)
    buf.seek(0)
    return buf.read()
