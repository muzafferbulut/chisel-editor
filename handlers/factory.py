from .text import TextHandler
from .spatial import SpatialHandler
import os


class HandlerFactory:

    @staticmethod
    def get_handler(file_path: str):
        extension = os.path.splitext(file_path)[1].lower()

        if extension in ['.geojson', '.json', '.kml', '.kmz', '.shp']:
            return SpatialHandler()

        return TextHandler()