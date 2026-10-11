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
        import csv
        encoding = "utf-8"
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                sample = f.read(8192)
        except UnicodeDecodeError:
            try:
                encoding = "cp1254"
                with open(file_path, "r", encoding="cp1254") as f:
                    sample = f.read(8192)
            except UnicodeDecodeError:
                encoding = "latin1"
                with open(file_path, "r", encoding="latin1") as f:
                    sample = f.read(8192)

        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            sep = dialect.delimiter
        except Exception:
            sep = ","

        df = pd.read_csv(file_path, sep=sep, encoding=encoding)
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
                        gdf.set_crs("EPSG:4326", inplace=True)
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
                                    gdf.set_crs("EPSG:4326", inplace=True)
                                return gdf

            if file_path.lower().endswith(".dxf"):
                try:
                    gdf = gpd.read_file(file_path)
                    if hasattr(gdf, "crs") and gdf.crs is None:
                        gdf.set_crs("EPSG:4326", inplace=True)
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

            if hasattr(gdf, "crs") and gdf.crs is None:
                gdf.set_crs("EPSG:4326", inplace=True)

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