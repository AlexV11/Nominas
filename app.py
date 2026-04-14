import io
import re

from datetime import datetime, timedelta
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

def get_week_range_text():
    today = datetime.today()

    # Lunes como inicio de semana
    start = today - timedelta(days=today.weekday())
    end = start + timedelta(days=6)

    meses = {
        1: "ENERO", 2: "FEBRERO", 3: "MARZO", 4: "ABRIL",
        5: "MAYO", 6: "JUNIO", 7: "JULIO", 8: "AGOSTO",
        9: "SEPTIEMBRE", 10: "OCTUBRE", 11: "NOVIEMBRE", 12: "DICIEMBRE"
    }

    return f"SEMANA DEL {start.day:02d} DE {meses[start.month]} AL {end.day:02d} DE {meses[end.month]} DEL {end.year}"

def _total_to_words(total) -> str:
    """Convert a numeric total to uppercase Spanish words."""
    if pd.isna(total):
        return ""

    try:
        total_str = str(total).strip()
        if total_str == "":
            return ""

        # Accept common decimal-comma input from spreadsheets.
        if "," in total_str and "." not in total_str:
            total_str = total_str.replace(",", ".")

        amount = float(total_str)
    except (ValueError, TypeError):
        return str(total).upper()

    if pd.isna(amount) or amount in (float("inf"), float("-inf")):
        return ""

    integer_part = int(amount)
    decimal_part = int(round((amount - integer_part) * 100))
    if decimal_part == 100:
        integer_part += 1
        decimal_part = 0

    words = num2words(integer_part, lang="es").upper()
    # Clean up extra spaces
    words = re.sub(r"\s+", " ", words).strip()

    if decimal_part > 0:
        cent_words = num2words(decimal_part, lang="es").upper()
        return f"{words} PESOS {cent_words}/100 CENTAVOS"
    return f"{words} PESOS"


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Strip whitespace from column names and normalise accents lightly."""
    alias_map = {
        "15%": "15%",
        "15": "15%",
        "%15": "15%",
        "0.15": "15%",
        "0,15": "15%",
        "DIRECCIÓN": "DIRECCION",
        "DIRECCION": "DIRECCION",
        "DIAFESTIVO": "DÍA FESTIVO",
        "DÍAFESTIVO": "DÍA FESTIVO",
    }

    normalised = []
    for col in df.columns:
        if pd.isna(col):
            normalised.append("")
            continue
        if isinstance(col, float) and col.is_integer():
            col = int(col)

        col_str = re.sub(r"\s+", " ", str(col)).strip()
        col_upper = col_str.upper()
        col_key = col_upper.replace(" ", "")

        if col_key in alias_map:
            normalised.append(alias_map[col_key])
        else:
            normalised.append(col_upper)

    df.columns = normalised
    return df


# ---------------------------------------------------------------------------
# PDF generation
# ---------------------------------------------------------------------------

def build_pdf(df: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()

    # Keep only rows with a real employee name to avoid blank payroll pages.
    if "EMPLEADO" in df.columns:
        df = df[~df["EMPLEADO"].apply(_is_blank)].reset_index(drop=True)
    else:
        df = df.reset_index(drop=True)

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle("title", parent=styles["Heading1"], fontSize=14, alignment=1)
    subtitle_style = ParagraphStyle("subtitle", parent=styles["Normal"], fontSize=10, alignment=1)
    normal_style = styles["Normal"]
    bold_style = ParagraphStyle("bold", parent=styles["Normal"], fontName="Helvetica-Bold")
    table_wrap_style = ParagraphStyle(
        "table_wrap",
        parent=styles["Normal"],
        fontSize=9,
        leading=11,
    )

    doc = BaseDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
    )

    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height)
    doc.addPageTemplates([PageTemplate(id="main", frames=frame)])

    story = []

    for idx, row in df.iterrows():

        nombre = _fmt(row.get("EMPLEADO", ""))
        direccion = _fmt(row.get("DIRECCION", ""))
        total = row.get("TOTAL", 0)

        # ───────── HEADER ─────────
        story.append(Paragraph("NÓMINA", title_style))
        story.append(Paragraph(get_week_range_text(), subtitle_style))
        story.append(Spacer(1, 10))

        story.append(Paragraph("<b>MELETO ES CAFÉ</b>", normal_style))
        story.append(Paragraph("Cuauhtémoc, Chihuahua", normal_style))
        story.append(Spacer(1, 15))

        # ───────── EMPLOYEE INFO ─────────
        story.append(Paragraph(f"<b>NOMBRE DEL EMPLEADO:</b> {nombre}", normal_style))
        story.append(Paragraph("<b>DÍAS LABORADOS:</b> ", normal_style))
        story.append(Paragraph("<b>DÍAS DE DESCANSO:</b> ", normal_style))
        story.append(Paragraph(direccion, normal_style))
        story.append(Paragraph("<b>DEPARTAMENTO:</b> ", normal_style))
        story.append(Paragraph("<b>HORARIO:</b> ", normal_style))
        story.append(Spacer(1, 15))

        # ───────── TABLE ─────────
        data = [
            ["PERCEPCIONES", "CANTIDAD"],
            ["Total acumulado en la semana", f"${_fmt(row.get('$'))} PESOS"],
            ["Horas laboradas en la semana", f"{_fmt(row.get('TOTAL HRS'))} HORAS"],
            ["Bonos", f"${_fmt(row.get('15%'))} PESOS"],
        ]

        if not _is_blank(row.get("PRIMA")):
            data.append(["Prima", f"${_fmt(row.get('PRIMA'))} PESOS"])

        if not _is_blank(row.get("ENCARGADO")):
            data.append(["Encargado", f"${_fmt(row.get('ENCARGADO'))} PESOS"])

        if not _is_blank(row.get("EXTRAS")):
            data.append(["Extras", f"${_fmt(row.get('EXTRAS'))} PESOS"])

        if not _is_blank(row.get("DÍA FESTIVO")):
            data.append(["Día festivo", f"${_fmt(row.get('DÍA FESTIVO'))} PESOS"])

        data.extend([
            ["Total", f"${_fmt(total)} PESOS"],
            ["Cantidad en letra", Paragraph(_total_to_words(total), table_wrap_style)],
        ])

        table = Table(data, colWidths=[doc.width * 0.65, doc.width * 0.35])
        table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))

        story.append(table)
        story.append(Spacer(1, 20))

        # ───────── LEGAL TEXT ─────────
        story.append(Paragraph(
            "RECIBÍ DE MELETO ES CAFÉ LA CANTIDAD QUE SEÑALA ESTE RECIBO DE PAGO, "
            "ESTANDO CONFORME CON LAS PERCEPCIONES Y LAS RETENCIONES ESCRITAS, "
            "POR LO QUE CERTIFICO QUE NO SE ME ADEUDA CANTIDAD ALGUNA.",
            normal_style
        ))

        story.append(Spacer(1, 60))

        # ───────── SIGNATURES ─────────
        signature_data = [
            [
                Paragraph("FIRMA DEL EMPLEADO: ____________________", normal_style),
                Paragraph("FIRMA DEL SUPERVISOR: ____________________", normal_style),
            ],
            [
                Paragraph("FECHA: ____ / ____ / ____", normal_style),
                Paragraph("FECHA: ____ / ____ / ____", normal_style),
            ],
        ]
        signature_table = Table(signature_data, colWidths=[doc.width * 0.5, doc.width * 0.5])
        signature_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        story.append(signature_table)

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
            total_rows = len(df)
            df_nominas = df[~df["EMPLEADO"].apply(_is_blank)].copy()
            st.success(
                f"✅ Archivo cargado correctamente — {len(df_nominas)} nómina(s) válida(s) "
                f"de {total_rows} fila(s)."
            )

            # Summary view instead of rendering the full employee table.
            for col in ["TOTAL", "TOTAL HRS", "$", "15%", "PRIMA", "ENCARGADO", "EXTRAS", "DÍA FESTIVO"]:
                if col in df_nominas.columns:
                    df_nominas[col] = pd.to_numeric(df_nominas[col], errors="coerce").fillna(0)

            descartadas = total_rows - len(df_nominas)
            total_nomina = float(df_nominas["TOTAL"].sum()) if "TOTAL" in df_nominas.columns else 0.0
            total_horas = float(df_nominas["TOTAL HRS"].sum()) if "TOTAL HRS" in df_nominas.columns else 0.0

            st.subheader("Resumen de nómina")

            st.metric("Monto total de nómina", f"${total_nomina:,.2f}")

            conceptos = ["$", "15%", "PRIMA", "ENCARGADO", "EXTRAS", "DÍA FESTIVO", "TOTAL"]
            resumen_conceptos = []
            for concepto in conceptos:
                if concepto in df_nominas.columns:
                    resumen_conceptos.append(
                        {
                            "Concepto": concepto,
                            "Monto": float(df_nominas[concepto].sum()),
                        }
                    )

            if resumen_conceptos:
                resumen_df = pd.DataFrame(resumen_conceptos)
                resumen_df["Monto"] = resumen_df["Monto"].map(lambda v: f"${v:,.2f}")
                st.table(resumen_df)

            if df_nominas.empty:
                st.warning("No hay empleados con nombre para generar nóminas.")
            elif st.button("Generar PDF de nóminas"):
                with st.spinner("Generando PDF…"):
                    pdf_bytes = build_pdf(df_nominas)

                st.download_button(
                    label="⬇️ Descargar PDF",
                    data=pdf_bytes,
                    file_name="nominas.pdf",
                    mime="application/pdf",
                )
    except Exception as exc:
        st.error(f"Error al leer el archivo: {exc}")
