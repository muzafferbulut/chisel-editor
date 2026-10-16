import io
import os
import warnings
import geopandas as gpd
import fiona
from .base import BaseHandler
import pandas as pd
from core.spatial_ops import SpatialOps

warnings.filterwarnings("ignore", category=RuntimeWarning, message="Several features with id.*")
warnings.filterwarnings("ignore", category=RuntimeWarning, module="pyogrio.*")

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

    @staticmethod
    def read_csv_spatial(file_path: str) -> gpd.GeoDataFrame:
        """
        Reads a CSV file and constructs a GeoDataFrame using WKT or coordinate pairs (lat/lon, y/x).
        Supports auto-detection of delimiters (, ; \t |) and encodings (utf-8, cp1254, latin1).
        """
        from core.io_utils import read_delimited_file
        df, _, _ = read_delimited_file(file_path)
        if df.empty:
            return gpd.GeoDataFrame(df, crs="EPSG:4326")

        cols_lower = {c: str(c).strip().lower() for c in df.columns}

        # 1. Check for WKT / geometry column
        wkt_candidates = ("wkt", "geometry", "geom", "the_geom", "shape", "wkt_geometry")
        wkt_col = None
        for orig, low in cols_lower.items():
            if low in wkt_candidates:
                wkt_col = orig
                break

        if wkt_col:
            import shapely
            raw_wkt = df[wkt_col].fillna("").astype(str).values
            geometries = shapely.from_wkt(raw_wkt, on_invalid='ignore')
            gdf = gpd.GeoDataFrame(df, geometry=geometries, crs="EPSG:4326")
            return gdf

        # 2. Check for coordinate pairs (lat/lon, y/x, enlem/boylam)
        lat_candidates = ("lat", "latitude", "enlem", "y", "point_y", "coord_y", "kuzey")
        lon_candidates = ("lon", "lng", "long", "longitude", "boylam", "x", "point_x", "coord_x", "dogu")

        lat_col = None
        lon_col = None

        for orig, low in cols_lower.items():
            if not lat_col and low in lat_candidates:
                lat_col = orig
            elif not lon_col and low in lon_candidates:
                lon_col = orig

        if lat_col and lon_col:
            def to_clean_float(series):
                if series.dtype == object:
                    clean_str = series.astype(str).str.strip().str.replace(",", ".")
                    return pd.to_numeric(clean_str, errors="coerce")
                return pd.to_numeric(series, errors="coerce")

            x = to_clean_float(df[lon_col])
            y = to_clean_float(df[lat_col])
            geometries = gpd.points_from_xy(x, y)
            gdf = gpd.GeoDataFrame(df, geometry=geometries, crs="EPSG:4326")
            return gdf

        return None

    def read_gdf(self, file_path: str, **kwargs) -> gpd.GeoDataFrame:
        try:
            if file_path.lower().endswith(".csv"):
                csv_gdf = self.read_csv_spatial(file_path)
                if csv_gdf is not None:
                    return csv_gdf
                # If no spatial columns, fallback to empty geometry GeoDataFrame
                import csv
                try:
                    df = pd.read_csv(file_path)
                except Exception:
                    df = pd.read_csv(file_path, sep=None, engine="python")
                return gpd.GeoDataFrame(df, geometry=[None] * len(df), crs="EPSG:4326")

            if file_path.lower().endswith(".kmz"):
                import zipfile
                import tempfile
                try:
                    gdf = gpd.read_file(file_path)
                    if hasattr(gdf, "crs") and gdf.crs is None:
                        gdf = gdf.set_crs("EPSG:4326")
                    return gdf
                except Exception:
                    with zipfile.ZipFile(file_path, 'r') as zf:
                        kml_members = [m for m in zf.namelist() if m.lower().endswith('.kml')]
                        if kml_members:
                            with tempfile.TemporaryDirectory() as tmp_dir:
                                zf.extract(kml_members[0], tmp_dir)
                                extracted_kml = os.path.join(tmp_dir, kml_members[0])
                                gdf = gpd.read_file(extracted_kml)
                                if hasattr(gdf, "crs") and gdf.crs is None:
                                    gdf = gdf.set_crs("EPSG:4326")
                                return gdf

            if file_path.lower().endswith(".dxf"):
                try:
                    gdf = gpd.read_file(file_path)
                    if hasattr(gdf, "crs") and gdf.crs is None:
                        gdf = gdf.set_crs("EPSG:4326")
                    return gdf
                except Exception as e:
                    raise RuntimeError(f"Failed to read DXF file: {str(e)}")

            merge_all = kwargs.get('merge_all', False)
            layer_name = kwargs.get('layer_name', None)

            try:
                import pyogrio
                layers = [l[0] for l in pyogrio.list_layers(file_path)]
            except Exception:
                layers = fiona.listlayers(file_path)

            if len(layers) > 1 and not (merge_all or layer_name):
                raise MultipleLayersError(layers)

            if merge_all:
                gdfs = []
                for l in layers:
                    try:
                        lgdf = gpd.read_file(file_path, layer=l, engine="pyogrio")
                    except Exception:
                        lgdf = gpd.read_file(file_path, layer=l)
                    if lgdf is not None and not lgdf.empty:
                        gdfs.append(lgdf)

                if not gdfs:
                    gdf = gpd.GeoDataFrame()
                elif len(gdfs) == 1:
                    gdf = gdfs[0]
                else:
                    base_crs = gdfs[0].crs or "EPSG:4326"
                    aligned = []
                    for g in gdfs:
                        if hasattr(g, 'crs') and g.crs is not None and g.crs != base_crs:
                            try:
                                aligned.append(g.to_crs(base_crs))
                            except Exception:
                                aligned.append(g)
                        else:
                            aligned.append(g)
                    concat_df = pd.concat(aligned, ignore_index=True)
                    geom_name = gdfs[0].geometry.name if hasattr(gdfs[0], 'geometry') and gdfs[0].geometry.name in concat_df.columns else 'geometry'
                    gdf = gpd.GeoDataFrame(concat_df, geometry=geom_name, crs=base_crs)
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

            if hasattr(gdf, "crs") and gdf.crs is None:
                gdf = gdf.set_crs("EPSG:4326")

            return gdf
        except MultipleLayersError:
            raise
        except Exception as e:
            raise RuntimeError(f"Failed to read spatial data: {str(e)}")

    def read(self, file_path: str, **kwargs) -> str:
        gdf = self.read_gdf(file_path, **kwargs)
        clean_gdf = SpatialOps.sanitize_gdf_for_json(gdf)
        return clean_gdf.to_json()

    def write(self, file_path: str, content: object) -> bool:
        try:
            if isinstance(content, gpd.GeoDataFrame):
                gdf = content
            elif isinstance(content, str):
                gdf = gpd.read_file(io.StringIO(content))
            elif isinstance(content, dict):
                import json
                gdf = gpd.read_file(io.StringIO(json.dumps(content)))
            else:
                gdf = gpd.GeoDataFrame(content)
            return SpatialOps.export_file(gdf, file_path)
        except Exception as e:
            raise RuntimeError(f"Failed to write spatial data: {str(e)}")