import os
import pandas as pd
from handlers.factory import HandlerFactory
from handlers.spatial import SpatialHandler
from handlers.docx import DocxHandler
from core.spatial_ops import SpatialOps


class FileConverter:
    """
    Central file conversion engine for spatial, tabular, and document formats.
    """

    SPATIAL_TARGETS = [
        ('.geojson', 'GeoJSON (*.geojson)'),
        ('.shp', 'ESRI Shapefile (*.shp)'),
        ('.gpkg', 'GeoPackage (*.gpkg)'),
        ('.kml', 'Google KML (*.kml)'),
        ('.kmz', 'Google KMZ (*.kmz)'),
        ('.dxf', 'AutoCAD DXF (*.dxf)'),
        ('.fgb', 'FlatGeobuf (*.fgb)'),
        ('.csv', 'CSV with WKT (*.csv)')
    ]

    EXCEL_TARGETS = [
        ('.csv', 'CSV (Comma Delimited) (*.csv)'),
        ('.json', 'JSON Data (*.json)'),
        ('.html', 'HTML Table (*.html)')
    ]

    CSV_TABULAR_TARGETS = [
        ('.xlsx', 'Excel Workbook (*.xlsx)'),
        ('.json', 'JSON Data (*.json)'),
        ('.html', 'HTML Table (*.html)')
    ]

    DOCX_TARGETS = [
        ('.html', 'HTML Document (*.html)'),
        ('.md', 'Markdown Document (*.md)'),
        ('.txt', 'Plain Text (*.txt)')
    ]

    @classmethod
    def get_conversion_targets(cls, file_path: str) -> list:
        """
        Returns list of (extension, label) available for the given file.
        """
        if not file_path or not os.path.isfile(file_path):
            return []

        ext = os.path.splitext(file_path)[1].lower()

        # Check if spatial
        if HandlerFactory.is_spatial_file(file_path):
            return [(t_ext, t_lbl) for t_ext, t_lbl in cls.SPATIAL_TARGETS if t_ext != ext]

        # Check if Excel
        if ext in ('.xlsx', '.xls'):
            return [(t_ext, t_lbl) for t_ext, t_lbl in cls.EXCEL_TARGETS if t_ext != ext]

        # Check if Tabular CSV
        if ext == '.csv':
            return [(t_ext, t_lbl) for t_ext, t_lbl in cls.CSV_TABULAR_TARGETS if t_ext != ext]

        # Check if Word
        if ext in ('.docx', '.doc'):
            return [(t_ext, t_lbl) for t_ext, t_lbl in cls.DOCX_TARGETS if t_ext != ext]

        return []

    @classmethod
    def convert(cls, source_path: str, target_ext: str, target_path: str = None) -> str:
        """
        Converts the source file to target_ext and returns the resulting file path.
        """
        if not os.path.exists(source_path):
            raise FileNotFoundError(f"Source file not found: {source_path}")

        target_ext = target_ext.lower()
        if not target_ext.startswith('.'):
            target_ext = '.' + target_ext

        if not target_path:
            base, _ = os.path.splitext(source_path)
            target_path = f"{base}{target_ext}"
            if target_path == source_path:
                target_path = f"{base}_converted{target_ext}"

        # 1. Spatial Conversion
        if HandlerFactory.is_spatial_file(source_path):
            handler = SpatialHandler()
            gdf = handler.read_gdf(source_path)
            if gdf is None or len(gdf) == 0:
                raise ValueError("Spatial file contains no valid geometry or features.")
            SpatialOps.export_file(gdf, target_path)
            return target_path

        # 2. Excel Conversion
        src_ext = os.path.splitext(source_path)[1].lower()
        if src_ext in ('.xlsx', '.xls'):
            df = pd.read_excel(source_path)
            cls._export_tabular(df, target_path, target_ext)
            return target_path

        # 3. Tabular CSV Conversion
        if src_ext == '.csv':
            from core.io_utils import read_delimited_file
            df, _, _ = read_delimited_file(source_path)
            cls._export_tabular(df, target_path, target_ext)
            return target_path

        # 4. Word Document Conversion
        if src_ext in ('.docx', '.doc'):
            handler = DocxHandler()
            doc_data = handler.read(source_path)
            if target_ext == '.txt':
                content = cls._docx_to_text(doc_data)
            elif target_ext == '.md':
                content = cls._docx_to_markdown(doc_data)
            elif target_ext == '.html':
                content = cls._docx_to_html(doc_data)
            else:
                raise ValueError(f"Unsupported Word output format: {target_ext}")

            with open(target_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return target_path

        raise ValueError(f"Unsupported conversion from {src_ext} to {target_ext}")

    @staticmethod
    def _docx_to_text(data) -> str:
        if isinstance(data, str):
            import re
            clean = re.sub(r'<[^>]+>', '\n', data)
            return re.sub(r'\n+', '\n', clean).strip()

        if not isinstance(data, dict):
            return str(data)

        lines = []
        for p in data.get("paragraphs", []):
            txt = p.get("text", "").strip()
            if txt:
                lines.append(txt)

        for table in data.get("tables", []):
            if table:
                lines.append("")
                for row in table:
                    lines.append("\t".join(str(cell) for cell in row))
                lines.append("")

        return "\n\n".join(lines) if lines else data.get("full_text", "")

    @staticmethod
    def _docx_to_markdown(data) -> str:
        if isinstance(data, str):
            import re
            clean = re.sub(r'<[^>]+>', '\n', data)
            return re.sub(r'\n+', '\n', clean).strip()

        if not isinstance(data, dict):
            return str(data)

        md_parts = []
        for p in data.get("paragraphs", []):
            style = p.get("style", "").lower()
            text = p.get("text", "").strip()
            if not text:
                continue

            if "heading 1" in style or style == "title":
                md_parts.append(f"# {text}")
            elif "heading 2" in style:
                md_parts.append(f"## {text}")
            elif "heading 3" in style:
                md_parts.append(f"### {text}")
            elif "heading 4" in style:
                md_parts.append(f"#### {text}")
            else:
                runs = p.get("runs", [])
                if runs:
                    run_texts = []
                    for r in runs:
                        rtxt = r.get("text", "")
                        if not rtxt:
                            continue
                        if r.get("bold") and r.get("italic"):
                            rtxt = f"***{rtxt}***"
                        elif r.get("bold"):
                            rtxt = f"**{rtxt}**"
                        elif r.get("italic"):
                            rtxt = f"*{rtxt}*"
                        run_texts.append(rtxt)
                    para_md = "".join(run_texts).strip()
                    md_parts.append(para_md if para_md else text)
                else:
                    md_parts.append(text)

        for table in data.get("tables", []):
            if table and len(table) > 0:
                md_parts.append("")
                header_row = table[0]
                cols_count = len(header_row)
                md_parts.append("| " + " | ".join(str(c).replace("\n", " ") for c in header_row) + " |")
                md_parts.append("| " + " | ".join(["---"] * cols_count) + " |")
                for row in table[1:]:
                    padded_row = list(row) + [""] * (cols_count - len(row))
                    md_parts.append("| " + " | ".join(str(c).replace("\n", " ") for c in padded_row[:cols_count]) + " |")
                md_parts.append("")

        return "\n\n".join(md_parts)

    @staticmethod
    def _docx_to_html(data) -> str:
        if isinstance(data, str):
            return data

        if not isinstance(data, dict):
            return f"<!DOCTYPE html><html><body><p>{data}</p></body></html>"

        import html
        html_parts = [
            "<!DOCTYPE html>",
            "<html>",
            "<head>",
            '  <meta charset="utf-8">',
            "  <style>",
            "    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; margin: 2rem; color: #1e293b; }",
            "    table { border-collapse: collapse; width: 100%; margin: 1rem 0; }",
            "    th, td { border: 1px solid #cbd5e1; padding: 8px 12px; text-align: left; }",
            "    th { background-color: #f1f5f9; font-weight: 600; }",
            "    p { margin-bottom: 0.8rem; }",
            "  </style>",
            "</head>",
            "<body>"
        ]

        for p in data.get("paragraphs", []):
            style = p.get("style", "").lower()
            text = p.get("text", "").strip()
            align = p.get("alignment", "left")
            align_style = f" style='text-align: {align};'" if align != "left" else ""

            if not text:
                continue

            tag = "p"
            if "heading 1" in style or style == "title":
                tag = "h1"
            elif "heading 2" in style:
                tag = "h2"
            elif "heading 3" in style:
                tag = "h3"
            elif "heading 4" in style:
                tag = "h4"

            runs = p.get("runs", [])
            if runs:
                run_htmls = []
                for r in runs:
                    rtxt = r.get("text", "")
                    if not rtxt:
                        continue
                    escaped_txt = html.escape(rtxt)
                    if r.get("bold"):
                        escaped_txt = f"<strong>{escaped_txt}</strong>"
                    if r.get("italic"):
                        escaped_txt = f"<em>{escaped_txt}</em>"
                    if r.get("underline"):
                        escaped_txt = f"<u>{escaped_txt}</u>"
                    run_htmls.append(escaped_txt)
                inner = "".join(run_htmls)
            else:
                inner = html.escape(text)

            html_parts.append(f"  <{tag}{align_style}>{inner}</{tag}>")

        for table in data.get("tables", []):
            if table and len(table) > 0:
                html_parts.append("  <table>")
                html_parts.append("    <thead><tr>" + "".join(f"<th>{html.escape(str(c))}</th>" for c in table[0]) + "</tr></thead>")
                if len(table) > 1:
                    html_parts.append("    <tbody>")
                    for row in table[1:]:
                        html_parts.append("      <tr>" + "".join(f"<td>{html.escape(str(c))}</td>" for c in row) + "</tr>")
                    html_parts.append("    </tbody>")
                html_parts.append("  </table>")

        html_parts.append("</body>")
        html_parts.append("</html>")
        return "\n".join(html_parts)

    @staticmethod
    def _export_tabular(df: pd.DataFrame, target_path: str, target_ext: str):
        if target_ext == '.csv':
            df.to_csv(target_path, index=False, encoding='utf-8-sig')
        elif target_ext == '.xlsx':
            df.to_excel(target_path, index=False)
        elif target_ext == '.json':
            df.to_json(target_path, orient='records', indent=2, force_ascii=False)
        elif target_ext == '.html':
            df.to_html(target_path, index=False)
        else:
            raise ValueError(f"Unsupported tabular output format: {target_ext}")

