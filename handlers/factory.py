import os
from .text import TextHandler
from .spatial import SpatialHandler


class HandlerFactory:

    SPATIAL_EXTENSIONS = {
        '.geojson', '.gpkg', '.shp', '.kml', '.kmz',
        '.fgb', '.gpx', '.geojsonseq', '.topojson'
    }

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
                        first_line = f.readline().lower()
                        if 'geometry' in first_line or 'wkt' in first_line or ('lat' in first_line and 'lon' in first_line):
                            return True
            except Exception:
                pass

        return False

    @staticmethod
    def get_handler(file_path: str):
        if HandlerFactory.is_spatial_file(file_path):
            return SpatialHandler()
        return TextHandler()
        return TextHandler()