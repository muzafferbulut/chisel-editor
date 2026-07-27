from .text import TextHandler
from .spatial import SpatialHandler
import os


class HandlerFactory:

    @staticmethod
    def get_handler(file_path: str):
        extension = os.path.splitext(file_path)[1].lower()

        if extension in ['.txt', '.md', '.log']:
            return TextHandler()

        elif extension in ['.geojson', '.kml', '.kmz','.shp']:
            return SpatialHandler()

        raise ValueError(f"Unsupported file extension: {extension}")