import os
from .text import TextHandler
from .spatial import SpatialHandler
from .excel import ExcelHandler
from .docx import DocxHandler
from .pdf import PdfHandler


class HandlerFactory:

    SPATIAL_EXTENSIONS = {
        '.geojson', '.gpkg', '.shp', '.kml', '.kmz',
        '.fgb', '.gpx', '.geojsonseq', '.topojson'
    }

    EXCEL_EXTENSIONS = {'.xlsx', '.xls'}
    WORD_EXTENSIONS = {'.docx', '.doc'}
    PDF_EXTENSIONS = {'.pdf'}

    @staticmethod
    def is_spatial_file(file_path: str) -> bool:
        ext = os.path.splitext(file_path)[1].lower()
        if ext in HandlerFactory.SPATIAL_EXTENSIONS:
            return True

        if ext == '.json':
            try:
                if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        header = f.read(4096).lower()
                        if any(marker in header for marker in ('"featurecollection"', '"features"', '"geometry"', '"coordinates"')):
                            return True
            except Exception:
                pass

        if ext == '.csv':
            try:
                if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        header = f.readline().lower()
                        if any(marker in header for marker in ('geometry', 'wkt', 'geom', 'the_geom', 'shape', 'wkt_geometry')):
                            return True
                        has_lat = any(marker in header for marker in ('lat', 'latitude', 'enlem', 'point_y', 'kuzey'))
                        has_lon = any(marker in header for marker in ('lon', 'lng', 'longitude', 'boylam', 'point_x', 'dogu'))
                        if has_lat and has_lon:
                            return True
            except Exception:
                pass

        return False

    @staticmethod
    def is_excel_file(file_path: str) -> bool:
        ext = os.path.splitext(file_path)[1].lower()
        return ext in HandlerFactory.EXCEL_EXTENSIONS or ext == '.csv'

    @staticmethod
    def is_word_file(file_path: str) -> bool:
        ext = os.path.splitext(file_path)[1].lower()
        return ext in HandlerFactory.WORD_EXTENSIONS

    @staticmethod
    def is_pdf_file(file_path: str) -> bool:
        ext = os.path.splitext(file_path)[1].lower()
        return ext in HandlerFactory.PDF_EXTENSIONS

    @staticmethod
    def get_handler(file_path: str):
        if HandlerFactory.is_spatial_file(file_path):
            return SpatialHandler()
        elif HandlerFactory.is_excel_file(file_path):
            return ExcelHandler()
        elif HandlerFactory.is_word_file(file_path):
            return DocxHandler()
        elif HandlerFactory.is_pdf_file(file_path):
            return PdfHandler()
        return TextHandler()