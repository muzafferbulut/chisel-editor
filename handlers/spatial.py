import os
import io
import json
import geopandas as gpd
import fiona
from .base import BaseHandler
import pandas as pd

fiona.drvsupport.supported_drivers['KML'] = 'rw'
fiona.drvsupport.supported_drivers['LIBKML'] = 'rw'

class MultipleLayersError(Exception):

    def __init__(self, layers):
        self.layers = layers
        super().__init__("Multiple layers detected.")

class SpatialHandler(BaseHandler):

    @property
    def is_spatial(self) -> bool:
        return True

    def read(self, file_path: str, **kwargs) -> str:
        try:
            merge_all = kwargs.get('merge_all', False)
            layer_name = kwargs.get('layer_name', None)
                         
            layers = fiona.listlayers(file_path)
                         
            if len(layers) > 1 and not (merge_all or layer_name):
                raise MultipleLayersError(layers)

            if merge_all:
                gdfs = [gpd.read_file(file_path, layer=l) for l in layers]
                gdf = pd.concat(gdfs, ignore_index=True)
            elif layer_name:
                gdf = gpd.read_file(file_path, layer=layer_name)
            else:
                gdf = gpd.read_file(file_path)

            for col in gdf.columns:
                if col != gdf.geometry.name:
                    if pd.api.types.is_datetime64_any_dtype(gdf[col]) or pd.api.types.is_timedelta64_dtype(gdf[col]):
                        gdf[col] = gdf[col].astype(str).replace({'NaT': None, 'nan': None})
                    elif gdf[col].dtype == 'object':
                        gdf[col] = gdf[col].apply(
                            lambda x: None if x is pd.NaT else (x.isoformat() if hasattr(x, 'isoformat') else x)
                        )

            raw_geojson = gdf.to_json()
            parsed_json = json.loads(raw_geojson)
            return json.dumps(parsed_json, indent=4, ensure_ascii=False)
                     
        except MultipleLayersError:
            raise
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