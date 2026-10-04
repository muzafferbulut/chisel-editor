import os
import io
import geopandas as gpd
import fiona
from .base import BaseHandler
import pandas as pd
from core.spatial_ops import SpatialOps

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
                gdfs = []
                for l in layers:
                    try:
                        gdfs.append(gpd.read_file(file_path, layer=l, engine="pyogrio"))
                    except Exception:
                        gdfs.append(gpd.read_file(file_path, layer=l))
                gdf = pd.concat(gdfs, ignore_index=True)
            elif layer_name:
                try:
                    gdf = gpd.read_file(file_path, layer=layer_name, engine="pyogrio")
                except Exception:
                    gdf = gpd.read_file(file_path, layer=layer_name)
            else:
                try:
                    gdf = gpd.read_file(file_path, engine="pyogrio")
                except Exception:
                    gdf = gpd.read_file(file_path)

            if gdf.crs is None:
                gdf.set_crs("EPSG:4326", inplace=True)

            # Sanitize and serialize cleanly
            clean_gdf = SpatialOps.sanitize_gdf_for_json(gdf)
            return clean_gdf.to_json()

        except MultipleLayersError:
            raise
        except Exception as e:
            raise RuntimeError(f"Failed to read spatial data: {str(e)}")

    def write(self, file_path: str, content: str) -> bool:
        try:
            gdf = gpd.read_file(io.StringIO(content))
            return SpatialOps.export_file(gdf, file_path)
        except Exception as e:
            raise RuntimeError(f"Failed to write spatial data: {str(e)}")