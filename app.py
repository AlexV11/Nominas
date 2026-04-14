import io
import re

import pandas as pd
import streamlit as st
from num2words import num2words
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REQUIRED_COLUMNS = {
    "EMPLEADO",
    "DIRECCION",
    "TOTAL HRS",
    "$",
    "15%",
    "PRIMA",
    "ENCARGADO",
    "EXTRAS",
    "DÍA FESTIVO",
    "TOTAL",
}


def _fmt(value) -> str:
    """Return a clean string representation of a cell value."""
    if pd.isna(value):
        return ""
    if isinstance(value, float) and value == int(value):
        return str(int(value))
    return str(value).strip()


def _is_blank(value) -> bool:
    """Return True if the value is empty / zero / NaN."""
    if pd.isna(value):
        return True
    s = str(value).strip()
    return s == "" or s == "0"


def _total_to_words(total) -> str:
    """Convert a numeric total to uppercase Spanish words."""
    try:
        amount = float(total)
    except (ValueError, TypeError):
        return str(total).upper()

    integer_part = int(amount)
    decimal_part = round((amount - integer_part) * 100)

    words = num2words(integer_part, lang="es").upper()
    # Clean up extra spaces
    words = re.sub(r"\s+", " ", words).strip()

    if decimal_part > 0:
        cent_words = num2words(decimal_part, lang="es").upper()
        return f"{words} PESOS {cent_words}/100 CENTAVOS"
    return f"{words} PESOS"


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Strip whitespace from column names and normalise accents lightly."""
    df.columns = [c.strip() for c in df.columns]
    return df


# ---------------------------------------------------------------------------
# PDF generation
# ---------------------------------------------------------------------------

def build_pdf(df: pd.DataFrame) -> bytes:
    """Generate a PDF with one page per employee row in *df*."""
    buffer = io.BytesIO()

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "titulo",
        parent=styles["Heading1"],
        fontSize=13,
        spaceAfter=2,
        leading=16,
    )
    label_style = ParagraphStyle(
        "label",
        parent=styles["Normal"],
        fontSize=10,
        spaceAfter=2,
    )
    bold_label_style = ParagraphStyle(
        "bold_label",
        parent=styles["Normal"],
        fontSize=10,
        fontName="Helvetica-Bold",
        spaceAfter=4,
    )

    doc = BaseDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )

    frame = Frame(
        doc.leftMargin,
        doc.bottomMargin,
        doc.width,
        doc.height,
        id="normal",
    )
    template = PageTemplate(id="main", frames=frame)
    doc.addPageTemplates([template])

    story = []

    for idx, row in df.iterrows():
        nombre = _fmt(row.get("EMPLEADO", ""))
        direccion = _fmt(row.get("DIRECCION", ""))
        total_hrs = row.get("TOTAL HRS", 0)
        base_rate = row.get("$", 0)
        bonus_15 = row.get("15%", 0)
        prima = row.get("PRIMA", 0)
        encargado = row.get("ENCARGADO", 0)
        extras = row.get("EXTRAS", 0)
        dia_festivo = row.get("DÍA FESTIVO", 0)
        total = row.get("TOTAL", 0)

        # ── Header ──────────────────────────────────────────────────────────
        story.append(Paragraph(nombre, title_style))
        story.append(Paragraph(direccion, label_style))
        story.append(Spacer(1, 0.15 * inch))

        # ── Perceptions table ────────────────────────────────────────────────
        header_row = [
            Paragraph("<b>PERCEPCIONES</b>", bold_label_style),
            Paragraph("<b>CANTIDAD</b>", bold_label_style),
        ]

        data = [header_row]

        # Sueldo base
        if not _is_blank(base_rate):
            data.append([
                "Sueldo base horario estudiante",
                f"{_fmt(base_rate)} PESOS POR HORA",
            ])

        # Horas laboradas
        if not _is_blank(total_hrs):
            data.append([
                "Horas laboradas a la semana",
                f"{_fmt(total_hrs)} HRS",
            ])

        # Prima dominical
        prima_str = _fmt(prima)
        if prima_str.upper() == "DESCANSO" or _is_blank(prima):
            prima_display = "DESCANSO"
        else:
            prima_display = f"{prima_str} PESOS"
        data.append(["Prima dominical", prima_display])

        # 15%
        if not _is_blank(bonus_15):
            data.append([
                "Puntualidad, asistencia, proactividad y uniforme completo (15%)",
                f"{_fmt(bonus_15)} PESOS",
            ])

        # Leader de turno
        if not _is_blank(encargado):
            data.append(["Leader de turno", f"{_fmt(encargado)} PESOS"])

        # Extras
        if not _is_blank(extras):
            data.append(["Horas extras", f"{_fmt(extras)} PESOS"])

        # Día festivo
        if not _is_blank(dia_festivo):
            data.append(["Día festivo", f"{_fmt(dia_festivo)} PESOS"])

        # Total
        data.append([
            Paragraph("<b>Total</b>", bold_label_style),
            Paragraph(f"<b>{_fmt(total)} PESOS</b>", bold_label_style),
        ])

        # Cantidad en letra
        data.append([
            Paragraph("<b>Cantidad en letra</b>", bold_label_style),
            Paragraph(
                f"<b>{_total_to_words(total)}</b>",
                bold_label_style,
            ),
        ])

        col_widths = [doc.width * 0.65, doc.width * 0.35]
        table = Table(data, colWidths=col_widths, repeatRows=1)
        table.setStyle(
            TableStyle([
                # Header row
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2C3E50")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 10),
                # Body rows
                ("FONTSIZE", (0, 1), (-1, -1), 9),
                ("ROWBACKGROUNDS", (0, 1), (-1, -3), [colors.white, colors.HexColor("#ECF0F1")]),
                # Total and words rows
                ("BACKGROUND", (0, -2), (-1, -1), colors.HexColor("#D5E8D4")),
                # Grid
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#BDC3C7")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ])
        )

        story.append(table)

        # Page break between employees (not after the last one)
        if idx < len(df) - 1:
            story.append(PageBreak())

    doc.build(story)
    buffer.seek(0)
    return buffer.read()


# ---------------------------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Generador de Nóminas", page_icon="📄", layout="centered")
st.title("📄 Generador de Nóminas")
st.write(
    "Sube el archivo Excel con las columnas **EMPLEADO, DIRECCION, TOTAL HRS, "
    "\\$, 15%, PRIMA, ENCARGADO, EXTRAS, DÍA FESTIVO, TOTAL** y descarga el PDF con las nóminas."
)

uploaded_file = st.file_uploader("Selecciona el archivo Excel (.xlsx)", type=["xlsx", "xls"])

if uploaded_file is not None:
    try:
        df = pd.read_excel(uploaded_file, engine="openpyxl")
        df = _normalise_columns(df)

        # Validate required columns
        missing = REQUIRED_COLUMNS - set(df.columns)
        if missing:
            st.error(
                f"El archivo no contiene las columnas requeridas: **{', '.join(sorted(missing))}**\n\n"
                f"Columnas encontradas: {', '.join(df.columns.tolist())}"
            )
        else:
            st.success(f"✅ Archivo cargado correctamente — {len(df)} empleado(s) encontrado(s).")
            st.dataframe(df, use_container_width=True)

            if st.button("Generar PDF de nóminas"):
                with st.spinner("Generando PDF…"):
                    pdf_bytes = build_pdf(df)

                st.download_button(
                    label="⬇️ Descargar PDF",
                    data=pdf_bytes,
                    file_name="nominas.pdf",
                    mime="application/pdf",
                )
    except Exception as exc:
        st.error(f"Error al leer el archivo: {exc}")
