import os
from .base import BaseHandler

try:
    import docx
    from docx.shared import Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH
except ImportError:
    docx = None


class DocxHandler(BaseHandler):
    """Handler for reading and writing Microsoft Word (.docx) documents."""

    @property
    def is_spatial(self) -> bool:
        return False

    def read(self, file_path: str, **kwargs) -> dict:
        """
        Reads a .docx file and returns structured content (paragraphs and tables).
        """
        if docx is None:
            raise ImportError("python-docx library is not installed.")

        try:
            doc = docx.Document(file_path)
            paragraphs_data = []

            for p in doc.paragraphs:
                runs_data = []
                for r in p.runs:
                    runs_data.append({
                        "text": r.text,
                        "bold": bool(r.bold),
                        "italic": bool(r.italic),
                        "underline": bool(r.underline),
                        "font_name": r.font.name if r.font else None,
                        "font_size": r.font.size.pt if r.font and r.font.size else None,
                    })
                
                align = "left"
                if p.alignment == WD_ALIGN_PARAGRAPH.CENTER:
                    align = "center"
                elif p.alignment == WD_ALIGN_PARAGRAPH.RIGHT:
                    align = "right"
                elif p.alignment == WD_ALIGN_PARAGRAPH.JUSTIFY:
                    align = "justify"

                style_name = p.style.name if p.style else "Normal"

                paragraphs_data.append({
                    "style": style_name,
                    "text": p.text,
                    "alignment": align,
                    "runs": runs_data
                })

            tables_data = []
            for t in doc.tables:
                table_rows = []
                for row in t.rows:
                    row_cells = [cell.text.strip() for cell in row.cells]
                    table_rows.append(row_cells)
                tables_data.append(table_rows)

            return {
                "file_path": file_path,
                "paragraphs": paragraphs_data,
                "tables": tables_data,
                "full_text": "\n".join(p.text for p in doc.paragraphs)
            }
        except Exception as e:
            raise RuntimeError(f"Failed to read Word document ({os.path.basename(file_path)}): {e}")

    def write(self, file_path: str, document_data: object, **kwargs) -> None:
        """
        Writes structured document content or text blocks to a .docx file.
        document_data can be a dictionary with 'paragraphs' and 'tables',
        or a list of paragraph items, or plain text.
        """
        if docx is None:
            raise ImportError("python-docx library is not installed.")

        try:
            doc = docx.Document()

            if isinstance(document_data, dict):
                paragraphs = document_data.get("paragraphs", [])
                for p_info in paragraphs:
                    style = p_info.get("style", "Normal")
                    p = doc.add_paragraph(style=style if style in [s.name for s in doc.styles] else None)
                    align_str = p_info.get("alignment", "left")
                    if align_str == "center":
                        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    elif align_str == "right":
                        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                    elif align_str == "justify":
                        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

                    runs = p_info.get("runs", [])
                    if runs:
                        for r_info in runs:
                            run = p.add_run(r_info.get("text", ""))
                            if r_info.get("bold"):
                                run.bold = True
                            if r_info.get("italic"):
                                run.italic = True
                            if r_info.get("underline"):
                                run.underline = True
                            if r_info.get("font_size"):
                                run.font.size = Pt(r_info["font_size"])
                    else:
                        p.text = p_info.get("text", "")

                tables = document_data.get("tables", [])
                if tables and isinstance(tables[0], list) and tables[0] and not isinstance(tables[0][0], list):
                    tables = [tables]

                for table_data in tables:
                    if table_data and len(table_data) > 0:
                        rows = len(table_data)
                        cols = len(table_data[0]) if rows > 0 else 0
                        table = doc.add_table(rows=rows, cols=cols)
                        table.style = 'Table Grid'
                        for r_idx, row_items in enumerate(table_data):
                            for c_idx, cell_value in enumerate(row_items):
                                if c_idx < cols:
                                    table.cell(r_idx, c_idx).text = str(cell_value)

            elif isinstance(document_data, str):
                for line in document_data.split("\n"):
                    doc.add_paragraph(line)

            doc.save(file_path)
        except Exception as e:
            raise RuntimeError(f"Failed to save Word document ({os.path.basename(file_path)}): {e}")
