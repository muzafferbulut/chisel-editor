import os
import io
import json
import warnings
import numpy as np
import pandas as pd
import geopandas as gpd
import shapely
from shapely.geometry import Polygon
from pyproj import CRS

warnings.filterwarnings("ignore", category=RuntimeWarning, message="Several features with id.*")
warnings.filterwarnings("ignore", category=RuntimeWarning, module="pyogrio.*")


class SpatialOps:
    """
    High-performance utility for GIS & spatial operations in Chisel Editor.
    Includes buffering, dissolving, geometry attribute calculations,
    simplification, validation, statistics, and multi-format exports.
    """

    @staticmethod
    def get_layer_geometry_type(gdf: gpd.GeoDataFrame) -> str:
        """
        Determines the dominant geometry type of the GeoDataFrame.
        Returns 'point', 'line', 'polygon', 'mixed', or 'any'.
        """
        if gdf is None or gdf.empty or "geometry" not in gdf.columns:
            return "any"

        valid_geoms = gdf.geometry.dropna()
        if valid_geoms.empty:
            return "any"

        types = valid_geoms.geom_type.str.lower().unique()
        has_point = any("point" in t for t in types)
        has_line = any("line" in t for t in types)
        has_poly = any("polygon" in t for t in types)

        count = sum([has_point, has_line, has_poly])
        if count > 1:
            return "mixed"
        if has_point:
            return "point"
        if has_line:
            return "line"
        if has_poly:
            return "polygon"
        return "any"

    @staticmethod
    def sanitize_gdf_for_json(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """
        Sanitizes non-serializable columns (datetime, Timestamps, NaT, NaN, categorical)
        so that gdf.to_json() succeeds without serialization errors.
        Uses shallow copy to avoid duplicating geometry coordinate buffers.
        """
        if gdf is None or gdf.empty:
            return gdf
        gdf_clean = gdf.copy(deep=False)
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
        Ensures EPSG:4326 projection as required by GeoJSON RFC 7946 standard for Leaflet.
        Guarantees no NaN, null, or out-of-range coordinates that could break Leaflet.
        """
        if gdf is None or gdf.empty:
            return '{"type": "FeatureCollection", "features": []}'

        clean_gdf = SpatialOps.sanitize_gdf_for_json(gdf)
        if clean_gdf is not None and not clean_gdf.empty and "geometry" in clean_gdf.columns:
            # Filter out null, empty, or non-finite geometries
            try:
                valid_mask = clean_gdf.geometry.notna() & (~clean_gdf.geometry.is_empty)
                clean_gdf = clean_gdf[valid_mask]
            except Exception:
                pass

            if clean_gdf.empty:
                return '{"type": "FeatureCollection", "features": []}'

            try:
                crs_is_4326 = False
                if clean_gdf.crs is not None:
                    crs_str = str(clean_gdf.crs).upper()
                    crs_is_4326 = ("4326" in crs_str or "CRS84" in crs_str)

                b = clean_gdf.total_bounds
                is_in_degrees = (
                    abs(b[0]) <= 180.0 and abs(b[2]) <= 180.0 and
                    abs(b[1]) <= 90.0 and abs(b[3]) <= 90.0
                )

                if crs_is_4326:
                    if not is_in_degrees:
                        # User data has metric coordinates but CRS was wrongly set to 4326
                        clean_gdf = clean_gdf.set_crs("EPSG:3857", allow_override=True)
                        clean_gdf = clean_gdf.to_crs("EPSG:4326")
                else:
                    if clean_gdf.crs is not None:
                        clean_gdf = clean_gdf.to_crs("EPSG:4326")
                    elif not is_in_degrees:
                        clean_gdf = clean_gdf.set_crs("EPSG:3857", allow_override=True)
                        clean_gdf = clean_gdf.to_crs("EPSG:4326")
                    else:
                        clean_gdf = clean_gdf.set_crs("EPSG:4326", allow_override=True)
            except Exception as e:
                print(f"Warning during CRS conversion in to_geojson_str: {e}")

        # Drop any null or empty geometries after reprojection
        try:
            valid_mask = clean_gdf.geometry.notna() & (~clean_gdf.geometry.is_empty)
            clean_gdf = clean_gdf[valid_mask]
        except Exception:
            pass

        raw_json = clean_gdf.to_json()

        # Sanitize against any NaN / Infinity literals in JSON
        if "NaN" in raw_json or "Infinity" in raw_json:
            import re
            raw_json = re.sub(r'\bNaN\b', 'null', raw_json)
            raw_json = re.sub(r'\bInfinity\b', 'null', raw_json)

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
            gdf = gdf.set_crs("EPSG:4326")
        return gdf

    @staticmethod
    def reproject_gdf(gdf: gpd.GeoDataFrame, target_crs: str) -> gpd.GeoDataFrame:
        """
        Reprojects GeoDataFrame to target CRS cleanly and safely.
        """
        if gdf is None or gdf.empty:
            return gdf

        source_gdf = gdf.copy()
        if source_gdf.crs is None:
            # Auto-detect source CRS based on coordinate ranges
            b = source_gdf.total_bounds
            if abs(b[0]) <= 180 and abs(b[2]) <= 180 and abs(b[1]) <= 90 and abs(b[3]) <= 90:
                source_gdf = source_gdf.set_crs("EPSG:4326")
            else:
                source_gdf = source_gdf.set_crs("EPSG:3857")

        reproj_gdf = source_gdf.to_crs(target_crs)
        # Drop any null or empty geometries that may result from out-of-bounds projections
        try:
            valid_mask = reproj_gdf.geometry.notna() & (~reproj_gdf.geometry.is_empty)
            if not valid_mask.all():
                reproj_gdf = reproj_gdf[valid_mask].reset_index(drop=True)
        except Exception:
            pass

        return reproj_gdf

    @staticmethod
    def set_crs_gdf(gdf: gpd.GeoDataFrame, crs_str: str) -> gpd.GeoDataFrame:
        """
        Sets or overrides CRS on GeoDataFrame without coordinate modification.
        """
        new_gdf = gdf.copy()
        return new_gdf.set_crs(crs_str, allow_override=True)

    @staticmethod
    def validate_geometries(gdf: gpd.GeoDataFrame) -> dict:
        """
        Validates geometries without modifying them.
        Returns a dictionary with validation statistics and error reasons:
        {
            'total_features': int,
            'valid_count': int,
            'invalid_count': int,
            'empty_count': int,
            'reasons': list[str]
        }
        """
        if gdf is None or gdf.empty:
            return {
                'total_features': 0,
                'valid_count': 0,
                'invalid_count': 0,
                'empty_count': 0,
                'reasons': []
            }

        total = len(gdf)
        is_empty = gdf.geometry.is_empty | gdf.geometry.isna()
        empty_count = int(is_empty.sum())

        valid_mask = gdf.geometry.is_valid
        invalid_mask = ~valid_mask & ~is_empty
        invalid_count = int(invalid_mask.sum())
        valid_count = total - invalid_count - empty_count

        reasons = []
        if invalid_count > 0:
            for idx in gdf[invalid_mask].index[:20]:
                geom = gdf.geometry.loc[idx]
                try:
                    reason = shapely.is_valid_reason(geom)
                except Exception as e:
                    reason = str(e)
                reasons.append(f"Feature #{idx}: {reason}")

        return {
            'total_features': total,
            'valid_count': valid_count,
            'invalid_count': invalid_count,
            'empty_count': empty_count,
            'reasons': reasons
        }

    @staticmethod
    def repair_geometries(gdf: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, int]:
        """
        Repairs invalid geometries using shapely.make_valid.
        Returns: (repaired_gdf, count_of_repaired_geometries)
        """
        if gdf is None or gdf.empty:
            return gdf, 0

        new_gdf = gdf.copy()
        invalid_mask = ~new_gdf.geometry.is_valid
        invalid_count = int(invalid_mask.sum())

        if invalid_count > 0:
            new_gdf.loc[invalid_mask, 'geometry'] = new_gdf.loc[invalid_mask, 'geometry'].apply(
                lambda geom: shapely.make_valid(geom) if geom is not None and not geom.is_empty else geom
            )
        return new_gdf, invalid_count

    @staticmethod
    def validate_and_repair(gdf: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, int]:
        """Backwards compatibility alias for repair_geometries."""
        return SpatialOps.repair_geometries(gdf)

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
        temporarily reprojects to World Mercator (EPSG:3857), applies the metric buffer,
        and reprojects back to the original CRS.
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
        try:
            metric_gdf = res_gdf.to_crs("EPSG:3857")
        except Exception:
            metric_gdf = res_gdf

        has_polygons = any(t in ('Polygon', 'MultiPolygon') for t in metric_gdf.geometry.geom_type)
        if has_polygons:
            res_gdf['area_sqkm'] = (metric_gdf.geometry.area / 1_000_000.0).round(4)
            res_gdf['area_ha'] = (metric_gdf.geometry.area / 10_000.0).round(2)
            res_gdf['perimeter_km'] = (metric_gdf.geometry.length / 1000.0).round(3)

        has_lines = any(t in ('LineString', 'MultiLineString') for t in metric_gdf.geometry.geom_type)
        if has_lines and not has_polygons:
            res_gdf['length_km'] = (metric_gdf.geometry.length / 1000.0).round(3)

        has_points = any(t in ('Point', 'MultiPoint') for t in res_gdf.geometry.geom_type)
        if has_points and not has_polygons and not has_lines:
            res_gdf['coord_x'] = res_gdf.geometry.apply(lambda g: round(g.x, 6) if hasattr(g, 'x') else None)
            res_gdf['coord_y'] = res_gdf.geometry.apply(lambda g: round(g.y, 6) if hasattr(g, 'y') else None)

        return res_gdf

    @staticmethod
    def calculate_convex_hull(gdf: gpd.GeoDataFrame, per_feature: bool = False) -> gpd.GeoDataFrame:
        """
        Calculates convex hull geometries.
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

        geom_types = {}
        for geom in gdf.geometry:
            if geom is not None and not geom.is_empty:
                gt = geom.geom_type
                geom_types[gt] = geom_types.get(gt, 0) + 1
            else:
                geom_types["Empty/None"] = geom_types.get("Empty/None", 0) + 1

        try:
            total_bounds = gdf.total_bounds.tolist() if feature_count > 0 else [0, 0, 0, 0]
        except Exception:
            total_bounds = [0, 0, 0, 0]

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
        Exports GeoDataFrame to various GIS vector formats (.geojson, .gpkg, .shp, .kml, .fgb, .csv).
        """
        ext = os.path.splitext(target_path)[1].lower()
        clean_gdf = SpatialOps.sanitize_gdf_for_json(gdf)

        if ext in ('.geojson', '.json'):
            clean_gdf.to_file(target_path, driver='GeoJSON')
        elif ext == '.gpkg':
            clean_gdf.to_file(target_path, driver='GPKG', engine='pyogrio')
        elif ext == '.shp':
            shp_gdf = clean_gdf.copy()
            # ESRI Shapefiles strictly require homogenous geometry types per layer
            valid_geom_types = shp_gdf.geometry.dropna().geom_type
            if not valid_geom_types.empty:
                base_types = set(t.replace('Multi', '') for t in valid_geom_types.unique())
                if len(base_types) > 1:
                    dominant_type = valid_geom_types.value_counts().index[0]
                    base_dominant = dominant_type.replace('Multi', '')
                    shp_gdf = shp_gdf[shp_gdf.geometry.geom_type.str.contains(base_dominant)].copy()
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
            if new_cols:
                shp_gdf = shp_gdf.rename(columns=new_cols)
            shp_gdf.to_file(target_path, driver='ESRI Shapefile', engine='pyogrio')
        elif ext == '.kml':
            kml_gdf = clean_gdf.copy()
            if kml_gdf.crs and str(kml_gdf.crs) != "EPSG:4326":
                kml_gdf = kml_gdf.to_crs("EPSG:4326")
            elif not kml_gdf.crs:
                kml_gdf = kml_gdf.set_crs("EPSG:4326")
            kml_gdf.to_file(target_path, driver='KML')
        elif ext == '.kmz':
            import zipfile
            import tempfile
            kml_gdf = clean_gdf.copy()
            if kml_gdf.crs and str(kml_gdf.crs) != "EPSG:4326":
                kml_gdf = kml_gdf.to_crs("EPSG:4326")
            elif not kml_gdf.crs:
                kml_gdf = kml_gdf.set_crs("EPSG:4326")
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_kml = os.path.join(tmp_dir, "doc.kml")
                kml_gdf.to_file(tmp_kml, driver="KML")
                with zipfile.ZipFile(target_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    zf.write(tmp_kml, arcname="doc.kml")
        elif ext == '.dxf':
            dxf_gdf = gpd.GeoDataFrame(geometry=clean_gdf.geometry, crs=clean_gdf.crs)
            layer_col = None
            for candidate in ('Layer', 'layer', 'name', 'title', 'category', 'type', 'id'):
                if candidate in clean_gdf.columns:
                    layer_col = candidate
                    break
            if layer_col:
                dxf_gdf['Layer'] = clean_gdf[layer_col].astype(str).str[:50]
            else:
                dxf_gdf['Layer'] = "0"
            if 'Text' in clean_gdf.columns:
                dxf_gdf['Text'] = clean_gdf['Text'].astype(str)
            dxf_gdf.to_file(target_path, driver='DXF', engine='fiona')
        elif ext == '.fgb':
            clean_gdf.to_file(target_path, driver='FlatGeobuf', engine='pyogrio')
        elif ext == '.csv':
            csv_df = pd.DataFrame(clean_gdf)
            csv_df['wkt_geometry'] = clean_gdf.geometry.apply(lambda g: g.wkt if g is not None else "")
            geom_col = clean_gdf.geometry.name
            if geom_col in csv_df.columns and geom_col != 'wkt_geometry':
                csv_df = csv_df.drop(columns=[geom_col])
            csv_df.to_csv(target_path, index=False, encoding='utf-8-sig')
        else:
            clean_gdf.to_file(target_path, engine='pyogrio')
        return True

    @staticmethod
    def create_sample_spatial_data() -> gpd.GeoDataFrame:
        """
        Generates sample Turkish GIS vector data for 1-click instant testing.
        """
        features = [
            {
                "city": "Istanbul",
                "region": "Marmara",
                "population": 15907951,
                "category": "Metropolis",
                "geometry": Polygon([(28.7, 40.9), (29.2, 40.9), (29.2, 41.2), (28.7, 41.2), (28.7, 40.9)])
            },
            {
                "city": "Ankara",
                "region": "Central Anatolia",
                "population": 5803482,
                "category": "Capital",
                "geometry": Polygon([(32.6, 39.8), (33.0, 39.8), (33.0, 40.1), (32.6, 40.1), (32.6, 39.8)])
            },
            {
                "city": "Izmir",
                "region": "Aegean",
                "population": 4462056,
                "category": "Metropolis",
                "geometry": Polygon([(26.9, 38.3), (27.3, 38.3), (27.3, 38.6), (26.9, 38.6), (26.9, 38.3)])
            },
            {
                "city": "Bursa",
                "region": "Marmara",
                "population": 3194720,
                "category": "Industrial",
                "geometry": Polygon([(28.9, 40.1), (29.3, 40.1), (29.3, 40.35), (28.9, 40.35), (28.9, 40.1)])
            },
            {
                "city": "Antalya",
                "region": "Mediterranean",
                "population": 2688004,
                "category": "Tourism",
                "geometry": Polygon([(30.5, 36.8), (30.9, 36.8), (30.9, 37.1), (30.5, 37.1), (30.5, 36.8)])
            },
            {
                "city": "Konya",
                "region": "Central Anatolia",
                "population": 2296347,
                "category": "Agriculture",
                "geometry": Polygon([(32.3, 37.7), (32.7, 37.7), (32.7, 38.1), (32.3, 38.1), (32.3, 37.7)])
            },
            {
                "city": "Gaziantep",
                "region": "Southeastern Anatolia",
                "population": 2154051,
                "category": "Industrial",
                "geometry": Polygon([(37.2, 36.9), (37.6, 36.9), (37.6, 37.2), (37.2, 37.2), (37.2, 36.9)])
            },
            {
                "city": "Trabzon",
                "region": "Black Sea",
                "population": 818023,
                "category": "Port",
                "geometry": Polygon([(39.6, 40.9), (39.9, 40.9), (39.9, 41.1), (39.6, 41.1), (39.6, 40.9)])
            }
        ]
        return gpd.GeoDataFrame(features, crs="EPSG:4326")

    @staticmethod
    def get_viewport_lod_tolerance(zoom: int) -> float:
        """
        Calculates Douglas-Peucker tolerance in degrees based on map zoom level.
        Approximates ~1.5 to 2 screen pixels.
        """
        deg_per_pixel = 360.0 / (256.0 * (2 ** max(1, zoom)))
        return deg_per_pixel * 1.5

    @staticmethod
    def get_overview_lod(gdf: gpd.GeoDataFrame, max_features: int = 1500, max_vertices: int = 25000) -> gpd.GeoDataFrame:
        """
        Builds a fast, representative overview of a large dataset for initial render.
        Samples features and simplifies vertices for lightweight initial loading.
        """
        if gdf is None or gdf.empty:
            return gdf

        feat_count = len(gdf)
        v_count = SpatialOps.count_vertices(gdf)
        if feat_count <= max_features and v_count <= max_vertices:
            return gdf

        # 1. Feature sampling if feature count exceeds max_features
        if feat_count > max_features:
            import math
            step = math.ceil(feat_count / max_features)
            sampled = gdf.iloc[::step].copy()
        else:
            sampled = gdf.copy()

        # 2. Vertex simplification if vertices exceed max_vertices
        sampled_v_count = SpatialOps.count_vertices(sampled)
        if sampled_v_count > max_vertices:
            geom_type = SpatialOps.get_layer_geometry_type(sampled)
            if geom_type in ("line", "polygon", "mixed"):
                try:
                    b = sampled.total_bounds
                    span = max(abs(b[2] - b[0]), abs(b[3] - b[1]))
                    if span > 0:
                        tol = max(1e-5, span / 800.0)
                        simplified_geom = sampled.geometry.simplify(tol, preserve_topology=False)
                        valid_mask = simplified_geom.notna() & (~simplified_geom.is_empty)
                        geom_col = sampled.geometry.name
                        sampled.loc[valid_mask, geom_col] = simplified_geom[valid_mask]
                except Exception:
                    pass

        return sampled

    @staticmethod
    def query_viewport_and_lod(
        gdf: gpd.GeoDataFrame,
        minx: float,
        miny: float,
        maxx: float,
        maxy: float,
        zoom: int,
        max_features: int = 3500
    ) -> gpd.GeoDataFrame:
        """
        QGIS-style on-the-fly viewport culling and level-of-detail simplification.
        Uses GEOS STRtree spatial index for sub-millisecond BBOX filtering.
        """
        if gdf is None or gdf.empty:
            return gdf

        if len(gdf) <= max_features:
            return gdf

        dx = (maxx - minx) * 0.2
        dy = (maxy - miny) * 0.2
        from shapely.geometry import box
        search_box = box(minx - dx, miny - dy, maxx + dx, maxy + dy)

        try:
            if gdf.crs is not None and str(gdf.crs).upper() not in ("EPSG:4326", "OGC:CRS84", "4326"):
                import pyproj
                from shapely.ops import transform
                transformer = pyproj.Transformer.from_crs("EPSG:4326", gdf.crs, always_xy=True)
                query_geom = transform(transformer.transform, search_box)
            else:
                query_geom = search_box

            indices = gdf.sindex.query(query_geom, predicate="intersects")
            if len(indices) == 0:
                return gdf.iloc[0:0]
            sub_gdf = gdf.iloc[indices].copy()
        except Exception:
            sub_gdf = gdf.copy()

        geom_type = SpatialOps.get_layer_geometry_type(sub_gdf)
        if geom_type in ("line", "polygon", "mixed") and zoom < 16:
            tol = SpatialOps.get_viewport_lod_tolerance(zoom)
            if gdf.crs is not None and str(gdf.crs).upper() not in ("EPSG:4326", "OGC:CRS84", "4326"):
                tol = tol * 111319.0
            try:
                sub_gdf.geometry = sub_gdf.geometry.simplify(tol, preserve_topology=False)
            except Exception:
                pass

        if len(sub_gdf) > max_features:
            step = max(1, len(sub_gdf) // max_features)
            sub_gdf = sub_gdf.iloc[::step]

        return sub_gdf
