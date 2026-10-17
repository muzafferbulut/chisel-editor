import math
import warnings
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Any

import numpy as np
import pandas as pd
import geopandas as gpd
import shapely
from shapely.geometry import Point, MultiPoint, LineString, MultiLineString, Polygon, MultiPolygon
from shapely.ops import unary_union

warnings.filterwarnings("ignore", category=RuntimeWarning, message="Several features with id.*")
warnings.filterwarnings("ignore", category=RuntimeWarning, module="pyogrio.*")


class TopologyRuleCode:
    POINT_DUPLICATES = "point_duplicates"
    GEOM_EMPTY_NULL = "geom_empty_null"
    LINE_SELF_INTERSECT = "line_self_intersect"
    LINE_DUPLICATE_NODES = "line_duplicate_nodes"
    LINE_SPIKES = "line_spikes"
    LINE_DANGLES = "line_dangles"
    LINE_PSEUDO_NODES = "line_pseudo_nodes"
    LINE_SHORT_SEGMENTS = "line_short_segments"
    LINE_OVERLAPS = "line_overlaps"
    POLYGON_OGC_VALID = "polygon_ogc_valid"
    POLYGON_DUPLICATE_VERTICES = "polygon_duplicate_vertices"
    POLYGON_OVERLAPS = "polygon_overlaps"
    POLYGON_SLIVERS = "polygon_slivers"
    POLYGON_GAPS = "polygon_gaps"


@dataclass
class TopologyRuleInfo:
    code: str
    name: str
    description: str
    geom_types: List[str]
    default_enabled: bool = True
    supports_auto_fix: bool = True


@dataclass
class ConfiguredRule:
    code: str
    name: str
    params: Dict[str, Any] = field(default_factory=dict)
    description: str = ""

    def get_param_summary(self, is_degree: bool = False) -> str:
        parts = []
        if "tolerance" in self.params:
            tol = float(self.params["tolerance"])
            parts.append(f"Tolerance: {tol:.3f} m")
        if "max_angle" in self.params:
            parts.append(f"Max Spike Angle: {float(self.params['max_angle']):.1f}°")
        if "min_length" in self.params:
            ml = float(self.params["min_length"])
            parts.append(f"Min Length: {ml:.2f} m")
        if "min_area" in self.params:
            ma = float(self.params["min_area"])
            parts.append(f"Min Area: {ma:.2f} m²")
        if "thinness" in self.params:
            parts.append(f"Thinness: {float(self.params['thinness']):.3f}")
        if "max_gap_area" in self.params:
            mga = float(self.params["max_gap_area"])
            parts.append(f"Max Gap: {mga:.2f} m²")
        return ", ".join(parts) if parts else "OGC Standard (No threshold)"


@dataclass
class TopologyError:
    id: int
    rule_code: str
    rule_name: str
    feature_ids: List[int]
    geometry: Any
    description: str
    severity: str = "error"  # "error" or "warning"
    can_fix: bool = True

    def __post_init__(self):
        self.id = int(self.id)
        if self.feature_ids:
            self.feature_ids = [int(x) for x in self.feature_ids]


@dataclass
class TopologyReport:
    total_errors: int = 0
    errors: List[TopologyError] = field(default_factory=list)
    rule_counts: Dict[str, int] = field(default_factory=dict)
    errors_gdf: Optional[gpd.GeoDataFrame] = None
    layer_geom_type: str = "any"
    configured_rules: List[ConfiguredRule] = field(default_factory=list)


