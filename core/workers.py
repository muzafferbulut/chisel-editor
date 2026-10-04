from PyQt6.QtCore import QThread, pyqtSignal
from handlers.factory import HandlerFactory
from handlers.spatial import MultipleLayersError
from core.spatial_ops import SpatialOps
import os
import geopandas as gpd


class FileLoadWorker(QThread):
    finished = pyqtSignal(str, str, bool, str)
    multiple_layers_detected = pyqtSignal(str, list)

    def __init__(self, file_path: str, **kwargs):
        super().__init__()
        self.file_path = file_path
        self.kwargs = kwargs

    def run(self):
        try:
            handler = HandlerFactory.get_handler(self.file_path)
            content = handler.read(self.file_path, **self.kwargs)
            self.finished.emit(self.file_path, content, handler.is_spatial, "")
        except MultipleLayersError as mle:
            self.multiple_layers_detected.emit(self.file_path, mle.layers)
        except Exception as e:
            self.finished.emit(self.file_path, "", False, str(e))


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