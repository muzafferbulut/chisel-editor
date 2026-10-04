import os
import io
import json
import warnings
import numpy as np
import pandas as pd
import geopandas as gpd
import shapely
from shapely.geometry import Point, Polygon, LineString, MultiPolygon
from pyproj import CRS


class SpatialOps:
    """
    High-performance utility for GIS & spatial operations in Chisel Editor.
    Includes buffering, dissolving, geometry attribute calculations,
    simplification, validation, statistics, and multi-format exports.
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
    def buffer_geometries(gdf: gpd.GeoDataFrame, distance: float, unit: str = "meters") -> gpd.GeoDataFrame:
        """
        Buffers geometries. If CRS is geographic (degrees/EPSG:4326) and unit is 'meters',
        temporarily reprojects to World Mercator (EPSG:3857) or appropriate UTM,
        applies the metric buffer, and reprojects back to the original CRS.
        """
        new_gdf = gdf.copy()
        orig_crs = new_gdf.crs or "EPSG:4326"
        is_geographic = False
        try:
            crs_obj = CRS.from_user_input(orig_crs)
            is_geographic = crs_obj.is_geographic
        except Exception:
            is_geographic = True

        if is_geographic and unit == "meters":
            # Reproject to EPSG:3857 for metric buffer calculation
            metric_gdf = new_gdf.to_crs("EPSG:3857")
            metric_gdf['geometry'] = metric_gdf.geometry.buffer(distance)
            buffered_gdf = metric_gdf.to_crs(orig_crs)
            return buffered_gdf
        else:
            new_gdf['geometry'] = new_gdf.geometry.buffer(distance)
            return new_gdf

    @staticmethod
    def dissolve_geometries(gdf: gpd.GeoDataFrame, by_column: str = None) -> gpd.GeoDataFrame:
        """
        Dissolves geometries by a specified attribute column or merges all features into one.
        """
        clean_gdf = SpatialOps.sanitize_gdf_for_json(gdf)
        if by_column and by_column in clean_gdf.columns:
            dissolved = clean_gdf.dissolve(by=by_column, as_index=False)
        else:
            dissolved = clean_gdf.dissolve(as_index=False)
        return dissolved

    @staticmethod
    def calculate_geometry_attributes(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """
        Calculates geometric properties (Area in km², Perimeter/Length in km, and Point Coordinates)
        using accurate metric projection (EPSG:3857), and adds them as new columns.
        """
        res_gdf = gdf.copy()
        orig_crs = res_gdf.crs or "EPSG:4326"

        try:
            metric_gdf = res_gdf.to_crs("EPSG:3857")
        except Exception:
            metric_gdf = res_gdf

        # Calculate Area for polygons (in km² and hectares)
        has_polygons = any(t in ('Polygon', 'MultiPolygon') for t in metric_gdf.geometry.geom_type)
        if has_polygons:
            res_gdf['area_sqkm'] = (metric_gdf.geometry.area / 1_000_000.0).round(4)
            res_gdf['area_ha'] = (metric_gdf.geometry.area / 10_000.0).round(2)
            res_gdf['perimeter_km'] = (metric_gdf.geometry.length / 1000.0).round(3)

        # Calculate Length for lines (in km)
        has_lines = any(t in ('LineString', 'MultiLineString') for t in metric_gdf.geometry.geom_type)
        if has_lines and not has_polygons:
            res_gdf['length_km'] = (metric_gdf.geometry.length / 1000.0).round(3)

        # Calculate X, Y for points
        has_points = any(t in ('Point', 'MultiPoint') for t in res_gdf.geometry.geom_type)
        if has_points and not has_polygons and not has_lines:
            res_gdf['coord_x'] = res_gdf.geometry.apply(lambda g: round(g.x, 6) if hasattr(g, 'x') else None)
            res_gdf['coord_y'] = res_gdf.geometry.apply(lambda g: round(g.y, 6) if hasattr(g, 'y') else None)

        return res_gdf

    @staticmethod
    def calculate_convex_hull(gdf: gpd.GeoDataFrame, per_feature: bool = False) -> gpd.GeoDataFrame:
        """
        Calculates convex hull geometries.
        If per_feature=True, calculates hull for each feature.
        If per_feature=False, calculates a single hull covering the entire layer.
        """
        if per_feature:
            new_gdf = gdf.copy()
            new_gdf['geometry'] = new_gdf.geometry.convex_hull
            return new_gdf
        else:
            orig_crs = gdf.crs or "EPSG:4326"
            hull = gdf.geometry.unary_union.convex_hull
            return gpd.GeoDataFrame([{"name": "Layer Convex Hull", "geometry": hull}], crs=orig_crs)

    @staticmethod
    def calculate_centroids(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """
        Calculates centroid points for all features in the GeoDataFrame.
        """
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
    def get_column_statistics(gdf: gpd.GeoDataFrame, column_name: str) -> dict:
        """
        Calculates statistical summary for an attribute column.
        """
        if column_name not in gdf.columns:
            raise ValueError(f"Column '{column_name}' not found.")

        series = gdf[column_name]
        total_count = len(series)
        null_count = int(series.isna().sum())
        valid_count = total_count - null_count

        stats = {
            "column": column_name,
            "count": total_count,
            "total_count": total_count,
            "valid_count": valid_count,
            "null_count": null_count,
            "is_numeric": pd.api.types.is_numeric_dtype(series)
        }

        if stats["is_numeric"] and valid_count > 0:
            stats["min"] = float(series.min())
            stats["max"] = float(series.max())
            stats["sum"] = float(series.sum())
            stats["mean"] = float(series.mean())
            stats["std"] = float(series.std()) if valid_count > 1 else 0.0
            stats["median"] = float(series.median())
        else:
            stats["unique_count"] = int(series.nunique())
            top_vals = series.value_counts().head(5).to_dict()
            stats["top_values"] = {str(k): int(v) for k, v in top_vals.items()}

        return stats

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
            kml_gdf = clean_gdf.copy()
            if kml_gdf.crs and str(kml_gdf.crs) != "EPSG:4326":
                kml_gdf = kml_gdf.to_crs("EPSG:4326")
            elif not kml_gdf.crs:
                kml_gdf.set_crs("EPSG:4326", inplace=True)
            kml_gdf.to_file(target_path, driver='KML')
        elif ext == '.fgb':
            clean_gdf.to_file(target_path, driver='FlatGeobuf', engine='pyogrio')
        elif ext == '.csv':
            csv_df = pd.DataFrame(clean_gdf)
            csv_df['wkt_geometry'] = clean_gdf.geometry.apply(lambda g: g.wkt if g is not None else "")
            geom_col = clean_gdf.geometry.name
            if geom_col in csv_df.columns:
                csv_df = csv_df.drop(columns=[geom_col])
            csv_df.to_csv(target_path, index=False, encoding='utf-8')
        else:
            clean_gdf.to_file(target_path, engine='pyogrio')
        return True

    @staticmethod
    def create_sample_spatial_data() -> gpd.GeoDataFrame:
        """
        Generates realistic sample GIS vector data (Turkish provinces & zones)
        for instant testing of attribute table, map preview, and GIS tools.
        """
        features = [
            {
                "city": "İstanbul",
                "region": "Marmara",
                "population": 15907951,
                "category": "Metropol",
                "geometry": Polygon([(28.7, 40.9), (29.2, 40.9), (29.2, 41.2), (28.7, 41.2), (28.7, 40.9)])
            },
            {
                "city": "Ankara",
                "region": "İç Anadolu",
                "population": 5803482,
                "category": "Başkent",
                "geometry": Polygon([(32.6, 39.8), (33.0, 39.8), (33.0, 40.1), (32.6, 40.1), (32.6, 39.8)])
            },
            {
                "city": "İzmir",
                "region": "Ege",
                "population": 4462056,
                "category": "Metropol",
                "geometry": Polygon([(26.9, 38.3), (27.3, 38.3), (27.3, 38.6), (26.9, 38.6), (26.9, 38.3)])
            },
            {
                "city": "Bursa",
                "region": "Marmara",
                "population": 3194720,
                "category": "Sanayi",
                "geometry": Polygon([(28.9, 40.1), (29.3, 40.1), (29.3, 40.35), (28.9, 40.35), (28.9, 40.1)])
            },
            {
                "city": "Antalya",
                "region": "Akdeniz",
                "population": 2688004,
                "category": "Turizm",
                "geometry": Polygon([(30.5, 36.8), (30.9, 36.8), (30.9, 37.1), (30.5, 37.1), (30.5, 36.8)])
            },
            {
                "city": "Konya",
                "region": "İç Anadolu",
                "population": 2296347,
                "category": "Tarım",
                "geometry": Polygon([(32.3, 37.7), (32.7, 37.7), (32.7, 38.1), (32.3, 38.1), (32.3, 37.7)])
            },
            {
                "city": "Gaziantep",
                "region": "Güneydoğu Anadolu",
                "population": 2154051,
                "category": "Sanayi",
                "geometry": Polygon([(37.2, 36.9), (37.6, 36.9), (37.6, 37.2), (37.2, 37.2), (37.2, 36.9)])
            },
            {
                "city": "Trabzon",
                "region": "Karadeniz",
                "population": 818023,
                "category": "Liman",
                "geometry": Polygon([(39.6, 40.9), (39.9, 40.9), (39.9, 41.1), (39.6, 41.1), (39.6, 40.9)])
            }
        ]
        return gpd.GeoDataFrame(features, crs="EPSG:4326")