class TopologyEngine:
    """
    QGIS Topology Checker-style Topology Engine for Chisel Editor.
    Provides comprehensive spatial integrity audits, error geometry generation,
    and automatic remediation for Point, Line, and Polygon layers.
    """

    RULES: Dict[str, TopologyRuleInfo] = {
        # Universal / Common
        TopologyRuleCode.GEOM_EMPTY_NULL: TopologyRuleInfo(
            code=TopologyRuleCode.GEOM_EMPTY_NULL,
            name="Must Not Be Empty / Null",
            description="Checks for features with null or empty geometries.",
            geom_types=["point", "line", "polygon", "mixed", "any"],
            default_enabled=True,
            supports_auto_fix=True
        ),

        # Point Rules
        TopologyRuleCode.POINT_DUPLICATES: TopologyRuleInfo(
            code=TopologyRuleCode.POINT_DUPLICATES,
            name="Must Not Have Duplicates",
            description="Flags coincident point features within snap tolerance.",
            geom_types=["point", "mixed"],
            default_enabled=True,
            supports_auto_fix=True
        ),

        # Line Rules
        TopologyRuleCode.LINE_SELF_INTERSECT: TopologyRuleInfo(
            code=TopologyRuleCode.LINE_SELF_INTERSECT,
            name="Must Not Self-Intersect",
            description="Detects lines that self-cross or form closed self-loops (knots).",
            geom_types=["line", "mixed"],
            default_enabled=True,
            supports_auto_fix=True
        ),
        TopologyRuleCode.LINE_DUPLICATE_NODES: TopologyRuleInfo(
            code=TopologyRuleCode.LINE_DUPLICATE_NODES,
            name="Must Not Have Duplicate Nodes",
            description="Identifies consecutive identical vertices along a line.",
            geom_types=["line", "mixed"],
            default_enabled=True,
            supports_auto_fix=True
        ),
        TopologyRuleCode.LINE_SPIKES: TopologyRuleInfo(
            code=TopologyRuleCode.LINE_SPIKES,
            name="Must Not Have Spikes",
            description="Detects sharp needles and retraced segments where a line doubles back on itself.",
            geom_types=["line", "mixed"],
            default_enabled=True,
            supports_auto_fix=True
        ),
        TopologyRuleCode.LINE_DANGLES: TopologyRuleInfo(
            code=TopologyRuleCode.LINE_DANGLES,
            name="Must Not Have Dangles",
            description="Flags open line endpoints not connected to other features; auto-snaps undershoots within tolerance.",
            geom_types=["line", "mixed"],
            default_enabled=False,  # Can be many in non-closed road/river networks
            supports_auto_fix=True
        ),
        TopologyRuleCode.LINE_PSEUDO_NODES: TopologyRuleInfo(
            code=TopologyRuleCode.LINE_PSEUDO_NODES,
            name="Must Not Have Pseudo-Nodes",
            description="Finds redundant endpoints connecting exactly two lines that could be merged.",
            geom_types=["line", "mixed"],
            default_enabled=True,
            supports_auto_fix=True
        ),
        TopologyRuleCode.LINE_SHORT_SEGMENTS: TopologyRuleInfo(
            code=TopologyRuleCode.LINE_SHORT_SEGMENTS,
            name="Must Not Have Short Segments",
            description="Detects lines or segments shorter than minimum length tolerance.",
            geom_types=["line", "mixed"],
            default_enabled=True,
            supports_auto_fix=True
        ),
        TopologyRuleCode.LINE_OVERLAPS: TopologyRuleInfo(
            code=TopologyRuleCode.LINE_OVERLAPS,
            name="Must Not Overlap",
            description="Detects lines sharing 1D segments with other lines.",
            geom_types=["line", "mixed"],
            default_enabled=True,
            supports_auto_fix=True
        ),

        # Polygon Rules
        TopologyRuleCode.POLYGON_OGC_VALID: TopologyRuleInfo(
            code=TopologyRuleCode.POLYGON_OGC_VALID,
            name="Must Be OGC Valid",
            description="Validates polygon boundaries (detects bowties, self-intersections, inverted holes).",
            geom_types=["polygon", "mixed"],
            default_enabled=True,
            supports_auto_fix=True
        ),
        TopologyRuleCode.POLYGON_DUPLICATE_VERTICES: TopologyRuleInfo(
            code=TopologyRuleCode.POLYGON_DUPLICATE_VERTICES,
            name="Must Not Have Duplicate Vertices",
            description="Detects consecutive duplicate vertices in polygon exterior or interior rings.",
            geom_types=["polygon", "mixed"],
            default_enabled=True,
            supports_auto_fix=True
        ),
        TopologyRuleCode.POLYGON_OVERLAPS: TopologyRuleInfo(
            code=TopologyRuleCode.POLYGON_OVERLAPS,
            name="Must Not Overlap",
            description="Identifies adjacent or overlapping polygons sharing 2D interior area.",
            geom_types=["polygon", "mixed"],
            default_enabled=True,
            supports_auto_fix=True
        ),
        TopologyRuleCode.POLYGON_SLIVERS: TopologyRuleInfo(
            code=TopologyRuleCode.POLYGON_SLIVERS,
            name="Must Not Have Slivers",
            description="Flags slivers, micro-polygons, or needle-like shapes below area/thinness thresholds.",
            geom_types=["polygon", "mixed"],
            default_enabled=True,
            supports_auto_fix=True
        ),
        TopologyRuleCode.POLYGON_GAPS: TopologyRuleInfo(
            code=TopologyRuleCode.POLYGON_GAPS,
            name="Must Not Have Gaps",
            description="Detects enclosed interior gaps/voids between contiguous polygons.",
            geom_types=["polygon", "mixed"],
            default_enabled=False,
            supports_auto_fix=False
        ),
    }

    @classmethod
    def get_applicable_rules(cls, geom_type: str) -> List[TopologyRuleInfo]:
        """
        Returns rule specifications matching the layer's geometry type.
        """
        raw = (geom_type or "any").lower()
        if "line" in raw:
            norm_type = "line"
        elif "poly" in raw:
            norm_type = "polygon"
        elif "point" in raw:
            norm_type = "point"
        elif "mixed" in raw:
            norm_type = "mixed"
        else:
            norm_type = "any"

        res = []
        for rule in cls.RULES.values():
            if "any" in rule.geom_types or norm_type in rule.geom_types or norm_type == "mixed":
                res.append(rule)
        return res

    @classmethod
    def get_metric_conversion_factors(cls, gdf: Optional[gpd.GeoDataFrame]) -> Tuple[float, float]:
        """
        Calculates metric conversion factors for the given layer:
          - meters_per_coord_unit: linear scale factor (meters per native coordinate unit)
          - sqmeters_per_coord_unit: area scale factor (square meters per native coordinate unit^2)

        For geographic CRS (e.g. EPSG:4326), computes geodesic meters per degree
        at the layer bounds / centroid.
        For metric projected CRS (e.g. EPSG:3857, UTM), returns (1.0, 1.0).
        """
        if gdf is None or gdf.empty:
            return 1.0, 1.0

        crs = gdf.crs
        is_geo = False
        if crs is not None:
            if hasattr(crs, "is_geographic") and crs.is_geographic:
                is_geo = True
            elif any(k in str(crs).upper() for k in ["4326", "WGS 84", "WGS84", "CRS84", "GEOGRAPHIC"]):
                is_geo = True
        else:
            try:
                b = gdf.total_bounds
                if abs(b[0]) <= 180.0 and abs(b[2]) <= 180.0 and abs(b[1]) <= 90.0 and abs(b[3]) <= 90.0:
                    is_geo = True
            except Exception:
                pass

        if is_geo:
            try:
                b = gdf.total_bounds
                lat_mid = (b[1] + b[3]) / 2.0
            except Exception:
                lat_mid = 0.0

            lat_mid = max(-89.0, min(89.0, lat_mid))
            phi = math.radians(lat_mid)
            # WGS-84 geodesic arc length approximations
            lat_m = 111132.95 - 559.82 * math.cos(2 * phi) + 1.175 * math.cos(4 * phi)
            lon_m = 111412.84 * math.cos(phi) - 93.5 * math.cos(3 * phi)
            lon_m = max(lon_m, 1.0)
            lat_m = max(lat_m, 1.0)

            meters_per_coord_unit = (lat_m + lon_m) / 2.0
            sqmeters_per_coord_unit = lat_m * lon_m
            return meters_per_coord_unit, sqmeters_per_coord_unit

        # Projected CRS unit factor check
        if crs is not None and hasattr(crs, "axis_info") and crs.axis_info:
            try:
                factor = float(crs.axis_info[0].unit_conversion_factor)
                if factor > 0:
                    return factor, factor * factor
            except Exception:
                pass

        return 1.0, 1.0

    @classmethod
    def get_default_configured_rules(cls, geom_type: str, is_degree: bool = False) -> List[ConfiguredRule]:
        """
        Returns recommended rules with default thresholds in metric units (meters and square meters).
        """
        applicable = cls.get_applicable_rules(geom_type)
        res = []
        for r in applicable:
            if not r.default_enabled:
                continue
            params = {}
            if r.code == TopologyRuleCode.POINT_DUPLICATES:
                params["tolerance"] = 0.05
            elif r.code == TopologyRuleCode.LINE_DUPLICATE_NODES:
                params["tolerance"] = 0.0
            elif r.code == TopologyRuleCode.LINE_SPIKES:
                params["max_angle"] = 15.0
            elif r.code == TopologyRuleCode.LINE_DANGLES:
                params["tolerance"] = 0.10
            elif r.code == TopologyRuleCode.LINE_SHORT_SEGMENTS:
                params["min_length"] = 0.50
            elif r.code == TopologyRuleCode.POLYGON_OVERLAPS:
                params["min_area"] = 0.10
            elif r.code == TopologyRuleCode.POLYGON_SLIVERS:
                params["min_area"] = 1.0
                params["thinness"] = 0.03
            elif r.code == TopologyRuleCode.POLYGON_GAPS:
                params["max_gap_area"] = 50.0

            res.append(ConfiguredRule(code=r.code, name=r.name, params=params, description=r.description))
        return res

    @classmethod
    def run_configured_rules(
        cls,
        gdf: gpd.GeoDataFrame,
        configured_rules: List[ConfiguredRule]
    ) -> TopologyReport:
        """
        Executes a user-configured list of topology rules.
        Parameters are entered in human metric units (meters and square meters)
        and converted into the layer's native coordinate system space.
        """
        if gdf is None or gdf.empty or not configured_rules:
            return TopologyReport()

        from core.spatial_ops import SpatialOps
        geom_type = SpatialOps.get_layer_geometry_type(gdf)

        orig_crs = gdf.crs or "EPSG:4326"
        meters_per_unit, sqmeters_per_unit = cls.get_metric_conversion_factors(gdf)

        errors: List[TopologyError] = []
        rule_counts: Dict[str, int] = {}
        next_id = 0

        for crule in configured_rules:
            code = crule.code
            params = crule.params or {}

            if code == TopologyRuleCode.GEOM_EMPTY_NULL:
                found = cls._check_empty_null(gdf, next_id)
                errors.extend(found)
                next_id += len(found)

            elif code == TopologyRuleCode.POINT_DUPLICATES:
                tol_m = float(params.get("tolerance", 0.05))
                tol_native = tol_m / meters_per_unit
                found = cls._check_point_duplicates(gdf, tol_native, next_id, meters_per_unit=meters_per_unit)
                errors.extend(found)
                next_id += len(found)

            elif code == TopologyRuleCode.LINE_SELF_INTERSECT:
                found = cls._check_line_self_intersect(gdf, next_id)
                errors.extend(found)
                next_id += len(found)

            elif code == TopologyRuleCode.LINE_DUPLICATE_NODES:
                tol_m = float(params.get("tolerance", 0.0))
                tol_native = (tol_m / meters_per_unit) if tol_m > 0 else 0.0
                found = cls._check_line_duplicate_nodes(gdf, tol_native, next_id, meters_per_unit=meters_per_unit)
                errors.extend(found)
                next_id += len(found)

            elif code == TopologyRuleCode.LINE_SPIKES:
                max_angle = float(params.get("max_angle", 15.0))
                found = cls._check_line_spikes(gdf, max_angle, next_id)
                errors.extend(found)
                next_id += len(found)

            elif code == TopologyRuleCode.LINE_DANGLES:
                tol_m = float(params.get("tolerance", 0.10))
                tol_native = tol_m / meters_per_unit
                found = cls._check_line_dangles(gdf, tol_native, next_id, meters_per_unit=meters_per_unit)
                errors.extend(found)
                next_id += len(found)

            elif code == TopologyRuleCode.LINE_PSEUDO_NODES:
                found = cls._check_line_pseudo_nodes(gdf, next_id)
                errors.extend(found)
                next_id += len(found)

            elif code == TopologyRuleCode.LINE_SHORT_SEGMENTS:
                min_len_m = float(params.get("min_length", 0.50))
                min_len_native = min_len_m / meters_per_unit
                found = cls._check_line_short_segments(gdf, min_len_native, next_id, meters_per_unit=meters_per_unit)
                errors.extend(found)
                next_id += len(found)

            elif code == TopologyRuleCode.LINE_OVERLAPS:
                found = cls._check_line_overlaps(gdf, next_id)
                errors.extend(found)
                next_id += len(found)

            elif code == TopologyRuleCode.POLYGON_OGC_VALID:
                found = cls._check_polygon_ogc_valid(gdf, next_id)
                errors.extend(found)
                next_id += len(found)

            elif code == TopologyRuleCode.POLYGON_DUPLICATE_VERTICES:
                found = cls._check_polygon_duplicate_vertices(gdf, next_id)
                errors.extend(found)
                next_id += len(found)

            elif code == TopologyRuleCode.POLYGON_OVERLAPS:
                min_area_m = float(params.get("min_area", 0.10))
                min_area_native = min_area_m / sqmeters_per_unit
                found = cls._check_polygon_overlaps(gdf, min_area_native, next_id, sqmeters_per_unit=sqmeters_per_unit)
                errors.extend(found)
                next_id += len(found)

            elif code == TopologyRuleCode.POLYGON_SLIVERS:
                min_area_m = float(params.get("min_area", 1.0))
                min_area_native = min_area_m / sqmeters_per_unit
                thinness = float(params.get("thinness", 0.03))
                found = cls._check_polygon_slivers(gdf, min_area_native, thinness, next_id, sqmeters_per_unit=sqmeters_per_unit)
                errors.extend(found)
                next_id += len(found)

            elif code == TopologyRuleCode.POLYGON_GAPS:
                max_gap_m = float(params.get("max_gap_area", 50.0))
                max_gap_native = max_gap_m / sqmeters_per_unit
                found = cls._check_polygon_gaps(gdf, max_gap_native, next_id, sqmeters_per_unit=sqmeters_per_unit)
                errors.extend(found)
                next_id += len(found)

        for err in errors:
            rule_counts[err.rule_code] = rule_counts.get(err.rule_code, 0) + 1

        # Build errors GeoDataFrame in native CRS
        errors_gdf = None
        if errors:
            records = []
            for err in errors:
                geom = err.geometry
                if geom is None or (hasattr(geom, "is_empty") and geom.is_empty):
                    if err.feature_ids and err.feature_ids[0] in gdf.index:
                        feat_geom = gdf.geometry.loc[err.feature_ids[0]]
                        geom = feat_geom.centroid if feat_geom is not None and not feat_geom.is_empty else Point(0, 0)
                    else:
                        geom = Point(0, 0)

                records.append({
                    "error_id": err.id,
                    "rule_code": err.rule_code,
                    "rule_name": err.rule_name,
                    "feature_id": err.feature_ids[0] if err.feature_ids else -1,
                    "feature_ids": ",".join(map(str, err.feature_ids)),
                    "description": err.description,
                    "severity": err.severity,
                    "can_fix": err.can_fix,
                    "geometry": geom
                })

            errors_gdf = gpd.GeoDataFrame(records, crs=orig_crs)

        return TopologyReport(
            total_errors=len(errors),
            errors=errors,
            rule_counts=rule_counts,
            errors_gdf=errors_gdf,
            layer_geom_type=geom_type,
            configured_rules=configured_rules
        )

    @classmethod
    def run_checks(
        cls,
        gdf: gpd.GeoDataFrame,
        enabled_rules: Optional[List[str]] = None,
        snap_tolerance: float = 0.05,
        min_length: float = 0.50,
        min_area: float = 1.0,
        sliver_thinness: float = 0.03
    ) -> TopologyReport:
        """
        Convenience wrapper executing selected rules with default metric thresholds.
        """
        if gdf is None or gdf.empty:
            return TopologyReport()

        from core.spatial_ops import SpatialOps
        geom_type = SpatialOps.get_layer_geometry_type(gdf)
        applicable = cls.get_applicable_rules(geom_type)

        if enabled_rules is None:
            rules_to_run = [r for r in applicable if r.default_enabled]
        else:
            rules_to_run = [r for r in applicable if r.code in enabled_rules]

        configured_rules = []
        for r in rules_to_run:
            params = {}
            if r.code in (TopologyRuleCode.POINT_DUPLICATES, TopologyRuleCode.LINE_DANGLES):
                params["tolerance"] = snap_tolerance
            elif r.code == TopologyRuleCode.LINE_SHORT_SEGMENTS:
                params["min_length"] = min_length
            elif r.code == TopologyRuleCode.POLYGON_OVERLAPS:
                params["min_area"] = min_area
            elif r.code == TopologyRuleCode.POLYGON_SLIVERS:
                params["min_area"] = min_area
                params["thinness"] = sliver_thinness
            elif r.code == TopologyRuleCode.POLYGON_GAPS:
                params["max_gap_area"] = 50.0

            configured_rules.append(ConfiguredRule(code=r.code, name=r.name, params=params, description=r.description))

        return cls.run_configured_rules(gdf, configured_rules)

    # -------------------------------------------------------------
    # Rule Check Implementations
    # -------------------------------------------------------------

    @classmethod
    def _check_empty_null(cls, gdf: gpd.GeoDataFrame, start_id: int) -> List[TopologyError]:
        errors = []
        rule = cls.RULES[TopologyRuleCode.GEOM_EMPTY_NULL]
        curr_id = start_id

        for idx, geom in gdf.geometry.items():
            if geom is None or geom.is_empty:
                errors.append(TopologyError(
                    id=curr_id,
                    rule_code=rule.code,
                    rule_name=rule.name,
                    feature_ids=[idx],
                    geometry=Point(0, 0),
                    description=f"Feature #{idx} has empty or null geometry.",
                    severity="error",
                    can_fix=True
                ))
                curr_id += 1
        return errors

    @classmethod
    def _check_point_duplicates(cls, gdf: gpd.GeoDataFrame, tolerance: float, start_id: int, meters_per_unit: float = 1.0) -> List[TopologyError]:
        errors = []
        rule = cls.RULES[TopologyRuleCode.POINT_DUPLICATES]
        curr_id = start_id

        valid_mask = gdf.geometry.notna() & ~gdf.geometry.is_empty
        sub_gdf = gdf[valid_mask]
        geoms = sub_gdf.geometry.values
        indices = sub_gdf.index.values

        if len(geoms) < 2:
            return errors

        tree = shapely.STRtree(geoms)
        dist = max(tolerance, 1e-12)
        matches = tree.query(geoms, predicate="dwithin", distance=dist)
        tol_m = dist * meters_per_unit

        seen_pairs = set()
        for i, j in zip(matches[0], matches[1]):
            if i < j:
                idx_i = indices[i]
                idx_j = indices[j]
                pair_key = (min(idx_i, idx_j), max(idx_i, idx_j))
                if pair_key not in seen_pairs:
                    seen_pairs.add(pair_key)
                    errors.append(TopologyError(
                        id=curr_id,
                        rule_code=rule.code,
                        rule_name=rule.name,
                        feature_ids=[idx_i, idx_j],
                        geometry=geoms[i],
                        description=f"Features #{idx_i} and #{idx_j} are coincident / duplicates within {tol_m:.3g} m.",
                        severity="error",
                        can_fix=True
                    ))
                    curr_id += 1
        return errors

    @classmethod
    def _check_line_self_intersect(cls, gdf: gpd.GeoDataFrame, start_id: int) -> List[TopologyError]:
        errors = []
        rule = cls.RULES[TopologyRuleCode.LINE_SELF_INTERSECT]
        curr_id = start_id

        for idx, geom in gdf.geometry.items():
            if geom is None or geom.is_empty or geom.geom_type not in ("LineString", "MultiLineString"):
                continue

            if not geom.is_simple:
                # Extract self-intersection point(s)
                try:
                    noded = shapely.node(geom)
                    coords = []
                    subgeoms = noded.geoms if hasattr(noded, "geoms") else [noded]
                    for g in subgeoms:
                        coords.extend([g.coords[0], g.coords[-1]])

                    from collections import Counter
                    counts = Counter(coords)
                    orig_endpoints = [geom.coords[0], geom.coords[-1]] if geom.geom_type == "LineString" else []
                    cross_pts = [
                        Point(c) for c, cnt in counts.items()
                        if cnt > 2 or (cnt == 2 and c not in orig_endpoints)
                    ]
                    err_geom = MultiPoint(cross_pts) if len(cross_pts) > 1 else (cross_pts[0] if cross_pts else geom.centroid)
                except Exception:
                    err_geom = geom.centroid

                errors.append(TopologyError(
                    id=curr_id,
                    rule_code=rule.code,
                    rule_name=rule.name,
                    feature_ids=[idx],
                    geometry=err_geom,
                    description=f"Line feature #{idx} self-intersects / contains self-loops.",
                    severity="error",
                    can_fix=True
                ))
                curr_id += 1
        return errors

    @staticmethod
    def _clean_line_duplicates(geom, tol: float = 0.0):
        if geom is None or geom.is_empty:
            return geom

        def clean_coords(coords):
            if len(coords) < 2:
                return coords
            res = [coords[0]]
            for pt in coords[1:]:
                if tol <= 0:
                    if pt != res[-1]:
                        res.append(pt)
                else:
                    dx = pt[0] - res[-1][0]
                    dy = pt[1] - res[-1][1]
                    if (dx * dx + dy * dy) > tol * tol:
                        res.append(pt)
            return res

        if geom.geom_type == 'LineString':
            cleaned = clean_coords(list(geom.coords))
            return LineString(cleaned) if len(cleaned) >= 2 else None
        elif geom.geom_type == 'MultiLineString':
            lines = [clean_coords(list(l.coords)) for l in geom.geoms]
            valid_lines = [LineString(c) for c in lines if len(c) >= 2]
            return MultiLineString(valid_lines) if valid_lines else None
        return geom

    @staticmethod
    def _clean_line_spikes(geom, max_angle_deg: float = 15.0):
        if geom is None or geom.is_empty:
            return geom

        def remove_spikes_from_coords(coords):
            if len(coords) < 3:
                return coords
            cos_thresh = math.cos(math.radians(max_angle_deg))
            pts = list(coords)
            changed = True

            while changed and len(pts) >= 3:
                changed = False
                new_pts = [pts[0]]
                i = 1
                while i < len(pts) - 1:
                    p0 = pts[i - 1]
                    p1 = pts[i]
                    p2 = pts[i + 1]

                    # 1. Exact retracing [p0 -> p1 -> p0]
                    if p0 == p2:
                        changed = True
                        i += 2
                        continue

                    # 2. Acute angle spike
                    v1x, v1y = p0[0] - p1[0], p0[1] - p1[1]
                    v2x, v2y = p2[0] - p1[0], p2[1] - p1[1]
                    len1 = math.hypot(v1x, v1y)
                    len2 = math.hypot(v2x, v2y)

                    if len1 > 0 and len2 > 0:
                        dot = (v1x * v2x + v1y * v2y) / (len1 * len2)
                        if dot >= cos_thresh:
                            changed = True
                            i += 1
                            continue

                    new_pts.append(p1)
                    i += 1

                if i < len(pts):
                    new_pts.append(pts[i])
                pts = new_pts

            return pts

        if geom.geom_type == 'LineString':
            cleaned = remove_spikes_from_coords(list(geom.coords))
            return LineString(cleaned) if len(cleaned) >= 2 else None
        elif geom.geom_type == 'MultiLineString':
            lines = [remove_spikes_from_coords(list(l.coords)) for l in geom.geoms]
            valid_lines = [LineString(c) for c in lines if len(c) >= 2]
            return MultiLineString(valid_lines) if valid_lines else None
        return geom

    @staticmethod
    def _clean_line_self_intersect(geom):
        if geom is None or geom.is_empty:
            return geom
        if geom.geom_type not in ("LineString", "MultiLineString"):
            return geom
        if geom.is_simple:
            return geom
        try:
            noded = shapely.node(geom)
            if noded is not None and not noded.is_empty:
                if noded.is_simple:
                    return noded
                subgeoms = noded.geoms if hasattr(noded, "geoms") else [noded]
                cleaned_lines = []
                for g in subgeoms:
                    coords = list(g.coords)
                    if len(coords) > 2 and coords[0] == coords[-1]:
                        mid = len(coords) // 2
                        cleaned_lines.append(LineString(coords[:mid + 1]))
                        cleaned_lines.append(LineString(coords[mid:]))
                    else:
                        cleaned_lines.append(g)
                res = MultiLineString(cleaned_lines)
                if res.is_simple:
                    return res
                return noded
        except Exception:
            pass
        return geom

    @staticmethod
    def _resolve_line_overlap(geom_a, geom_b, min_overlap: float = 1e-8):
        """
        Resolves overlap between two lines by either dropping redundant features
        or trimming the shared 1D segment from geom_b.
        Returns (new_geom_a, new_geom_b, ok) where None means the feature should be dropped.
        """
        if geom_a is None or geom_b is None or geom_a.is_empty or geom_b.is_empty:
            return geom_a, geom_b, False
        if not geom_a.intersects(geom_b):
            return geom_a, geom_b, False

        inter = geom_a.intersection(geom_b)
        if inter is None or inter.is_empty or inter.length <= min_overlap:
            return geom_a, geom_b, False

        # 1. If geom_b is completely covered by geom_a or identical
        diff_b = geom_b.difference(geom_a)
        if diff_b is None or diff_b.is_empty or diff_b.length <= min_overlap:
            return geom_a, None, True

        # 2. If geom_a is completely covered by geom_b
        diff_a = geom_a.difference(geom_b)
        if diff_a is None or diff_a.is_empty or diff_a.length <= min_overlap:
            return None, geom_b, True

        # 3. Partial overlap: trim geom_b by removing the shared segment
        return geom_a, diff_b, True

    @classmethod
    def _resolve_pseudo_node(cls, geom_a, geom_b):
        """
        Merges two lines meeting at a pseudo-node into a single continuous LineString.
        """
        if geom_a is None or geom_b is None or geom_a.is_empty or geom_b.is_empty:
            return None, False
        try:
            lines = []
            if hasattr(geom_a, "geoms"):
                lines.extend(list(geom_a.geoms))
            else:
                lines.append(geom_a)
            if hasattr(geom_b, "geoms"):
                lines.extend(list(geom_b.geoms))
            else:
                lines.append(geom_b)

            merged = shapely.ops.linemerge(lines)
            if merged is not None and not merged.is_empty:
                orig_cnt = len(lines)
                new_cnt = len(merged.geoms) if hasattr(merged, "geoms") else 1
                if new_cnt < orig_cnt:
                    cleaned = cls._clean_line_duplicates(merged)
                    return cleaned, True
        except Exception:
            pass
        return None, False

    @staticmethod
    def _snap_geom_to_target(geom_a, geom_b, snap_tol: float):
        """
        Snaps the nearest open endpoint of geom_a to the closest vertex or edge on geom_b.
        Returns (new_geom_a, new_geom_b, ok).
        """
        if geom_a is None or geom_b is None or geom_a.is_empty or geom_b.is_empty:
            return geom_a, geom_b, False

        sub_lines = list(geom_a.geoms) if hasattr(geom_a, "geoms") else [geom_a]
        best_candidate = None
        min_dist = float("inf")

        for l_idx, line in enumerate(sub_lines):
            if line.geom_type != "LineString" or len(line.coords) < 2:
                continue
            p_start = Point(line.coords[0])
            p_end = Point(line.coords[-1])
            d_start = p_start.distance(geom_b)
            d_end = p_end.distance(geom_b)

            if 1e-8 < d_start <= snap_tol and d_start < min_dist:
                min_dist = d_start
                best_candidate = (l_idx, "start", p_start)
            if 1e-8 < d_end <= snap_tol and d_end < min_dist:
                min_dist = d_end
                best_candidate = (l_idx, "end", p_end)

        if best_candidate is None:
            return geom_a, geom_b, False

        l_idx, which, p_src = best_candidate
        _, p_near = shapely.ops.nearest_points(p_src, geom_b)

        orig_line = sub_lines[l_idx]
        coords = list(orig_line.coords)
        if which == "start":
            coords[0] = (p_near.x, p_near.y)
        else:
            coords[-1] = (p_near.x, p_near.y)

        sub_lines[l_idx] = LineString(coords)
        new_geom_a = MultiLineString(sub_lines) if hasattr(geom_a, "geoms") else sub_lines[0]

        try:
            new_geom_b = shapely.snap(geom_b, new_geom_a, tolerance=1e-5)
        except Exception:
            new_geom_b = geom_b

        return new_geom_a, new_geom_b, True

    @classmethod
    def _check_line_duplicate_nodes(cls, gdf: gpd.GeoDataFrame, tolerance: float = 0.0, start_id: int = 0, meters_per_unit: float = 1.0) -> List[TopologyError]:
        errors = []
        rule = cls.RULES[TopologyRuleCode.LINE_DUPLICATE_NODES]
        curr_id = start_id
        tol_sq = tolerance * tolerance if tolerance > 0 else 0.0

        for idx, geom in gdf.geometry.items():
            if geom is None or geom.is_empty:
                continue

            lines = geom.geoms if hasattr(geom, "geoms") else [geom]
            dup_points = []
            for line in lines:
                if line.geom_type != "LineString":
                    continue
                coords = list(line.coords)
                for i in range(len(coords) - 1):
                    p0 = coords[i]
                    p1 = coords[i + 1]
                    is_dup = (p0 == p1)
                    if not is_dup and tolerance > 0:
                        dx = p0[0] - p1[0]
                        dy = p0[1] - p1[1]
                        if (dx * dx + dy * dy) <= tol_sq:
                            is_dup = True
                    if is_dup:
                        dup_points.append(Point(p0))

            if dup_points:
                err_geom = MultiPoint(dup_points) if len(dup_points) > 1 else dup_points[0]
                tol_str = f" within {tolerance * meters_per_unit:.3g} m" if tolerance > 0 else ""
                errors.append(TopologyError(
                    id=curr_id,
                    rule_code=rule.code,
                    rule_name=rule.name,
                    feature_ids=[idx],
                    geometry=err_geom,
                    description=f"Line feature #{idx} has {len(dup_points)} consecutive duplicate vertices{tol_str}.",
                    severity="warning",
                    can_fix=True
                ))
                curr_id += 1
        return errors

    @classmethod
    def _check_line_spikes(cls, gdf: gpd.GeoDataFrame, max_angle_deg: float = 15.0, start_id: int = 0) -> List[TopologyError]:
        errors = []
        rule = cls.RULES[TopologyRuleCode.LINE_SPIKES]
        curr_id = start_id
        cos_thresh = math.cos(math.radians(max_angle_deg))

        for idx, geom in gdf.geometry.items():
            if geom is None or geom.is_empty:
                continue

            lines = geom.geoms if hasattr(geom, "geoms") else [geom]
            spike_points = []
            for line in lines:
                if line.geom_type != "LineString":
                    continue
                coords = list(line.coords)
                if len(coords) < 3:
                    continue

                for i in range(1, len(coords) - 1):
                    p0 = coords[i - 1]
                    p1 = coords[i]
                    p2 = coords[i + 1]

                    # 1. Retraced spike: p0 == p2
                    if p0 == p2:
                        spike_points.append(Point(p1))
                        continue

                    # 2. Acute angle spike
                    v1x, v1y = p0[0] - p1[0], p0[1] - p1[1]
                    v2x, v2y = p2[0] - p1[0], p2[1] - p1[1]
                    len1 = math.hypot(v1x, v1y)
                    len2 = math.hypot(v2x, v2y)

                    if len1 > 0 and len2 > 0:
                        dot = (v1x * v2x + v1y * v2y) / (len1 * len2)
                        if dot >= cos_thresh:
                            spike_points.append(Point(p1))

            if spike_points:
                err_geom = MultiPoint(spike_points) if len(spike_points) > 1 else spike_points[0]
                errors.append(TopologyError(
                    id=curr_id,
                    rule_code=rule.code,
                    rule_name=rule.name,
                    feature_ids=[idx],
                    geometry=err_geom,
                    description=f"Line feature #{idx} contains {len(spike_points)} spike(s) or retraced segments.",
                    severity="warning",
                    can_fix=True
                ))
                curr_id += 1
        return errors

    @classmethod
    def _check_line_dangles(cls, gdf: gpd.GeoDataFrame, snap_tolerance: float, start_id: int, meters_per_unit: float = 1.0) -> List[TopologyError]:
        errors = []
        rule = cls.RULES[TopologyRuleCode.LINE_DANGLES]
        curr_id = start_id

        endpoints = []
        geoms_list = []
        indices_list = []
        for idx, geom in gdf.geometry.items():
            if geom is None or geom.is_empty:
                continue
            geoms_list.append(geom)
            indices_list.append(idx)
            lines = geom.geoms if hasattr(geom, "geoms") else [geom]
            for line in lines:
                if line.geom_type == "LineString" and len(line.coords) >= 2:
                    endpoints.append((Point(line.coords[0]), idx, "start"))
                    endpoints.append((Point(line.coords[-1]), idx, "end"))

        if not endpoints:
            return errors

        pts = [p for p, _, _ in endpoints]
        end_tree = shapely.STRtree(pts)
        line_tree = shapely.STRtree(geoms_list)

        for pt, idx, which in endpoints:
            # 1. Does this endpoint touch another feature's vertex or edge?
            inter_line_indices = line_tree.query(pt, predicate="dwithin", distance=1e-8)
            touches_other = any(indices_list[g_i] != idx for g_i in inter_line_indices)
            if touches_other:
                continue  # Connected to another feature, not a dangle

            # Check if it connects to another part of the same feature (e.g. closed loop)
            same_feat_matches = [m for m in end_tree.query(pt, predicate="dwithin", distance=1e-8) if endpoints[m][1] == idx]
            if len(same_feat_matches) > 1:
                continue  # Closed loop within the same feature

            # 2. It IS an open endpoint (dangle). Is it an undershoot (near another feature within snap_tolerance)?
            nearby_lines = [g_i for g_i in line_tree.query(pt, predicate="dwithin", distance=snap_tolerance) if indices_list[g_i] != idx]
            if nearby_lines:
                # Find nearest target line
                best_g_i = min(nearby_lines, key=lambda g_i: pt.distance(geoms_list[g_i]))
                best_idx = indices_list[best_g_i]
                min_dist = pt.distance(geoms_list[best_g_i])
                min_dist_m = min_dist * meters_per_unit
                snap_tol_m = snap_tolerance * meters_per_unit
                errors.append(TopologyError(
                    id=curr_id,
                    rule_code=rule.code,
                    rule_name=rule.name,
                    feature_ids=[idx, best_idx],
                    geometry=pt,
                    description=f"Undershoot dangle ({which}) on line #{idx} is {min_dist_m:.2f} m from line #{best_idx} (snap tolerance: {snap_tol_m:.2f} m).",
                    severity="warning",
                    can_fix=True
                ))
            else:
                errors.append(TopologyError(
                    id=curr_id,
                    rule_code=rule.code,
                    rule_name=rule.name,
                    feature_ids=[idx],
                    geometry=pt,
                    description=f"Dangling endpoint ({which}) on line #{idx} (dead-end).",
                    severity="info",
                    can_fix=False
                ))
            curr_id += 1
        return errors

    @classmethod
    def _check_line_pseudo_nodes(cls, gdf: gpd.GeoDataFrame, start_id: int) -> List[TopologyError]:
        errors = []
        rule = cls.RULES[TopologyRuleCode.LINE_PSEUDO_NODES]
        curr_id = start_id

        endpoints = []
        geoms_list = []
        indices_list = []
        for idx, geom in gdf.geometry.items():
            if geom is None or geom.is_empty:
                continue
            geoms_list.append(geom)
            indices_list.append(idx)
            lines = geom.geoms if hasattr(geom, "geoms") else [geom]
            for line in lines:
                if line.geom_type == "LineString" and len(line.coords) >= 2:
                    endpoints.append((Point(line.coords[0]), idx))
                    endpoints.append((Point(line.coords[-1]), idx))

        if not endpoints:
            return errors

        pts = [p for p, _ in endpoints]
        tree = shapely.STRtree(pts)
        line_tree = shapely.STRtree(geoms_list)
        checked = set()

        for pt, idx in endpoints:
            matches = tree.query(pt, predicate="dwithin", distance=1e-8)
            if len(matches) == 2:
                idx_a = endpoints[matches[0]][1]
                idx_b = endpoints[matches[1]][1]
                if idx_a != idx_b:
                    coord_key = (round(pt.x, 7), round(pt.y, 7))
                    if coord_key not in checked:
                        checked.add(coord_key)
                        touching_geoms = line_tree.query(pt, predicate="dwithin", distance=1e-8)
                        other_touching = [indices_list[g_i] for g_i in touching_geoms if indices_list[g_i] not in (idx_a, idx_b)]
                        if not other_touching:
                            errors.append(TopologyError(
                                id=curr_id,
                                rule_code=rule.code,
                                rule_name=rule.name,
                                feature_ids=[idx_a, idx_b],
                                geometry=pt,
                                description=f"Pseudo-node joining lines #{idx_a} and #{idx_b} (can be merged).",
                                severity="warning",
                                can_fix=True
                            ))
                            curr_id += 1
        return errors

    @classmethod
    def _check_line_short_segments(cls, gdf: gpd.GeoDataFrame, min_length: float, start_id: int, meters_per_unit: float = 1.0) -> List[TopologyError]:
        errors = []
        rule = cls.RULES[TopologyRuleCode.LINE_SHORT_SEGMENTS]
        curr_id = start_id

        for idx, geom in gdf.geometry.items():
            if geom is None or geom.is_empty or geom.geom_type not in ("LineString", "MultiLineString"):
                continue

            if geom.length < min_length:
                geom_len_m = geom.length * meters_per_unit
                thresh_len_m = min_length * meters_per_unit
                errors.append(TopologyError(
                    id=curr_id,
                    rule_code=rule.code,
                    rule_name=rule.name,
                    feature_ids=[idx],
                    geometry=geom,
                    description=f"Line feature #{idx} length ({geom_len_m:.2f} m) is below minimum threshold ({thresh_len_m:.2f} m).",
                    severity="warning",
                    can_fix=True
                ))
                curr_id += 1
        return errors

    @classmethod
    def _check_line_overlaps(cls, gdf: gpd.GeoDataFrame, start_id: int) -> List[TopologyError]:
        errors = []
        rule = cls.RULES[TopologyRuleCode.LINE_OVERLAPS]
        curr_id = start_id

        valid_mask = gdf.geometry.notna() & ~gdf.geometry.is_empty
        sub_gdf = gdf[valid_mask]
        geoms = sub_gdf.geometry.values
        indices = sub_gdf.index.values

        if len(geoms) < 2:
            return errors

        tree = shapely.STRtree(geoms)
        matches = tree.query(geoms, predicate="intersects")

        seen_pairs = set()
        for i, j in zip(matches[0], matches[1]):
            if i < j:
                idx_i = indices[i]
                idx_j = indices[j]
                pair_key = (min(idx_i, idx_j), max(idx_i, idx_j))
                if pair_key not in seen_pairs:
                    seen_pairs.add(pair_key)
                    try:
                        inter = geoms[i].intersection(geoms[j])
                        if inter is not None and not inter.is_empty and inter.length > 1e-8:
                            errors.append(TopologyError(
                                id=curr_id,
                                rule_code=rule.code,
                                rule_name=rule.name,
                                feature_ids=[idx_i, idx_j],
                                geometry=inter,
                                description=f"Lines #{idx_i} and #{idx_j} overlap by length {inter.length:.4g}.",
                                severity="error",
                                can_fix=True
                            ))
                            curr_id += 1
                    except Exception:
                        pass
        return errors

    @classmethod
    def _check_polygon_ogc_valid(cls, gdf: gpd.GeoDataFrame, start_id: int) -> List[TopologyError]:
        errors = []
        rule = cls.RULES[TopologyRuleCode.POLYGON_OGC_VALID]
        curr_id = start_id

        for idx, geom in gdf.geometry.items():
            if geom is None or geom.is_empty:
                continue

            if not geom.is_valid:
                try:
                    reason = shapely.is_valid_reason(geom)
                except Exception as e:
                    reason = str(e)

                # Attempt to extract invalid point from reason text e.g. "Self-intersection[32.8 39.9]"
                err_geom = None
                if "[" in reason and "]" in reason:
                    try:
                        coords_str = reason[reason.find("[") + 1: reason.find("]")]
                        parts = coords_str.strip().split()
                        if len(parts) >= 2:
                            err_geom = Point(float(parts[0]), float(parts[1]))
                    except Exception:
                        pass

                if err_geom is None:
                    try:
                        b = geom.exterior
                        noded = shapely.node(b)
                        subgeoms = noded.geoms if hasattr(noded, "geoms") else [noded]
                        pts = [c for g in subgeoms for c in (g.coords[0], g.coords[-1])]
                        from collections import Counter
                        cnts = Counter(pts)
                        crossings = [Point(c) for c, cnt in cnts.items() if cnt >= 4]
                        if crossings:
                            err_geom = MultiPoint(crossings) if len(crossings) > 1 else crossings[0]
                    except Exception:
                        pass

                if err_geom is None:
                    err_geom = geom.centroid if geom is not None and not geom.is_empty else Point(0, 0)

                errors.append(TopologyError(
                    id=curr_id,
                    rule_code=rule.code,
                    rule_name=rule.name,
                    feature_ids=[idx],
                    geometry=err_geom,
                    description=f"Polygon #{idx} is OGC invalid: {reason}",
                    severity="error",
                    can_fix=True
                ))
                curr_id += 1
        return errors

    @classmethod
    def _check_polygon_duplicate_vertices(cls, gdf: gpd.GeoDataFrame, start_id: int) -> List[TopologyError]:
        errors = []
        rule = cls.RULES[TopologyRuleCode.POLYGON_DUPLICATE_VERTICES]
        curr_id = start_id

        for idx, geom in gdf.geometry.items():
            if geom is None or geom.is_empty:
                continue

            polys = geom.geoms if hasattr(geom, "geoms") else [geom]
            dup_points = []
            for poly in polys:
                if poly.geom_type != "Polygon":
                    continue
                # check exterior
                ext_coords = list(poly.exterior.coords)
                for i in range(len(ext_coords) - 1):
                    if ext_coords[i] == ext_coords[i + 1]:
                        dup_points.append(Point(ext_coords[i]))
                # check interiors
                for ring in poly.interiors:
                    ring_coords = list(ring.coords)
                    for i in range(len(ring_coords) - 1):
                        if ring_coords[i] == ring_coords[i + 1]:
                            dup_points.append(Point(ring_coords[i]))

            if dup_points:
                err_geom = MultiPoint(dup_points) if len(dup_points) > 1 else dup_points[0]
                errors.append(TopologyError(
                    id=curr_id,
                    rule_code=rule.code,
                    rule_name=rule.name,
                    feature_ids=[idx],
                    geometry=err_geom,
                    description=f"Polygon #{idx} contains {len(dup_points)} consecutive duplicate vertices.",
                    severity="warning",
                    can_fix=True
                ))
                curr_id += 1
        return errors

    @classmethod
    def _check_polygon_overlaps(cls, gdf: gpd.GeoDataFrame, min_area: float, start_id: int, sqmeters_per_unit: float = 1.0) -> List[TopologyError]:
        errors = []
        rule = cls.RULES[TopologyRuleCode.POLYGON_OVERLAPS]
        curr_id = start_id

        valid_mask = gdf.geometry.notna() & ~gdf.geometry.is_empty
        sub_gdf = gdf[valid_mask]
        geoms = sub_gdf.geometry.values
        indices = sub_gdf.index.values

        if len(geoms) < 2:
            return errors

        tree = shapely.STRtree(geoms)
        matches = tree.query(geoms, predicate="overlaps")

        seen_pairs = set()
        for i, j in zip(matches[0], matches[1]):
            if i < j:
                idx_i = indices[i]
                idx_j = indices[j]
                pair_key = (min(idx_i, idx_j), max(idx_i, idx_j))
                if pair_key not in seen_pairs:
                    seen_pairs.add(pair_key)
                    try:
                        inter = geoms[i].intersection(geoms[j])
                        if inter is not None and not inter.is_empty and inter.area >= min_area:
                            inter_area_m2 = inter.area * sqmeters_per_unit
                            errors.append(TopologyError(
                                id=curr_id,
                                rule_code=rule.code,
                                rule_name=rule.name,
                                feature_ids=[idx_i, idx_j],
                                geometry=inter,
                                description=f"Polygons #{idx_i} and #{idx_j} overlap by area {inter_area_m2:.2f} m².",
                                severity="error",
                                can_fix=True
                            ))
                            curr_id += 1
                    except Exception:
                        pass
        return errors

    @classmethod
    def _check_polygon_slivers(cls, gdf: gpd.GeoDataFrame, min_area: float, thinness_threshold: float, start_id: int, sqmeters_per_unit: float = 1.0) -> List[TopologyError]:
        errors = []
        rule = cls.RULES[TopologyRuleCode.POLYGON_SLIVERS]
        curr_id = start_id

        for idx, geom in gdf.geometry.items():
            if geom is None or geom.is_empty:
                continue

            polys = geom.geoms if hasattr(geom, "geoms") else [geom]
            for poly in polys:
                if poly.geom_type != "Polygon":
                    continue
                area = poly.area
                peri = poly.length
                if peri <= 0:
                    continue

                thinness = (4 * math.pi * area) / (peri ** 2)
                is_micro = area < min_area
                is_sliver = thinness < thinness_threshold and area < (min_area * 1000)

                if is_micro or is_sliver:
                    area_m2 = area * sqmeters_per_unit
                    reason = f"Micro-area ({area_m2:.2f} m²)" if is_micro else f"Thinness ratio ({thinness:.4f} < {thinness_threshold})"
                    errors.append(TopologyError(
                        id=curr_id,
                        rule_code=rule.code,
                        rule_name=rule.name,
                        feature_ids=[idx],
                        geometry=poly,
                        description=f"Polygon #{idx} flagged as sliver/micro-geometry: {reason}.",
                        severity="warning",
                        can_fix=True
                    ))
                    curr_id += 1
        return errors

    @classmethod
    def _check_polygon_gaps(cls, gdf: gpd.GeoDataFrame, max_gap_area: float, start_id: int, sqmeters_per_unit: float = 1.0) -> List[TopologyError]:
        errors = []
        rule = cls.RULES[TopologyRuleCode.POLYGON_GAPS]
        curr_id = start_id

        valid_geoms = [g for g in gdf.geometry if g is not None and not g.is_empty and g.geom_type in ("Polygon", "MultiPolygon")]
        if len(valid_geoms) < 2:
            return errors

        try:
            combined = unary_union(valid_geoms)
            subgeoms = combined.geoms if hasattr(combined, "geoms") else [combined]
            for geom in subgeoms:
                if geom.geom_type == "Polygon":
                    for interior in geom.interiors:
                        hole = Polygon(interior)
                        if 0 < hole.area <= max_gap_area:
                            hole_area_m2 = hole.area * sqmeters_per_unit
                            errors.append(TopologyError(
                                id=curr_id,
                                rule_code=rule.code,
                                rule_name=rule.name,
                                feature_ids=[],
                                geometry=hole,
                                description=f"Enclosed gap / void found between adjacent polygons (Area: {hole_area_m2:.2f} m²).",
                                severity="warning",
                                can_fix=False
                            ))
                            curr_id += 1
        except Exception:
            pass

        return errors

    # -------------------------------------------------------------
    # Automated Repair Methods
    # -------------------------------------------------------------

    @classmethod
    def fix_all(cls, gdf: gpd.GeoDataFrame, report: TopologyReport) -> Tuple[gpd.GeoDataFrame, int]:
        """
        Applies all supported automatic fixes sequentially.
        Returns: (repaired_gdf, fixed_count)
        """
        if gdf is None or gdf.empty or report.total_errors == 0:
            return gdf, 0

        res_gdf = gdf.copy()
        total_fixed = 0
        meters_per_unit, sqmeters_per_unit = cls.get_metric_conversion_factors(res_gdf)

        # 1. Clean empty / null geometries
        if TopologyRuleCode.GEOM_EMPTY_NULL in report.rule_counts:
            orig_len = len(res_gdf)
            res_gdf = res_gdf[res_gdf.geometry.notna() & ~res_gdf.geometry.is_empty].copy()
            total_fixed += (orig_len - len(res_gdf))

        # 2. Repair Line Self-Intersection (Noding)
        if TopologyRuleCode.LINE_SELF_INTERSECT in report.rule_counts:
            fixed_self_inter = 0
            for idx in list(res_gdf.index):
                geom = res_gdf.geometry.loc[idx]
                if geom is not None and not geom.is_empty and geom.geom_type in ("LineString", "MultiLineString"):
                    if not geom.is_simple:
                        noded = cls._clean_line_self_intersect(geom)
                        if noded is not None and not noded.is_empty and noded != geom:
                            res_gdf.loc[idx, "geometry"] = noded
                            fixed_self_inter += 1
            total_fixed += fixed_self_inter

        # 3. Clean line duplicate vertices (preserving collinear vertices)
        if TopologyRuleCode.LINE_DUPLICATE_NODES in report.rule_counts:
            fixed_dups = 0
            for idx in list(res_gdf.index):
                geom = res_gdf.geometry.loc[idx]
                if geom is not None and not geom.is_empty and geom.geom_type in ("LineString", "MultiLineString"):
                    cleaned = cls._clean_line_duplicates(geom)
                    if cleaned is not None and not cleaned.is_empty and cleaned != geom:
                        res_gdf.loc[idx, "geometry"] = cleaned
                        fixed_dups += 1
            total_fixed += fixed_dups

        # 4. Clean line spikes & retraced segments
        if TopologyRuleCode.LINE_SPIKES in report.rule_counts:
            fixed_spikes = 0
            max_angle = 15.0
            for r in getattr(report, "configured_rules", []):
                if r.code == TopologyRuleCode.LINE_SPIKES:
                    max_angle = float(r.params.get("max_angle", 15.0))
            for idx in list(res_gdf.index):
                geom = res_gdf.geometry.loc[idx]
                if geom is not None and not geom.is_empty and geom.geom_type in ("LineString", "MultiLineString"):
                    cleaned = cls._clean_line_spikes(geom, max_angle_deg=max_angle)
                    if cleaned is not None and not cleaned.is_empty and cleaned != geom:
                        res_gdf.loc[idx, "geometry"] = cleaned
                        fixed_spikes += 1
            total_fixed += fixed_spikes

        # 5. Clean line short segments
        if TopologyRuleCode.LINE_SHORT_SEGMENTS in report.rule_counts:
            min_len_m = 0.50
            for r in getattr(report, "configured_rules", []):
                if r.code == TopologyRuleCode.LINE_SHORT_SEGMENTS:
                    min_len_m = float(r.params.get("min_length", 0.50))
            min_len = min_len_m / meters_per_unit
            is_line = res_gdf.geometry.geom_type.isin(["LineString", "MultiLineString"])
            too_short = is_line & (res_gdf.geometry.length < min_len)
            res_gdf = res_gdf[~too_short].copy()
            total_fixed += int(too_short.sum())

        # 6. Clean line overlaps
        if TopologyRuleCode.LINE_OVERLAPS in report.rule_counts:
            fixed_line_overlaps = 0
            overlap_errs = [e for e in report.errors if e.rule_code == TopologyRuleCode.LINE_OVERLAPS]
            for err in overlap_errs:
                if len(err.feature_ids) < 2:
                    continue
                idx_a, idx_b = err.feature_ids[0], err.feature_ids[1]
                if idx_a not in res_gdf.index or idx_b not in res_gdf.index:
                    continue
                geom_a = res_gdf.geometry.loc[idx_a]
                geom_b = res_gdf.geometry.loc[idx_b]
                new_a, new_b, ok = cls._resolve_line_overlap(geom_a, geom_b)
                if ok:
                    if new_a is None:
                        res_gdf = res_gdf.drop(index=idx_a)
                    else:
                        res_gdf.loc[idx_a, "geometry"] = new_a
                    if new_b is None:
                        res_gdf = res_gdf.drop(index=idx_b)
                    else:
                        res_gdf.loc[idx_b, "geometry"] = new_b
                    fixed_line_overlaps += 1
            total_fixed += fixed_line_overlaps

        # 7. Snap line dangles (undershoots)
        if TopologyRuleCode.LINE_DANGLES in report.rule_counts:
            snap_tol_m = 0.10
            for r in getattr(report, "configured_rules", []):
                if r.code == TopologyRuleCode.LINE_DANGLES:
                    snap_tol_m = float(r.params.get("tolerance", 0.10))
            snap_tol = snap_tol_m / meters_per_unit
            fixed_dangles = 0
            dangle_errs = [e for e in report.errors if e.rule_code == TopologyRuleCode.LINE_DANGLES and e.can_fix]
            for err in dangle_errs:
                if not err.feature_ids:
                    continue
                idx_a = err.feature_ids[0]
                target_idx = err.feature_ids[1] if len(err.feature_ids) >= 2 else None
                if idx_a not in res_gdf.index or target_idx is None or target_idx not in res_gdf.index:
                    continue
                geom_a = res_gdf.geometry.loc[idx_a]
                geom_b = res_gdf.geometry.loc[target_idx]
                new_a, new_b, ok = cls._snap_geom_to_target(geom_a, geom_b, snap_tol)
                if ok:
                    res_gdf.loc[idx_a, "geometry"] = new_a
                    res_gdf.loc[target_idx, "geometry"] = new_b
                    fixed_dangles += 1
            total_fixed += fixed_dangles

        # 8. Merge line pseudo-nodes
        if TopologyRuleCode.LINE_PSEUDO_NODES in report.rule_counts:
            fixed_pseudo = 0
            pseudo_errs = [e for e in report.errors if e.rule_code == TopologyRuleCode.LINE_PSEUDO_NODES]
            for err in pseudo_errs:
                if len(err.feature_ids) < 2:
                    continue
                idx_a, idx_b = err.feature_ids[0], err.feature_ids[1]
                if idx_a not in res_gdf.index or idx_b not in res_gdf.index:
                    continue
                geom_a = res_gdf.geometry.loc[idx_a]
                geom_b = res_gdf.geometry.loc[idx_b]
                merged, ok = cls._resolve_pseudo_node(geom_a, geom_b)
                if ok:
                    res_gdf.loc[idx_a, "geometry"] = merged
                    res_gdf = res_gdf.drop(index=idx_b)
                    fixed_pseudo += 1
            total_fixed += fixed_pseudo

        # 9. Repair Polygon OGC valid
        if TopologyRuleCode.POLYGON_OGC_VALID in report.rule_counts:
            invalid_mask = ~res_gdf.geometry.is_valid & res_gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])
            count_invalid = int(invalid_mask.sum())
            if count_invalid > 0:
                res_gdf.loc[invalid_mask, "geometry"] = res_gdf.loc[invalid_mask, "geometry"].apply(
                    lambda g: shapely.make_valid(g) if g is not None and not g.is_empty else g
                )
                total_fixed += count_invalid

        # 7. Clean Polygon duplicate vertices
        if TopologyRuleCode.POLYGON_DUPLICATE_VERTICES in report.rule_counts:
            fixed_dups = 0
            for idx in res_gdf.index:
                geom = res_gdf.geometry.loc[idx]
                if geom is not None and not geom.is_empty and geom.geom_type in ("Polygon", "MultiPolygon"):
                    cleaned = shapely.simplify(geom, tolerance=0)
                    if cleaned is not None and not cleaned.is_empty:
                        res_gdf.loc[idx, "geometry"] = cleaned
                        fixed_dups += 1
            if fixed_dups > 0:
                total_fixed += min(fixed_dups, report.rule_counts.get(TopologyRuleCode.POLYGON_DUPLICATE_VERTICES, 0))

        # 4. Repair Point Duplicates
        if TopologyRuleCode.POINT_DUPLICATES in report.rule_counts:
            tol_m = 0.05
            for r in getattr(report, "configured_rules", []):
                if r.code == TopologyRuleCode.POINT_DUPLICATES:
                    tol_m = float(r.params.get("tolerance", 0.05))
            tol_native = tol_m / meters_per_unit
            orig_cnt = len(res_gdf)
            if tol_native > 1e-9:
                valid_mask = res_gdf.geometry.notna() & ~res_gdf.geometry.is_empty
                pts_geoms = res_gdf[valid_mask].geometry.values
                pts_indices = list(res_gdf[valid_mask].index)
                if len(pts_geoms) >= 2:
                    tree = shapely.STRtree(pts_geoms)
                    matches = tree.query(pts_geoms, predicate="dwithin", distance=tol_native)
                    to_drop = set()
                    for i, j in zip(matches[0], matches[1]):
                        if i < j and pts_indices[i] not in to_drop:
                            to_drop.add(pts_indices[j])
                    if to_drop:
                        res_gdf = res_gdf.drop(index=list(to_drop)).copy()
            else:
                res_gdf = res_gdf.drop_duplicates(subset=["geometry"]).copy()
            total_fixed += (orig_cnt - len(res_gdf))

        # 5. Resolve Polygon Overlaps (clip overlapping regions)
        if TopologyRuleCode.POLYGON_OVERLAPS in report.rule_counts:
            fixed_overlaps = 0
            min_area_m = 0.10
            for r in getattr(report, "configured_rules", []):
                if r.code == TopologyRuleCode.POLYGON_OVERLAPS:
                    min_area_m = float(r.params.get("min_area", 0.10))
            min_area = min_area_m / sqmeters_per_unit
            indices = list(res_gdf.index)
            for i in range(len(indices)):
                for j in range(i + 1, len(indices)):
                    idx_i, idx_j = indices[i], indices[j]
                    if idx_i not in res_gdf.index or idx_j not in res_gdf.index:
                        continue
                    geom_i = res_gdf.geometry.loc[idx_i]
                    geom_j = res_gdf.geometry.loc[idx_j]
                    if geom_i is not None and geom_j is not None and geom_i.intersects(geom_j):
                        inter = geom_i.intersection(geom_j)
                        if inter.area >= min_area:
                            new_geom_j = geom_j.difference(geom_i)
                            if new_geom_j is not None and not new_geom_j.is_empty:
                                res_gdf.loc[idx_j, "geometry"] = new_geom_j
                                fixed_overlaps += 1
            total_fixed += fixed_overlaps

        # 6. Eliminate slivers (merge with longest neighbor)
        if TopologyRuleCode.POLYGON_SLIVERS in report.rule_counts:
            sliver_errs = [e for e in report.errors if e.rule_code == TopologyRuleCode.POLYGON_SLIVERS]
            sliver_indices = set(e.feature_ids[0] for e in sliver_errs if e.feature_ids)
            fixed_slivers = 0
            for s_idx in sliver_indices:
                if s_idx not in res_gdf.index:
                    continue
                s_geom = res_gdf.geometry.loc[s_idx]
                # Find adjacent neighbor with longest shared boundary
                best_neighbor = None
                max_shared_len = 0.0
                for n_idx in res_gdf.index:
                    if n_idx == s_idx:
                        continue
                    n_geom = res_gdf.geometry.loc[n_idx]
                    if n_geom is not None and s_geom.touches(n_geom):
                        shared_len = s_geom.boundary.intersection(n_geom.boundary).length
                        if shared_len > max_shared_len:
                            max_shared_len = shared_len
                            best_neighbor = n_idx

                if best_neighbor is not None:
                    n_geom = res_gdf.geometry.loc[best_neighbor]
                    merged = unary_union([n_geom, s_geom])
                    res_gdf.loc[best_neighbor, "geometry"] = merged
                    res_gdf = res_gdf.drop(index=s_idx)
                    fixed_slivers += 1
            total_fixed += fixed_slivers

        return res_gdf, total_fixed

    @classmethod
    def fix_single_error(cls, gdf: gpd.GeoDataFrame, error: TopologyError) -> Tuple[gpd.GeoDataFrame, bool]:
        """
        Attempts to fix a single specific topology error.
        """
        if gdf is None or gdf.empty or not error.feature_ids:
            return gdf, False

        res_gdf = gdf.copy()
        feat_id = error.feature_ids[0]
        if feat_id not in res_gdf.index:
            return gdf, False

        rule = error.rule_code

        if rule == TopologyRuleCode.GEOM_EMPTY_NULL:
            res_gdf = res_gdf.drop(index=feat_id)
            return res_gdf, True

        elif rule == TopologyRuleCode.LINE_SELF_INTERSECT:
            geom = res_gdf.geometry.loc[feat_id]
            if geom is not None and not geom.is_empty:
                noded = cls._clean_line_self_intersect(geom)
                if noded is not None and not noded.is_empty:
                    res_gdf.loc[feat_id, "geometry"] = noded
                    return res_gdf, True

        elif rule == TopologyRuleCode.LINE_DUPLICATE_NODES:
            geom = res_gdf.geometry.loc[feat_id]
            if geom is not None and not geom.is_empty:
                cleaned = cls._clean_line_duplicates(geom)
                if cleaned is not None and not cleaned.is_empty:
                    res_gdf.loc[feat_id, "geometry"] = cleaned
                    return res_gdf, True

        elif rule == TopologyRuleCode.LINE_SPIKES:
            geom = res_gdf.geometry.loc[feat_id]
            if geom is not None and not geom.is_empty:
                cleaned = cls._clean_line_spikes(geom)
                if cleaned is not None and not cleaned.is_empty:
                    res_gdf.loc[feat_id, "geometry"] = cleaned
                    return res_gdf, True

        elif rule == TopologyRuleCode.LINE_SHORT_SEGMENTS:
            res_gdf = res_gdf.drop(index=feat_id)
            return res_gdf, True

        elif rule == TopologyRuleCode.LINE_OVERLAPS and len(error.feature_ids) >= 2:
            feat_b = error.feature_ids[1]
            if feat_b in res_gdf.index:
                geom_a = res_gdf.geometry.loc[feat_id]
                geom_b = res_gdf.geometry.loc[feat_b]
                new_a, new_b, ok = cls._resolve_line_overlap(geom_a, geom_b)
                if ok:
                    if new_a is None:
                        res_gdf = res_gdf.drop(index=feat_id)
                    else:
                        res_gdf.loc[feat_id, "geometry"] = new_a
                    if new_b is None:
                        res_gdf = res_gdf.drop(index=feat_b)
                    else:
                        res_gdf.loc[feat_b, "geometry"] = new_b
                    return res_gdf, True

        elif rule == TopologyRuleCode.LINE_PSEUDO_NODES and len(error.feature_ids) >= 2:
            feat_b = error.feature_ids[1]
            if feat_b in res_gdf.index:
                geom_a = res_gdf.geometry.loc[feat_id]
                geom_b = res_gdf.geometry.loc[feat_b]
                merged, ok = cls._resolve_pseudo_node(geom_a, geom_b)
                if ok:
                    res_gdf.loc[feat_id, "geometry"] = merged
                    res_gdf = res_gdf.drop(index=feat_b)
                    return res_gdf, True

        elif rule == TopologyRuleCode.LINE_DANGLES and error.can_fix:
            target_idx = error.feature_ids[1] if len(error.feature_ids) >= 2 else None
            if target_idx is not None and target_idx in res_gdf.index:
                geom_a = res_gdf.geometry.loc[feat_id]
                geom_b = res_gdf.geometry.loc[target_idx]
                new_a, new_b, ok = cls._snap_geom_to_target(geom_a, geom_b, snap_tol=1000.0)
                if ok:
                    res_gdf.loc[feat_id, "geometry"] = new_a
                    res_gdf.loc[target_idx, "geometry"] = new_b
                    return res_gdf, True

        elif rule == TopologyRuleCode.POLYGON_OGC_VALID:
            geom = res_gdf.geometry.loc[feat_id]
            if geom is not None and not geom.is_empty:
                res_gdf.loc[feat_id, "geometry"] = shapely.make_valid(geom)
                return res_gdf, True

        elif rule == TopologyRuleCode.POLYGON_DUPLICATE_VERTICES:
            geom = res_gdf.geometry.loc[feat_id]
            if geom is not None and not geom.is_empty:
                res_gdf.loc[feat_id, "geometry"] = shapely.simplify(geom, tolerance=0)
                return res_gdf, True

        elif rule == TopologyRuleCode.POLYGON_OVERLAPS and len(error.feature_ids) >= 2:
            feat_b = error.feature_ids[1]
            if feat_b in res_gdf.index:
                geom_a = res_gdf.geometry.loc[feat_id]
                geom_b = res_gdf.geometry.loc[feat_b]
                diff_b = geom_b.difference(geom_a)
                if diff_b is not None and not diff_b.is_empty:
                    res_gdf.loc[feat_b, "geometry"] = diff_b
                    return res_gdf, True

        elif rule == TopologyRuleCode.POINT_DUPLICATES and len(error.feature_ids) >= 2:
            feat_b = error.feature_ids[1]
            if feat_b in res_gdf.index:
                res_gdf = res_gdf.drop(index=feat_b)
                return res_gdf, True

        return gdf, False
