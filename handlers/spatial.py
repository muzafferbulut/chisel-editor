import os
import io
import json
import geopandas as gpd
import fiona
from .base import BaseHandler

fiona.drvsupport.supported_drivers['KML'] = 'rw'
fiona.drvsupport.supported_drivers['LIBKML'] = 'rw'

class SpatialHandler(BaseHandler):

    @property
    def is_spatial(self) -> bool:
        return True

    def read(self, file_path: str) -> str:
        try:
            gdf = gpd.read_file(file_path)
            raw_geojson = gdf.to_json()
            parsed_json = json.loads(raw_geojson)
            return json.dumps(parsed_json, indent=4, ensure_ascii=False)
            
        except Exception as e:
            raise RuntimeError(f"Failed to read spatial data: {str(e)}")

    def write(self, file_path: str, content: str) -> bool:
        try:
            gdf = gpd.read_file(io.StringIO(content))
            ext = os.path.splitext(file_path)[1].lower()
            
            if ext == '.geojson':
                gdf.to_file(file_path, driver='GeoJSON')
            elif ext == '.kml':
                gdf.to_file(file_path, driver='KML')
            elif ext == '.shp':
                gdf.to_file(file_path)
            else:
                raise ValueError(f"Unsupported spatial export format: {ext}")
            return True
            
        except Exception as e:
            raise RuntimeError(f"Failed to write spatial data: {str(e)}")