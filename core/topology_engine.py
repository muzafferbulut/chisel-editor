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
        dist_unit = "°" if is_degree else "m"
        area_unit = "°²" if is_degree else "m²"
        parts = []
        if "tolerance" in self.params:
            tol = float(self.params["tolerance"])
            fmt = f"{tol:.6f}" if is_degree else f"{tol:.3f}"
            parts.append(f"Tolerance: {fmt} {dist_unit}")
        if "min_length" in self.params:
            ml = float(self.params["min_length"])
            fmt = f"{ml:.6f}" if is_degree else f"{ml:.3f}"
            parts.append(f"Min Length: {fmt} {dist_unit}")
        if "min_area" in self.params:
            ma = float(self.params["min_area"])
            fmt = f"{ma:.8f}" if is_degree else f"{ma:.2f}"
            parts.append(f"Min Area: {fmt} {area_unit}")
        if "thinness" in self.params:
            parts.append(f"Thinness: {float(self.params['thinness']):.3f}")
        if "max_gap_area" in self.params:
            mga = float(self.params["max_gap_area"])
            fmt = f"{mga:.8f}" if is_degree else f"{mga:.2f}"
            parts.append(f"Max Gap: {fmt} {area_unit}")
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


@dataclass
class TopologyReport:
    total_errors: int = 0
    errors: List[TopologyError] = field(default_factory=list)
    rule_counts: Dict[str, int] = field(default_factory=dict)
    errors_gdf: Optional[gpd.GeoDataFrame] = None
    layer_geom_type: str = "any"


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
        TopologyRuleCode.LINE_DANGLES: TopologyRuleInfo(
            code=TopologyRuleCode.LINE_DANGLES,
            name="Must Not Have Dangles",
            description="Flags open line endpoints not connected to other features in the network.",
            geom_types=["line", "mixed"],
            default_enabled=False,  # Can be many in non-closed road/river networks
            supports_auto_fix=False
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
        norm_type = (geom_type or "any").lower()
        res = []
        for rule in cls.RULES.values():
            if "any" in rule.geom_types or norm_type in rule.geom_types or norm_type == "mixed":
                res.append(rule)
        return res

    @classmethod
    def get_default_configured_rules(cls, geom_type: str, is_degree: bool) -> List[ConfiguredRule]:
        """
        Returns recommended rules with default thresholds tailored to the layer's CRS unit.
        """
        applicable = cls.get_applicable_rules(geom_type)
        res = []
        for r in applicable:
            if not r.default_enabled:
                continue
            params = {}
            if r.code == TopologyRuleCode.POINT_DUPLICATES:
                params["tolerance"] = 0.0001 if is_degree else 0.05
            elif r.code == TopologyRuleCode.LINE_DANGLES:
                params["tolerance"] = 0.0002 if is_degree else 0.10
            elif r.code == TopologyRuleCode.LINE_SHORT_SEGMENTS:
                params["min_length"] = 0.0001 if is_degree else 0.10
            elif r.code == TopologyRuleCode.POLYGON_OVERLAPS:
                params["min_area"] = 1e-7 if is_degree else 0.10
            elif r.code == TopologyRuleCode.POLYGON_SLIVERS:
                params["min_area"] = 1e-7 if is_degree else 1.0
                params["thinness"] = 0.03
            elif r.code == TopologyRuleCode.POLYGON_GAPS:
                params["max_gap_area"] = 1e-5 if is_degree else 50.0

            res.append(ConfiguredRule(code=r.code, name=r.name, params=params, description=r.description))
        return res

    @classmethod
    def run_configured_rules(
        cls,
        gdf: gpd.GeoDataFrame,
        configured_rules: List[ConfiguredRule]
    ) -> TopologyReport:
        """
        Executes a user-configured list of topology rules directly in the layer's
        native coordinate system unit (degrees for geographic CRS, meters for projected CRS).
        """
        if gdf is None or gdf.empty or not configured_rules:
            return TopologyReport()

        from core.spatial_ops import SpatialOps
        geom_type = SpatialOps.get_layer_geometry_type(gdf)

        orig_crs = gdf.crs or "EPSG:4326"

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
                tol = float(params.get("tolerance", 0.0001))
                found = cls._check_point_duplicates(gdf, tol, next_id)
                errors.extend(found)
                next_id += len(found)

            elif code == TopologyRuleCode.LINE_SELF_INTERSECT:
                found = cls._check_line_self_intersect(gdf, next_id)
                errors.extend(found)
                next_id += len(found)

            elif code == TopologyRuleCode.LINE_DUPLICATE_NODES:
                found = cls._check_line_duplicate_nodes(gdf, next_id)
                errors.extend(found)
                next_id += len(found)

            elif code == TopologyRuleCode.LINE_DANGLES:
                tol = float(params.get("tolerance", 0.0002))
                found = cls._check_line_dangles(gdf, tol, next_id)
                errors.extend(found)
                next_id += len(found)

            elif code == TopologyRuleCode.LINE_PSEUDO_NODES:
                found = cls._check_line_pseudo_nodes(gdf, next_id)
                errors.extend(found)
                next_id += len(found)

            elif code == TopologyRuleCode.LINE_SHORT_SEGMENTS:
                min_len = float(params.get("min_length", 0.0001))
                found = cls._check_line_short_segments(gdf, min_len, next_id)
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
                min_area = float(params.get("min_area", 1e-7))
                found = cls._check_polygon_overlaps(gdf, min_area, next_id)
                errors.extend(found)
                next_id += len(found)

            elif code == TopologyRuleCode.POLYGON_SLIVERS:
                min_area = float(params.get("min_area", 1e-7))
                thinness = float(params.get("thinness", 0.03))
                found = cls._check_polygon_slivers(gdf, min_area, thinness, next_id)
                errors.extend(found)
                next_id += len(found)

            elif code == TopologyRuleCode.POLYGON_GAPS:
                max_gap = float(params.get("max_gap_area", 1e-5))
                found = cls._check_polygon_gaps(gdf, max_gap, next_id)
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
            layer_geom_type=geom_type
        )

    @classmethod
    def run_checks(
        cls,
        gdf: gpd.GeoDataFrame,
        enabled_rules: Optional[List[str]] = None,
        snap_tolerance: float = 0.05,
        min_length: float = 0.1,
        min_area: float = 1.0,
        sliver_thinness: float = 0.03
    ) -> TopologyReport:
        """
        Convenience wrapper executing selected rules with default thresholds.
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
                params["max_gap_area"] = min_area * 100

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
    def _check_point_duplicates(cls, gdf: gpd.GeoDataFrame, tolerance: float, start_id: int) -> List[TopologyError]:
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
                        description=f"Features #{idx_i} and #{idx_j} are coincident / duplicates within {dist:g}.",
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

    @classmethod
    def _check_line_duplicate_nodes(cls, gdf: gpd.GeoDataFrame, start_id: int) -> List[TopologyError]:
        errors = []
        rule = cls.RULES[TopologyRuleCode.LINE_DUPLICATE_NODES]
        curr_id = start_id

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
                    if coords[i] == coords[i + 1]:
                        dup_points.append(Point(coords[i]))

            if dup_points:
                err_geom = MultiPoint(dup_points) if len(dup_points) > 1 else dup_points[0]
                errors.append(TopologyError(
                    id=curr_id,
                    rule_code=rule.code,
                    rule_name=rule.name,
                    feature_ids=[idx],
                    geometry=err_geom,
                    description=f"Line feature #{idx} has {len(dup_points)} consecutive duplicate vertices.",
                    severity="warning",
                    can_fix=True
                ))
                curr_id += 1
        return errors

    @classmethod
    def _check_line_dangles(cls, gdf: gpd.GeoDataFrame, snap_tolerance: float, start_id: int) -> List[TopologyError]:
        errors = []
        rule = cls.RULES[TopologyRuleCode.LINE_DANGLES]
        curr_id = start_id

        endpoints = []
        for idx, geom in gdf.geometry.items():
            if geom is None or geom.is_empty:
                continue
            lines = geom.geoms if hasattr(geom, "geoms") else [geom]
            for line in lines:
                if line.geom_type == "LineString" and len(line.coords) >= 2:
                    endpoints.append((Point(line.coords[0]), idx, "start"))
                    endpoints.append((Point(line.coords[-1]), idx, "end"))

        if not endpoints:
            return errors

        pts = [p for p, _, _ in endpoints]
        tree = shapely.STRtree(pts)

        for pt, idx, which in endpoints:
            matches = tree.query(pt, predicate="dwithin", distance=1e-8)
            if len(matches) <= 1:
                # It's an open endpoint
                nearby = tree.query(pt, predicate="dwithin", distance=snap_tolerance)
                is_close_undershoot = len(nearby) > 1
                desc = (
                    f"Dangle endpoint ({which}) on line #{idx} close to another node within snap tolerance."
                    if is_close_undershoot
                    else f"Dangling endpoint ({which}) on line #{idx}."
                )
                errors.append(TopologyError(
                    id=curr_id,
                    rule_code=rule.code,
                    rule_name=rule.name,
                    feature_ids=[idx],
                    geometry=pt,
                    description=desc,
                    severity="warning" if is_close_undershoot else "info",
                    can_fix=is_close_undershoot
                ))
                curr_id += 1
        return errors

    @classmethod
    def _check_line_pseudo_nodes(cls, gdf: gpd.GeoDataFrame, start_id: int) -> List[TopologyError]:
        errors = []
        rule = cls.RULES[TopologyRuleCode.LINE_PSEUDO_NODES]
        curr_id = start_id

        endpoints = []
        for idx, geom in gdf.geometry.items():
            if geom is None or geom.is_empty:
                continue
            lines = geom.geoms if hasattr(geom, "geoms") else [geom]
            for line in lines:
                if line.geom_type == "LineString" and len(line.coords) >= 2:
                    endpoints.append((Point(line.coords[0]), idx))
                    endpoints.append((Point(line.coords[-1]), idx))

        if not endpoints:
            return errors

        pts = [p for p, _ in endpoints]
        tree = shapely.STRtree(pts)
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
    def _check_line_short_segments(cls, gdf: gpd.GeoDataFrame, min_length: float, start_id: int) -> List[TopologyError]:
        errors = []
        rule = cls.RULES[TopologyRuleCode.LINE_SHORT_SEGMENTS]
        curr_id = start_id

        for idx, geom in gdf.geometry.items():
            if geom is None or geom.is_empty or geom.geom_type not in ("LineString", "MultiLineString"):
                continue

            if geom.length < min_length:
                errors.append(TopologyError(
                    id=curr_id,
                    rule_code=rule.code,
                    rule_name=rule.name,
                    feature_ids=[idx],
                    geometry=geom,
                    description=f"Line feature #{idx} length ({geom.length:.4g}) is below minimum threshold ({min_length:g}).",
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
                        if inter is not None and not inter.is_empty and inter.length > 0:
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
                err_geom = geom.centroid
                if "[" in reason and "]" in reason:
                    try:
                        coords_str = reason[reason.find("[") + 1: reason.find("]")]
                        parts = coords_str.strip().split()
                        if len(parts) >= 2:
                            err_geom = Point(float(parts[0]), float(parts[1]))
                    except Exception:
                        pass

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
    def _check_polygon_overlaps(cls, gdf: gpd.GeoDataFrame, min_area: float, start_id: int) -> List[TopologyError]:
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
                            errors.append(TopologyError(
                                id=curr_id,
                                rule_code=rule.code,
                                rule_name=rule.name,
                                feature_ids=[idx_i, idx_j],
                                geometry=inter,
                                description=f"Polygons #{idx_i} and #{idx_j} overlap by area {inter.area:.4g}.",
                                severity="error",
                                can_fix=True
                            ))
                            curr_id += 1
                    except Exception:
                        pass
        return errors

    @classmethod
    def _check_polygon_slivers(cls, gdf: gpd.GeoDataFrame, min_area: float, thinness_threshold: float, start_id: int) -> List[TopologyError]:
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
                    reason = f"Micro-area ({area:.4g})" if is_micro else f"Thinness ratio ({thinness:.4f} < {thinness_threshold})"
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
    def _check_polygon_gaps(cls, gdf: gpd.GeoDataFrame, max_gap_area: float, start_id: int) -> List[TopologyError]:
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
                            errors.append(TopologyError(
                                id=curr_id,
                                rule_code=rule.code,
                                rule_name=rule.name,
                                feature_ids=[],
                                geometry=hole,
                                description=f"Enclosed gap / void found between adjacent polygons (Area: {hole.area:.4g}).",
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

        # 1. Clean empty / null geometries
        if TopologyRuleCode.GEOM_EMPTY_NULL in report.rule_counts:
            orig_len = len(res_gdf)
            res_gdf = res_gdf[res_gdf.geometry.notna() & ~res_gdf.geometry.is_empty].copy()
            total_fixed += (orig_len - len(res_gdf))

        # 2. Repair OGC valid
        if TopologyRuleCode.POLYGON_OGC_VALID in report.rule_counts or TopologyRuleCode.LINE_SELF_INTERSECT in report.rule_counts:
            invalid_mask = ~res_gdf.geometry.is_valid
            count_invalid = int(invalid_mask.sum())
            if count_invalid > 0:
                res_gdf.loc[invalid_mask, "geometry"] = res_gdf.loc[invalid_mask, "geometry"].apply(
                    lambda g: shapely.make_valid(g) if g is not None and not g.is_empty else g
                )
                total_fixed += count_invalid

        # 3. Clean duplicate vertices
        if (TopologyRuleCode.POLYGON_DUPLICATE_VERTICES in report.rule_counts or
                TopologyRuleCode.LINE_DUPLICATE_NODES in report.rule_counts):
            fixed_dups = 0
            for idx in res_gdf.index:
                geom = res_gdf.geometry.loc[idx]
                if geom is not None and not geom.is_empty:
                    cleaned = shapely.simplify(geom, tolerance=0)
                    if cleaned is not None and not cleaned.is_empty:
                        res_gdf.loc[idx, "geometry"] = cleaned
                        fixed_dups += 1
            if fixed_dups > 0:
                total_fixed += min(fixed_dups, report.rule_counts.get(TopologyRuleCode.POLYGON_DUPLICATE_VERTICES, 0) +
                                   report.rule_counts.get(TopologyRuleCode.LINE_DUPLICATE_NODES, 0))

        # 4. Repair Point Duplicates
        if TopologyRuleCode.POINT_DUPLICATES in report.rule_counts:
            orig_cnt = len(res_gdf)
            # Drop identical geometries
            res_gdf = res_gdf.drop_duplicates(subset=["geometry"]).copy()
            total_fixed += (orig_cnt - len(res_gdf))

        # 5. Resolve Polygon Overlaps (clip overlapping regions)
        if TopologyRuleCode.POLYGON_OVERLAPS in report.rule_counts:
            fixed_overlaps = 0
            indices = list(res_gdf.index)
            for i in range(len(indices)):
                for j in range(i + 1, len(indices)):
                    idx_i, idx_j = indices[i], indices[j]
                    geom_i = res_gdf.geometry.loc[idx_i]
                    geom_j = res_gdf.geometry.loc[idx_j]
                    if geom_i is not None and geom_j is not None and geom_i.intersects(geom_j):
                        inter = geom_i.intersection(geom_j)
                        if inter.area > 1e-9:
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

        elif rule in (TopologyRuleCode.POLYGON_OGC_VALID, TopologyRuleCode.LINE_SELF_INTERSECT):
            geom = res_gdf.geometry.loc[feat_id]
            if geom is not None and not geom.is_empty:
                res_gdf.loc[feat_id, "geometry"] = shapely.make_valid(geom)
                return res_gdf, True

        elif rule in (TopologyRuleCode.POLYGON_DUPLICATE_VERTICES, TopologyRuleCode.LINE_DUPLICATE_NODES):
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
