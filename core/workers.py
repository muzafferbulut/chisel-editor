import io
import os
import requests
from PyQt6.QtCore import QThread, pyqtSignal
from handlers.factory import HandlerFactory
from handlers.spatial import MultipleLayersError
from core.spatial_ops import SpatialOps
import geopandas as gpd


class FileLoadWorker(QThread):
    finished = pyqtSignal(str, str, bool, object, str)  # (file_path, content, is_spatial, gdf, error)
    multiple_layers_detected = pyqtSignal(str, list)

    def __init__(self, file_path: str, **kwargs):
        super().__init__()
        self.file_path = file_path
        self.kwargs = kwargs

    def run(self):
        try:
            handler = HandlerFactory.get_handler(self.file_path)
            if handler.is_spatial and hasattr(handler, 'read_gdf'):
                gdf = handler.read_gdf(self.file_path, **self.kwargs)
                clean_gdf = SpatialOps.sanitize_gdf_for_json(gdf)
                # Performance Optimization: Avoid serializing 100k+ rows to JSON
                if len(clean_gdf) <= 3000:
                    content = clean_gdf.to_json()
                else:
                    content = SpatialOps.to_geojson_str(clean_gdf.iloc[:50])
                self.finished.emit(self.file_path, content, True, clean_gdf, "")
            else:
                content = handler.read(self.file_path, **self.kwargs)
                self.finished.emit(self.file_path, content, False, None, "")
        except MultipleLayersError as mle:
            self.multiple_layers_detected.emit(self.file_path, mle.layers)
        except Exception as e:
            self.finished.emit(self.file_path, "", False, None, str(e))


class ViewportQueryWorker(QThread):
    finished = pyqtSignal(str, str, str, str)  # (layer_id, layer_name, geojson_str, geom_type)

    def __init__(self, layer_id: str, layer_name: str, gdf: gpd.GeoDataFrame, geom_type: str, minx: float, miny: float, maxx: float, maxy: float, zoom: int):
        super().__init__()
        self.layer_id = layer_id
        self.layer_name = layer_name
        self.gdf = gdf
        self.geom_type = geom_type
        self.minx = minx
        self.miny = miny
        self.maxx = maxx
        self.maxy = maxy
        self.zoom = zoom

    def run(self):
        try:
            sub_gdf = SpatialOps.query_viewport_and_lod(self.gdf, self.minx, self.miny, self.maxx, self.maxy, self.zoom)
            raw_geojson = SpatialOps.to_geojson_str(sub_gdf)
            self.finished.emit(self.layer_id, self.layer_name, raw_geojson, self.geom_type)
        except Exception:
            pass


class WFSWorker(QThread):
    finished = pyqtSignal(str, object, str)  # (layer_name, GeoDataFrame, error)

    def __init__(self, url: str, type_name: str = "", limit: int = 500):
        super().__init__()
        self.url = url
        self.type_name = type_name
        self.limit = limit

    def run(self):
        try:
            req_url = self.url
            if self.type_name and "GetFeature" not in req_url:
                delim = "&" if "?" in req_url else "?"
                req_url = f"{req_url}{delim}service=WFS&version=2.0.0&request=GetFeature&typeNames={self.type_name}&outputFormat=application/json&count={self.limit}"

            resp = requests.get(req_url, timeout=25, headers={"User-Agent": "ChiselEditor/1.0"})
            resp.raise_for_status()

            text = resp.text
            gdf = gpd.read_file(io.StringIO(text))
            if gdf.crs is None:
                gdf.set_crs("EPSG:4326", inplace=True)

            layer_name = self.type_name or "WFS_Layer"
            self.finished.emit(layer_name, gdf, "")
        except Exception as e:
            self.finished.emit("", None, str(e))


class SpatialOpWorker(QThread):
    finished = pyqtSignal(str, object, str)

    def __init__(self, op_name: str, gdf: gpd.GeoDataFrame, **params):
        super().__init__()
        self.op_name = op_name
        self.gdf = gdf
        self.params = params

    def run(self):
        try:
            if self.op_name == "reproject":
                target_crs = self.params.get("target_crs")
                res = SpatialOps.reproject_gdf(self.gdf, target_crs)
                self.finished.emit(self.op_name, res, "")

            elif self.op_name == "set_crs":
                new_crs = self.params.get("new_crs")
                res = SpatialOps.set_crs_gdf(self.gdf, new_crs)
                self.finished.emit(self.op_name, res, "")

            elif self.op_name == "validate_repair":
                res, fixed_count = SpatialOps.validate_and_repair(self.gdf)
                self.finished.emit(self.op_name, (res, fixed_count), "")

            elif self.op_name == "simplify":
                tolerance = self.params.get("tolerance", 0.001)
                preserve_topo = self.params.get("preserve_topology", True)
                res, orig_v, simp_v = SpatialOps.simplify_geometries(self.gdf, tolerance, preserve_topo)
                self.finished.emit(self.op_name, (res, orig_v, simp_v), "")

            elif self.op_name == "buffer":
                dist = self.params.get("distance", 100)
                unit = self.params.get("unit", "meters")
                res = SpatialOps.buffer_geometries(self.gdf, dist, unit)
                self.finished.emit(self.op_name, res, "")

            elif self.op_name == "dissolve":
                by_col = self.params.get("by_column", None)
                res = SpatialOps.dissolve_geometries(self.gdf, by_col)
                self.finished.emit(self.op_name, res, "")

            elif self.op_name == "calc_geometry":
                res = SpatialOps.calculate_geometry_attributes(self.gdf)
                self.finished.emit(self.op_name, res, "")

            elif self.op_name == "convex_hull":
                per_feature = self.params.get("per_feature", False)
                res = SpatialOps.calculate_convex_hull(self.gdf, per_feature)
                self.finished.emit(self.op_name, res, "")

            elif self.op_name == "centroids":
                res = SpatialOps.calculate_centroids(self.gdf)
                self.finished.emit(self.op_name, res, "")

            elif self.op_name == "bounding_boxes":
                res = SpatialOps.calculate_bounding_boxes(self.gdf)
                self.finished.emit(self.op_name, res, "")

            elif self.op_name == "export":
                target_path = self.params.get("target_path")
                success = SpatialOps.export_file(self.gdf, target_path)
                self.finished.emit(self.op_name, success, "")

            else:
                self.finished.emit(self.op_name, None, f"Unknown operation: {self.op_name}")

        except Exception as e:
            self.finished.emit(self.op_name, None, str(e))