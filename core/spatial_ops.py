import os
import io
import json
import numpy as np
import pandas as pd
import geopandas as gpd
import shapely
from shapely.geometry import shape, mapping
from pyproj import CRS


class SpatialOps:
    """
    High-performance, robust utility for spatial data operations.
    Handles GeoDataFrames, conversions, reprojections, geometry validations,
    simplifications, and format exports.
    """

    @staticmethod
    def sanitize_gdf_for_json(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """
        Sanitizes non-serializable columns (datetime, Timestamps, NaT, NaN, categorical)
        so that gdf.to_json() succeeds without serialization errors.
        """
        gdf_clean = gdf.copy()
        for col in gdf_clean.columns:
            if col == gdf_clean.geometry.name:
                continue

            # Convert datetime / timedelta to ISO string
            if pd.api.types.is_datetime64_any_dtype(gdf_clean[col]) or pd.api.types.is_timedelta64_dtype(gdf_clean[col]):
                gdf_clean[col] = gdf_clean[col].astype(str).replace({'NaT': None, 'nan': None, '<NA>': None, 'None': None})
            elif pd.api.types.is_categorical_dtype(gdf_clean[col]):
                gdf_clean[col] = gdf_clean[col].astype(str)
            elif gdf_clean[col].dtype == 'object':
                gdf_clean[col] = gdf_clean[col].apply(
                    lambda x: x.isoformat() if isinstance(x, (pd.Timestamp, np.datetime64)) else x
                )
                gdf_clean[col] = gdf_clean[col].replace({pd.NaT: None, 'NaT': None, np.nan: None})
            elif pd.api.types.is_float_dtype(gdf_clean[col]):
                gdf_clean[col] = gdf_clean[col].replace({np.nan: None, np.inf: None, -np.inf: None})

        return gdf_clean

    @staticmethod
    def to_geojson_str(gdf: gpd.GeoDataFrame, indent: int = None) -> str:
        """
        Converts GeoDataFrame to clean GeoJSON string.
        """
        clean_gdf = SpatialOps.sanitize_gdf_for_json(gdf)
        raw_json = clean_gdf.to_json()
        if indent is not None and indent > 0:
            try:
                parsed = json.loads(raw_json)
                return json.dumps(parsed, indent=indent, ensure_ascii=False)
            except Exception:
                pass
        return raw_json

    @staticmethod
    def parse_geojson_str(content: str) -> gpd.GeoDataFrame:
        """
        Parses a GeoJSON string into a GeoDataFrame.
        Ensures EPSG:4326 default if not explicitly defined in CRS.
        """
        gdf = gpd.read_file(io.StringIO(content))
        if gdf.crs is None:
            gdf.set_crs("EPSG:4326", inplace=True)
        return gdf

    @staticmethod
    def is_valid_geojson_content(content: str) -> bool:
        """
        Quickly tests if string is valid GeoJSON Feature or FeatureCollection.
        """
        if not content or len(content.strip()) < 10:
            return False
        stripped = content.strip()
        if not (stripped.startswith("{") and stripped.endswith("}")):
            return False
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                t = data.get("type", "")
                if t in ("FeatureCollection", "Feature", "GeometryCollection", "Point", "MultiPoint",
                         "LineString", "MultiLineString", "Polygon", "MultiPolygon"):
                    return True
        except Exception:
            pass
        return False

    @staticmethod
    def reproject_gdf(gdf: gpd.GeoDataFrame, target_crs: str) -> gpd.GeoDataFrame:
        """
        Reprojects GeoDataFrame to target CRS.
        """
        if gdf.crs is None:
            raise ValueError("Data has no CRS defined. Please set CRS first before reprojecting.")
        return gdf.to_crs(target_crs)

    @staticmethod
    def set_crs_gdf(gdf: gpd.GeoDataFrame, crs_str: str) -> gpd.GeoDataFrame:
        """
        Sets or overrides CRS on GeoDataFrame without coordinate modification.
        """
        new_gdf = gdf.copy()
        new_gdf.set_crs(crs_str, allow_override=True, inplace=True)
        return new_gdf

    @staticmethod
    def validate_and_repair(gdf: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, int]:
        """
        Validates geometries and repairs invalid ones using shapely.make_valid.
        Returns: (repaired_gdf, count_of_repaired_geometries)
        """
        new_gdf = gdf.copy()
        invalid_mask = ~new_gdf.geometry.is_valid
        invalid_count = int(invalid_mask.sum())

        if invalid_count > 0:
            new_gdf.loc[invalid_mask, 'geometry'] = new_gdf.loc[invalid_mask, 'geometry'].apply(
                lambda geom: shapely.make_valid(geom) if geom is not None and not geom.is_empty else geom
            )
        return new_gdf, invalid_count

    @staticmethod
    def count_vertices(gdf: gpd.GeoDataFrame) -> int:
        """
        Counts total number of vertices across all geometries in the GeoDataFrame.
        """
        total = 0
        for geom in gdf.geometry:
            if geom is not None and not geom.is_empty:
                total += shapely.get_num_coordinates(geom)
        return int(total)

    @staticmethod
    def simplify_geometries(gdf: gpd.GeoDataFrame, tolerance: float,
                            preserve_topology: bool = True) -> tuple[gpd.GeoDataFrame, int, int]:
        """
        Simplifies geometries using Douglas-Peucker algorithm.
        Returns: (simplified_gdf, original_vertices, simplified_vertices)
        """
        orig_vertices = SpatialOps.count_vertices(gdf)
        new_gdf = gdf.copy()
        new_gdf['geometry'] = new_gdf.geometry.simplify(tolerance=tolerance, preserve_topology=preserve_topology)
        simplified_vertices = SpatialOps.count_vertices(new_gdf)
        return new_gdf, orig_vertices, simplified_vertices

    @staticmethod
    def calculate_centroids(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """
        Calculates centroid points for all features in the GeoDataFrame.
        """
        import warnings
        new_gdf = gdf.copy()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=UserWarning)
            new_gdf['geometry'] = gdf.geometry.centroid
        return new_gdf

    @staticmethod
    def calculate_bounding_boxes(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """
        Calculates bounding envelope polygon for each feature.
        """
        new_gdf = gdf.copy()
        new_gdf['geometry'] = gdf.geometry.envelope
        return new_gdf

    @staticmethod
    def get_summary(gdf: gpd.GeoDataFrame) -> dict:
        """
        Extracts comprehensive spatial summary information.
        """
        feature_count = len(gdf)
        crs_str = str(gdf.crs) if gdf.crs else "Unset"
        
        # Geometry types breakdown
        geom_types = {}
        for geom in gdf.geometry:
            if geom is not None and not geom.is_empty:
                gt = geom.geom_type
                geom_types[gt] = geom_types.get(gt, 0) + 1
            else:
                geom_types["Empty/None"] = geom_types.get("Empty/None", 0) + 1

        # Bounds (minx, miny, maxx, maxy)
        try:
            total_bounds = gdf.total_bounds.tolist() if feature_count > 0 else [0, 0, 0, 0]
        except Exception:
            total_bounds = [0, 0, 0, 0]

        # Non-geometry columns with sample types
        columns_info = []
        for col in gdf.columns:
            if col != gdf.geometry.name:
                columns_info.append({
                    "name": col,
                    "dtype": str(gdf[col].dtype),
                    "non_null": int(gdf[col].count())
                })

        vertex_count = SpatialOps.count_vertices(gdf)
        valid_count = int(gdf.geometry.is_valid.sum()) if feature_count > 0 else 0

        return {
            "feature_count": feature_count,
            "crs": crs_str,
            "geometry_types": geom_types,
            "total_bounds": total_bounds,
            "vertex_count": vertex_count,
            "valid_count": valid_count,
            "all_valid": valid_count == feature_count,
            "columns": columns_info
        }

    @staticmethod
    def export_file(gdf: gpd.GeoDataFrame, target_path: str, driver: str = None) -> bool:
        """
        Exports GeoDataFrame to various GIS vector formats with proper driver options.
        Supports: .geojson, .gpkg, .shp, .kml, .fgb, .csv
        """
        ext = os.path.splitext(target_path)[1].lower()
        clean_gdf = SpatialOps.sanitize_gdf_for_json(gdf)

        if ext in ('.geojson', '.json'):
            clean_gdf.to_file(target_path, driver='GeoJSON')
        elif ext == '.gpkg':
            clean_gdf.to_file(target_path, driver='GPKG', engine='pyogrio')
        elif ext == '.shp':
            # ESRI Shapefile column name limit: 10 characters
            shp_gdf = clean_gdf.copy()
            new_cols = {}
            seen = set()
            for col in shp_gdf.columns:
                if col == shp_gdf.geometry.name:
                    continue
                short = col[:10]
                idx = 1
                while short in seen:
                    short = f"{col[:7]}_{idx}"
                    idx += 1
                seen.add(short)
                new_cols[col] = short
            shp_gdf.rename(columns=new_cols, inplace=True)
            shp_gdf.to_file(target_path, driver='ESRI Shapefile', engine='pyogrio')
        elif ext == '.kml':
            # KML requires EPSG:4326
            kml_gdf = clean_gdf.copy()
            if kml_gdf.crs and str(kml_gdf.crs) != "EPSG:4326":
                kml_gdf = kml_gdf.to_crs("EPSG:4326")
            elif not kml_gdf.crs:
                kml_gdf.set_crs("EPSG:4326", inplace=True)
            kml_gdf.to_file(target_path, driver='KML')
        elif ext == '.fgb':
            clean_gdf.to_file(target_path, driver='FlatGeobuf', engine='pyogrio')
        elif ext == '.csv':
            # Export attributes with WKT geometry
            csv_df = pd.DataFrame(clean_gdf)
            csv_df['wkt_geometry'] = clean_gdf.geometry.apply(lambda g: g.wkt if g is not None else "")
            geom_col = clean_gdf.geometry.name
            if geom_col in csv_df.columns:
                csv_df = csv_df.drop(columns=[geom_col])
            csv_df.to_csv(target_path, index=False, encoding='utf-8')
        else:
            # Fallback
            clean_gdf.to_file(target_path, engine='pyogrio')
        return True
