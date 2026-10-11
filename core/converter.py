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
            try:
                df = pd.read_csv(source_path)
            except Exception:
                df = pd.read_csv(source_path, sep=None, engine='python')
            cls._export_tabular(df, target_path, target_ext)
            return target_path

        # 4. Word Document Conversion
        if src_ext in ('.docx', '.doc'):
            handler = DocxHandler()
            content = handler.read(source_path)
            if target_ext in ('.txt', '.md'):
                # Strip HTML tags for clean text/md
                import re
                clean_text = re.sub(r'<[^>]+>', '\n', content)
                clean_text = re.sub(r'\n+', '\n', clean_text).strip()
                with open(target_path, 'w', encoding='utf-8') as f:
                    f.write(clean_text)
            else:
                with open(target_path, 'w', encoding='utf-8') as f:
                    f.write(content)
            return target_path

        raise ValueError(f"Unsupported conversion from {src_ext} to {target_ext}")

    @staticmethod
    def _export_tabular(df: pd.DataFrame, target_path: str, target_ext: str):
        if target_ext == '.csv':
            df.to_csv(target_path, index=False, encoding='utf-8')
        elif target_ext == '.xlsx':
            df.to_excel(target_path, index=False)
        elif target_ext == '.json':
            df.to_json(target_path, orient='records', indent=2, force_ascii=False)
        elif target_ext == '.html':
            df.to_html(target_path, index=False)
        else:
            raise ValueError(f"Unsupported tabular output format: {target_ext}")

