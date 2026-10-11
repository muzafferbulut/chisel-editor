import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableView,
    QLineEdit, QPushButton, QLabel, QHeaderView, QFileDialog, QMessageBox,
    QDialog, QComboBox, QFrame, QTextEdit
)
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt, pyqtSignal, QAbstractTableModel, QModelIndex, QSortFilterProxyModel, QItemSelectionModel, QItemSelection, QSize
import geopandas as gpd
import pandas as pd
from core.spatial_ops import SpatialOps


class AttributeTableProxyModel(QSortFilterProxyModel):
    """
    High-performance proxy model that handles fast text search filtering
    and optional 'Show only selected features' mode like QGIS.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._only_selected = False
        self._selected_source_rows = set()

    def set_only_selected(self, enabled: bool, selected_rows: set):
        self._only_selected = enabled
        self._selected_source_rows = set(selected_rows)
        self.invalidateFilter()

    def is_only_selected(self) -> bool:
        return self._only_selected

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex):
        if self._only_selected and source_row not in self._selected_source_rows:
            return False
        return super().filterAcceptsRow(source_row, source_parent)


class AddFieldDialog(QDialog):
    """QGIS-style dialog for adding a new attribute field/column to the layer."""

    def __init__(self, existing_columns: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Yeni Alan / Sütun Ekle")
        self.setFixedSize(320, 220)
        self.existing_columns = [str(c).lower() for c in existing_columns]
        self.field_name = ""
        self.field_type = "str"
        self.default_val = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        layout.addWidget(QLabel("<b>Sütun Adı:</b>"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("örn: mahalle_adi, nufus, durum")
        layout.addWidget(self.name_edit)

        layout.addWidget(QLabel("<b>Veri Türü:</b>"))
        self.type_combo = QComboBox()
        self.type_combo.addItem("Metin (String / Yazı)", "str")
        self.type_combo.addItem("Tamsayı (Integer)", "int")
        self.type_combo.addItem("Ondalık Sayı (Float / Double)", "float")
        layout.addWidget(self.type_combo)

        layout.addWidget(QLabel("<b>Varsayılan Değer (İsteğe bağlı):</b>"))
        self.default_edit = QLineEdit()
        self.default_edit.setPlaceholderText("Boş bırakılabilir")
        layout.addWidget(self.default_edit)

        btn_box = QHBoxLayout()
        btn_cancel = QPushButton("İptal")
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("Ekle")
        btn_ok.setStyleSheet("background-color: #007acc; color: white; font-weight: bold; border-radius: 4px; padding: 4px 14px;")
        btn_ok.clicked.connect(self._on_accept)
        btn_box.addStretch()
        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_ok)
        layout.addLayout(btn_box)

    def _on_accept(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Geçersiz Ad", "Lütfen bir sütun adı girin.")
            return
        if name.lower() in self.existing_columns:
            QMessageBox.warning(self, "Mevcut Sütun", f"'{name}' isimli bir sütun zaten mevcut.")
            return

        self.field_name = name
        self.field_type = self.type_combo.currentData()
        raw_val = self.default_edit.text().strip()

        if raw_val:
            try:
                if self.field_type == "int":
                    self.default_val = int(raw_val)
                elif self.field_type == "float":
                    self.default_val = float(raw_val.replace(",", "."))
                else:
                    self.default_val = raw_val
            except ValueError:
                QMessageBox.warning(self, "Tür Uyuşmazlığı", "Varsayılan değer seçilen türe dönüştürülemedi.")
                return
        else:
            if self.field_type == "int":
                self.default_val = 0
            elif self.field_type == "float":
                self.default_val = 0.0
            else:
                self.default_val = ""

        self.accept()


class EditGeometryDialog(QDialog):
    """QGIS-style dialog to view and update feature geometry via WKT and coordinates."""
    def __init__(self, geometry, geom_type: str, crs_str: str = "EPSG:4326", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Geometriyi Düzenle (WKT & Koordinatlar)")
        self.setMinimumSize(480, 360)
        self.original_geom = geometry
        self.geom_type = geom_type
        self.crs_str = crs_str
        self.updated_geom = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        info_lbl = QLabel(f"<b>Geometri Türü:</b> {self.geom_type.capitalize()} &nbsp;|&nbsp; <b>Projeksiyon:</b> {self.crs_str}")
        layout.addWidget(info_lbl)

        layout.addWidget(QLabel("<b>WKT (Well-Known Text) Formatında Geometri:</b>"))
        self.wkt_edit = QTextEdit()
        self.wkt_edit.setStyleSheet("font-family: Consolas, monospace; font-size: 12px;")
        if self.original_geom is not None and hasattr(self.original_geom, 'wkt'):
            self.wkt_edit.setPlainText(self.original_geom.wkt)
        layout.addWidget(self.wkt_edit)

        tip_lbl = QLabel("<small style='color:#858585;'>💡 Örnekler: POINT(29.0 41.0) | LINESTRING(29 41, 30 41) | POLYGON((29 41, 30 41, 30 42, 29 41))</small>")
        layout.addWidget(tip_lbl)

        btn_box = QHBoxLayout()
        btn_cancel = QPushButton("İptal")
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("Kaydet ve Güncelle")
        btn_ok.setStyleSheet("background-color: #007acc; color: white; font-weight: bold; border-radius: 4px; padding: 5px 14px;")
        btn_ok.clicked.connect(self._on_save)
        btn_box.addStretch()
        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_ok)
        layout.addLayout(btn_box)

    def _on_save(self):
        text = self.wkt_edit.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Hata", "Lütfen geçerli bir WKT geometrisi girin.")
            return
        try:
            import shapely.wkt
            geom = shapely.wkt.loads(text)
            if not geom.is_valid:
                from shapely.validation import make_valid
                geom = make_valid(geom)
            self.updated_geom = geom
            self.accept()
        except Exception as e:
            QMessageBox.warning(self, "Geçersiz WKT", f"WKT biçimi ayrıştırılamadı:\n{e}")


class GeoDataFrameTableModel(QAbstractTableModel):
    """
    High-performance virtual table model for GeoDataFrame / DataFrame.
    Renders 100,000+ rows instantly with 0ms overhead by referencing memory directly.
    Supports inline cell editing and dynamic data changes.
    """
    data_changed_signal = pyqtSignal()

    def __init__(self, gdf: gpd.GeoDataFrame = None):
        super().__init__()
        self._gdf = gdf if gdf is not None and not gdf.empty else gpd.GeoDataFrame()
        self._columns = []
        self._update_columns()

    def _update_columns(self):
        if self._gdf is not None and not self._gdf.empty:
            geom_name = getattr(self._gdf, 'geometry', None)
            self._geom_col = geom_name.name if geom_name is not None else None
            self._columns = [c for c in self._gdf.columns if c != self._geom_col]
            if self._geom_col and self._geom_col in self._gdf.columns:
                self._columns.append(self._geom_col)
        else:
            self._geom_col = None
            self._columns = []

    def set_data(self, gdf: gpd.GeoDataFrame):
        self.beginResetModel()
        self._gdf = gdf if gdf is not None and not gdf.empty else gpd.GeoDataFrame()
        self._update_columns()
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return len(self._gdf) if self._gdf is not None and not self._gdf.empty else 0

    def columnCount(self, parent=QModelIndex()):
        return len(self._columns)

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or self._gdf is None or self._gdf.empty:
            return None

        row = index.row()
        col_idx = index.column()
        if row >= len(self._gdf) or col_idx >= len(self._columns):
            return None

        col_name = self._columns[col_idx]
        val = self._gdf[col_name].iat[row]

        if role == Qt.ItemDataRole.DisplayRole:
            if col_name == self._geom_col:
                if val is not None and hasattr(val, 'geom_type'):
                    return f"<{val.geom_type}>"
                return "<Empty>"
            if pd.isna(val):
                return ""
            if isinstance(val, float):
                return f"{val:.4f}" if abs(val) < 10000 else f"{val:,.2f}"
            return str(val)

        elif role == Qt.ItemDataRole.EditRole:
            if col_name == self._geom_col:
                if val is not None and hasattr(val, 'wkt'):
                    return val.wkt
                return ""
            if pd.isna(val):
                return ""
            return str(val)

        elif role == Qt.ItemDataRole.TextAlignmentRole:
            if isinstance(val, (int, float)) and not pd.isna(val):
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        return None

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if not index.isValid() or role != Qt.ItemDataRole.EditRole or self._gdf is None:
            return False

        row = index.row()
        col_idx = index.column()
        if row >= len(self._gdf) or col_idx >= len(self._columns):
            return False

        col_name = self._columns[col_idx]

        try:
            if col_name == self._geom_col:
                import shapely.wkt
                val_str = str(value).strip()
                if not val_str:
                    return False
                new_geom = shapely.wkt.loads(val_str)
                if not new_geom.is_valid:
                    from shapely.validation import make_valid
                    new_geom = make_valid(new_geom)
                self._gdf.at[self._gdf.index[row], col_name] = new_geom
            else:
                curr_dtype = self._gdf[col_name].dtype
                str_val = str(value).strip()

                if str_val == "" or str_val.lower() in ("nan", "none", "null"):
                    if pd.api.types.is_numeric_dtype(curr_dtype):
                        converted = None if pd.api.types.is_integer_dtype(curr_dtype) else float('nan')
                    else:
                        converted = None
                elif pd.api.types.is_integer_dtype(curr_dtype):
                    converted = int(str_val)
                elif pd.api.types.is_float_dtype(curr_dtype):
                    converted = float(str_val.replace(',', '.'))
                elif pd.api.types.is_bool_dtype(curr_dtype):
                    converted = str_val.lower() in ('true', '1', 't', 'evet', 'doğru', 'yes')
                else:
                    converted = str_val

                self._gdf.at[self._gdf.index[row], col_name] = converted

            self.dataChanged.emit(index, index, [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole])
            self.data_changed_signal.emit()
            return True
        except Exception as e:
            print(f"Error setting cell data: {e}")
            return False

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None

        if orientation == Qt.Orientation.Horizontal:
            if section < len(self._columns):
                return str(self._columns[section])
        elif orientation == Qt.Orientation.Vertical:
            return str(section + 1)
        return None

    def sort(self, column, order=Qt.SortOrder.AscendingOrder):
        if self._gdf is None or self._gdf.empty or column >= len(self._columns):
            return
        self.layoutAboutToBeChanged.emit()
        col_name = self._columns[column]
        ascending = (order == Qt.SortOrder.AscendingOrder)
        try:
            self._gdf = self._gdf.sort_values(by=col_name, ascending=ascending).reset_index(drop=True)
        except Exception:
            pass
        self.layoutChanged.emit()


class AttributeTableWidget(QWidget):
    feature_selected = pyqtSignal(int)
    features_selected = pyqtSignal(list)
    delete_requested = pyqtSignal(list)
    data_modified = pyqtSignal(object)
    zoom_to_selected_requested = pyqtSignal()
    close_requested = pyqtSignal()
    layer_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_gdf = None
        self._block_selection_signals = False
        self._block_layer_signals = False
        self._cached_selected_rows = set()
        self._tool_buttons = {}
        self._init_ui()
        self.apply_theme()

    def _create_vsep(self) -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        sep.setStyleSheet("background-color: rgba(128, 128, 128, 0.25); width: 1px; margin: 3px 2px; border: none;")
        return sep

    def _get_icon(self, icon_name: str, theme_name: str = None) -> QIcon:
        try:
            from ui.icons import get_lucide_icon
            icon = get_lucide_icon(icon_name, theme_name=theme_name)
            if not icon.isNull():
                return icon
        except Exception:
            pass
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        icon_path = os.path.join(base_dir, "resources", "icons", f"{icon_name}.png")
        if os.path.isfile(icon_path):
            return QIcon(icon_path)
        return QIcon()

    def _create_tool_btn(self, icon_name: str, fallback_text: str, tooltip: str, callback=None, checkable: bool = False, obj_name: str = "") -> QPushButton:
        btn = QPushButton()
        self._tool_buttons[btn] = icon_name
        icon = self._get_icon(icon_name)
        if not icon.isNull():
            btn.setIcon(icon)
            btn.setIconSize(QSize(16, 16))
        else:
            btn.setText(fallback_text)

        btn.setToolTip(tooltip)
        btn.setFixedSize(28, 28)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if obj_name:
            btn.setObjectName(obj_name)
        if checkable:
            btn.setCheckable(True)
        if callback:
            if checkable:
                btn.toggled.connect(callback)
            else:
                btn.clicked.connect(callback)
        return btn

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        # Toolbar Container (Theme-adaptive styling)
        self.toolbar_container = QWidget()
        self.toolbar_container.setObjectName("AttributeTableToolbar")
        toolbar_container = self.toolbar_container
        toolbar_container.setStyleSheet(
            "#AttributeTableToolbar QPushButton {"
            "  background-color: transparent;"
            "  border: 1px solid transparent;"
            "  border-radius: 4px;"
            "  padding: 0px;"
            "  min-width: 28px;"
            "  max-width: 28px;"
            "  min-height: 28px;"
            "  max-height: 28px;"
            "}"
            "#AttributeTableToolbar QPushButton:hover {"
            "  background-color: rgba(128, 128, 128, 0.2);"
            "  border: 1px solid rgba(128, 128, 128, 0.35);"
            "}"
            "#AttributeTableToolbar QPushButton:pressed {"
            "  background-color: rgba(128, 128, 128, 0.35);"
            "}"
            "#AttributeTableToolbar QPushButton:checked {"
            "  background-color: rgba(0, 122, 204, 0.25);"
            "  border: 1px solid #007acc;"
            "}"
            "#AttributeTableToolbar QPushButton:disabled {"
            "  background-color: transparent;"
            "  border: 1px solid transparent;"
            "}"
            "#AttributeTableToolbar QPushButton#btn_del:hover:enabled {"
            "  background-color: rgba(239, 68, 68, 0.2);"
            "  border: 1px solid rgba(239, 68, 68, 0.4);"
            "}"
            "#AttributeTableToolbar QPushButton#btn_close {"
            "  border: 1px solid transparent;"
            "  font-weight: bold;"
            "  font-size: 13px;"
            "}"
            "#AttributeTableToolbar QPushButton#btn_close:hover {"
            "  background-color: rgba(239, 68, 68, 0.2);"
            "  border: 1px solid rgba(239, 68, 68, 0.4);"
            "}"
        )
        toolbar = QHBoxLayout(toolbar_container)
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.setSpacing(4)

        # Active Layer Selector Dropdown
        self.layer_combo = QComboBox()
        self.layer_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.layer_combo.setToolTip("Aktif Katmanı Değiştir")
        self.layer_combo.currentIndexChanged.connect(self._on_layer_combo_changed)
        toolbar.addWidget(self.layer_combo)

        toolbar.addWidget(self._create_vsep())

        # Quick Search Box
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Tabloda filtrele...")
        self.search_input.setMaximumWidth(200)
        self.search_input.setClearButtonEnabled(True)
        self.search_action = self.search_input.addAction(
            self._get_icon("search"), QLineEdit.ActionPosition.LeadingPosition
        )
        self.search_input.textChanged.connect(self._filter_table)
        toolbar.addWidget(self.search_input)

        self.stats_label = QLabel("0 özellik")
        self.stats_label.setStyleSheet("color: #858585; font-size: 11px; padding: 0 4px;")
        toolbar.addWidget(self.stats_label)

        toolbar.addWidget(self._create_vsep())

        # QGIS Selection Tools
        self.btn_zoom_selected = self._create_tool_btn("zoom_to_selected", "🔍", "Haritada Seçilenlere Yakınlaş", self._zoom_to_selected)
        self.btn_zoom_selected.setEnabled(False)
        toolbar.addWidget(self.btn_zoom_selected)

        self.btn_select_all = self._create_tool_btn("select_all", "🔲", "Tümünü Seç (Ctrl+A)", self._select_all)
        toolbar.addWidget(self.btn_select_all)

        self.btn_invert_sel = self._create_tool_btn("invert_selection", "🔄", "Seçimi Tersine Çevir", self._invert_selection)
        toolbar.addWidget(self.btn_invert_sel)

        self.btn_clear_sel = self._create_tool_btn("clear_selection", "✖", "Seçimi Temizle", self._clear_selection)
        toolbar.addWidget(self.btn_clear_sel)

        self.btn_show_selected = self._create_tool_btn("show_selected", "🎯", "Yalnızca Seçilenleri Göster / Tümünü Göster", self._toggle_show_selected, checkable=True)
        toolbar.addWidget(self.btn_show_selected)

        toolbar.addWidget(self._create_vsep())

        # QGIS Data / Calculation Tools
        self.btn_add_row = self._create_tool_btn("add_row", "+R", "Yeni Kayıt / Satır Ekle", self._add_row)
        toolbar.addWidget(self.btn_add_row)

        self.btn_add_col = self._create_tool_btn("add_field", "+A", "Yeni Sütun / Alan Ekle", self._add_field)
        toolbar.addWidget(self.btn_add_col)

        self.btn_edit_geom = self._create_tool_btn("edit_geometry", "✏️", "Seçili Geometriyi Düzenle (WKT & Koordinatlar)", self._edit_selected_geometry)
        self.btn_edit_geom.setEnabled(False)
        toolbar.addWidget(self.btn_edit_geom)

        self.btn_calc_geom = self._create_tool_btn("calc_geom", "📐", "Geometri Hesapla (Alan, Uzunluk, Koordinatlar)", self._calculate_geometry)
        toolbar.addWidget(self.btn_calc_geom)

        self.btn_stats = self._create_tool_btn("statistics", "📊", "Sütun İstatistikleri (Tüm katman için)", self._show_column_statistics)
        toolbar.addWidget(self.btn_stats)

        self.btn_del_selected = self._create_tool_btn("delete_selected", "🗑️", "Seçili Kayıtları Sil (Del)", self._delete_selected_rows, obj_name="btn_del")
        self.btn_del_selected.setEnabled(False)
        toolbar.addWidget(self.btn_del_selected)

        toolbar.addWidget(self._create_vsep())

        # Export & Close
        self.btn_export_csv = self._create_tool_btn("export_csv", "💾", "Öznitelik Tablosunu CSV Olarak Dışa Aktar", self._export_csv)
        toolbar.addWidget(self.btn_export_csv)

        toolbar.addStretch()

        self.btn_close = self._create_tool_btn("close", "✕", "Öznitelik Tablosunu Kapat (F6)", self.close_requested.emit, obj_name="btn_close")
        toolbar.addWidget(self.btn_close)

        layout.addWidget(toolbar_container)

        # Table View with Virtual Model
        self.table_view = QTableView()
        self.table_view.setAlternatingRowColors(True)
        self.table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table_view.setSelectionMode(QTableView.SelectionMode.ExtendedSelection)
        self.table_view.setSortingEnabled(True)
        self.table_view.horizontalHeader().setStretchLastSection(False)
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table_view.verticalHeader().setDefaultSectionSize(25)

        self.source_model = GeoDataFrameTableModel()
        self.proxy_model = AttributeTableProxyModel(self)
        self.proxy_model.setSourceModel(self.source_model)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxy_model.setFilterKeyColumn(-1)

        self.table_view.setModel(self.proxy_model)
        self.table_view.selectionModel().selectionChanged.connect(self._on_selection_changed)
        self.table_view.doubleClicked.connect(self._on_table_double_clicked)
        self.source_model.data_changed_signal.connect(self._on_cell_data_changed)

        layout.addWidget(self.table_view)
        self.apply_theme()

    def apply_theme(self, theme_name: str = None):
        """Applies dynamic theme styling to toolbar, table view, headers, and search box."""
        from core.theme import ThemeManager
        tokens = ThemeManager.get_tokens(theme_name)
        bg = tokens.get("panel_bg", "#ffffff")
        toolbar_bg = tokens.get("toolbar_bg", "#f8fafc")
        text = tokens.get("text", "#1e293b")
        text_muted = tokens.get("text_muted", "#64748b")
        border = tokens.get("border", "#e2e8f0")
        hover = tokens.get("hover", "rgba(128,128,128,0.18)")
        active = tokens.get("active", "rgba(128,128,128,0.30)")
        accent = tokens.get("accent", "#0284c7")
        grid = tokens.get("grid_line", "#e2e8f0")
        is_dark = ThemeManager.is_dark(theme_name)
        alt_bg = tokens.get("hover", "#f8fafc") if not is_dark else tokens.get("active", "#252526")

        tb_qss = f"""
            #AttributeTableToolbar QPushButton {{
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: 4px;
                padding: 0px;
                min-width: 28px;
                max-width: 28px;
                min-height: 28px;
                max-height: 28px;
                color: {text};
            }}
            #AttributeTableToolbar QPushButton:hover {{
                background-color: {hover};
                border: 1px solid {border};
            }}
            #AttributeTableToolbar QPushButton:pressed {{
                background-color: {active};
            }}
            #AttributeTableToolbar QPushButton:checked {{
                background-color: {active};
                border: 1px solid {accent};
            }}
            #AttributeTableToolbar QPushButton:disabled {{
                background-color: transparent;
                border: 1px solid transparent;
                color: {text_muted};
            }}
            #AttributeTableToolbar QPushButton#btn_del:hover:enabled {{
                background-color: rgba(239, 68, 68, 0.2);
                border: 1px solid rgba(239, 68, 68, 0.4);
            }}
            #AttributeTableToolbar QPushButton#btn_close:hover {{
                background-color: rgba(239, 68, 68, 0.2);
                border: 1px solid rgba(239, 68, 68, 0.4);
            }}
        """
        self.toolbar_container.setStyleSheet(tb_qss)

        # Update all toolbar button icons to match current theme colors
        if hasattr(self, '_tool_buttons'):
            for btn, icon_name in self._tool_buttons.items():
                ico = self._get_icon(icon_name, theme_name=theme_name)
                if not ico.isNull():
                    btn.setIcon(ico)
                    btn.setIconSize(QSize(16, 16))

        if hasattr(self, 'search_action') and self.search_action:
            self.search_action.setIcon(self._get_icon("search", theme_name=theme_name))

        table_qss = f"""
            QTableView {{
                background-color: {bg};
                color: {text};
                gridline-color: {grid};
                border: 1px solid {border};
                selection-background-color: {accent};
                selection-color: #ffffff;
                font-size: 12px;
            }}
            QTableView::item:alternate {{
                background-color: {alt_bg};
            }}
            QTableView::item:selected {{
                background-color: {accent};
                color: #ffffff;
            }}
            QHeaderView::section {{
                background-color: {toolbar_bg};
                color: {text_muted};
                border: 1px solid {border};
                padding: 4px 6px;
                font-weight: 600;
                font-size: 11px;
            }}
        """
        self.table_view.setStyleSheet(table_qss)
        self.search_input.setStyleSheet(
            f"QLineEdit {{ background-color: {bg}; color: {text}; border: 1px solid {border}; "
            f"border-radius: 4px; padding: 2px 6px; font-size: 11px; }} "
            f"QLineEdit:focus {{ border: 1px solid {accent}; }}"
        )
        self.layer_combo.setStyleSheet(
            f"QComboBox {{ background-color: {bg}; color: {text}; border: 1px solid {border}; "
            f"border-radius: 4px; padding: 2px 6px; font-size: 11px; font-weight: 600; min-height: 22px; }} "
            f"QComboBox:hover {{ border: 1px solid {accent}; }} "
            f"QComboBox::drop-down {{ border: none; width: 14px; }} "
            f"QComboBox QAbstractItemView {{ background-color: {bg}; color: {text}; selection-background-color: {accent}; selection-color: #ffffff; border: 1px solid {border}; padding: 3px; }}"
        )
        self.stats_label.setStyleSheet(f"color: {text_muted}; font-size: 11px;")

    def update_layer_list(self, layers: list, active_id: str):
        """Updates the layer selector dropdown with list of (layer_id, name, geom_type)."""
        self._block_layer_signals = True
        self.layer_combo.clear()
        if not layers:
            self.layer_combo.addItem("Katman Yok", "")
            self.layer_combo.setEnabled(False)
        elif len(layers) == 1:
            lid, name, gtype = layers[0]
            icon_str = "📍" if gtype == "point" else ("〰️" if gtype == "line" else ("📐" if gtype == "polygon" else "🔶"))
            self.layer_combo.addItem(f"{icon_str} {name}", lid)
            self.layer_combo.setEnabled(False)
        else:
            self.layer_combo.setEnabled(True)
            active_idx = 0
            for i, (lid, name, gtype) in enumerate(layers):
                icon_str = "📍" if gtype == "point" else ("〰️" if gtype == "line" else ("📐" if gtype == "polygon" else "🔶"))
                self.layer_combo.addItem(f"{icon_str} {name}", lid)
                if lid == active_id:
                    active_idx = i
            self.layer_combo.setCurrentIndex(active_idx)
        self._block_layer_signals = False

    def _on_layer_combo_changed(self, index: int):
        if self._block_layer_signals or index < 0:
            return
        layer_id = self.layer_combo.itemData(index)
        if layer_id:
            self.layer_changed.emit(layer_id)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            if self.btn_del_selected.isEnabled():
                self._delete_selected_rows()
                return
        super().keyPressEvent(event)

    def load_data(self, gdf: gpd.GeoDataFrame, layer_name: str = None, layer_id: str = None):
        self._current_gdf = gdf
        self.btn_show_selected.blockSignals(True)
        self.btn_show_selected.setChecked(False)
        self.btn_show_selected.blockSignals(False)
        self.proxy_model.set_only_selected(False, set())

        self.source_model.set_data(gdf)

        count = len(gdf) if gdf is not None and not gdf.empty else 0
        self.stats_label.setText(f"{count:,} özellik")
        self.btn_del_selected.setEnabled(False)
        self.btn_del_selected.setToolTip("Seçili Kayıtları Sil (Del)")
        self.btn_zoom_selected.setEnabled(False)
        self.btn_zoom_selected.setToolTip("Haritada Seçilenlere Yakınlaş")
        self.btn_stats.setToolTip("Sütun İstatistikleri (Tüm katman için)")
        self.btn_edit_geom.setEnabled(False)
        self.btn_add_row.setEnabled(gdf is not None)

        header = self.table_view.horizontalHeader()
        header.setDefaultSectionSize(120)
        for col in range(min(5, self.source_model.columnCount())):
            header.resizeSection(col, 130)

    def _filter_table(self, text: str):
        self.proxy_model.setFilterFixedString(text)
        self._update_stats_label()

    def _update_stats_label(self):
        visible = self.proxy_model.rowCount()
        total = self.source_model.rowCount()
        if self.proxy_model.is_only_selected() or bool(self.search_input.text().strip()):
            self.stats_label.setText(f"{visible:,} / {total:,} özellik")
        else:
            self.stats_label.setText(f"{total:,} özellik")

    def _zoom_to_selected(self):
        self.zoom_to_selected_requested.emit()

    def _select_all(self):
        self.table_view.selectAll()

    def _invert_selection(self):
        sel_model = self.table_view.selectionModel()
        total_rows = self.proxy_model.rowCount()
        col_count = self.proxy_model.columnCount()
        if total_rows == 0 or col_count == 0:
            return
        selection = QItemSelection(
            self.proxy_model.index(0, 0),
            self.proxy_model.index(total_rows - 1, col_count - 1)
        )
        sel_model.select(selection, QItemSelectionModel.SelectionFlag.Toggle | QItemSelectionModel.SelectionFlag.Rows)

    def _clear_selection(self):
        self.table_view.selectionModel().clearSelection()

    def _toggle_show_selected(self, checked: bool):
        if checked:
            indexes = self.table_view.selectionModel().selectedRows()
            src_rows = set()
            for p_idx in indexes:
                s_idx = self.proxy_model.mapToSource(p_idx)
                if s_idx.isValid():
                    src_rows.add(s_idx.row())
            if not src_rows:
                self.btn_show_selected.blockSignals(True)
                self.btn_show_selected.setChecked(False)
                self.btn_show_selected.blockSignals(False)
                QMessageBox.information(
                    self, "Seçim Yok",
                    "Yalnızca seçilenleri göstermek için önce tablodan veya haritadan en az bir özellik seçmelisiniz."
                )
                return
            self._cached_selected_rows = src_rows
            self.proxy_model.set_only_selected(True, src_rows)
            self.table_view.selectAll()
        else:
            self.proxy_model.set_only_selected(False, set())
            if self._cached_selected_rows:
                self.select_features(list(self._cached_selected_rows))
        self._update_stats_label()

    def _add_field(self):
        if self._current_gdf is None or self._current_gdf.empty:
            QMessageBox.information(self, "Veri Yok", "Yüklü mekansal katman bulunamadı.")
            return

        dlg = AddFieldDialog(list(self._current_gdf.columns), parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            name = dlg.field_name
            val = dlg.default_val
            try:
                self._current_gdf[name] = val
                self.load_data(self._current_gdf)
                self.data_modified.emit(self._current_gdf)
                QMessageBox.information(self, "Alan Eklendi", f"'{name}' sütunu başarıyla eklendi!")
            except Exception as e:
                QMessageBox.critical(self, "Hata", f"Sütun eklenirken hata oluştu: {e}")

    def _on_cell_data_changed(self):
        self.data_modified.emit(self._current_gdf)

    def _on_table_double_clicked(self, proxy_idx):
        if not proxy_idx.isValid() or self._current_gdf is None or self._current_gdf.empty:
            return
        src_idx = self.proxy_model.mapToSource(proxy_idx)
        if not src_idx.isValid():
            return
        col_name = self.source_model._columns[src_idx.column()]
        geom_name = getattr(self._current_gdf, 'geometry', None).name if hasattr(self._current_gdf, 'geometry') else None
        if col_name == geom_name:
            self._edit_selected_geometry()
        else:
            self.table_view.edit(proxy_idx)

    def _edit_selected_geometry(self):
        indexes = self.table_view.selectionModel().selectedRows()
        if not indexes or self._current_gdf is None or self._current_gdf.empty:
            return
        src_idx = self.proxy_model.mapToSource(indexes[0])
        if not src_idx.isValid():
            return
        row = src_idx.row()
        if row < 0 or row >= len(self._current_gdf):
            return

        geom = self._current_gdf.geometry.iat[row]
        geom_type = getattr(geom, 'geom_type', 'Nokta') if geom is not None else 'Nokta'
        crs_str = str(self._current_gdf.crs) if self._current_gdf.crs else "EPSG:4326"

        dlg = EditGeometryDialog(geom, geom_type, crs_str, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.updated_geom is not None:
            geom_col = getattr(self._current_gdf, 'geometry', None).name if hasattr(self._current_gdf, 'geometry') else 'geometry'
            self._current_gdf.at[self._current_gdf.index[row], geom_col] = dlg.updated_geom
            self.source_model.set_data(self._current_gdf)
            self.data_modified.emit(self._current_gdf)

    def _add_row(self):
        if self._current_gdf is None:
            return
        geom_col = getattr(self._current_gdf, 'geometry', None).name if hasattr(self._current_gdf, 'geometry') else 'geometry'
        geom_type = SpatialOps.get_layer_geometry_type(self._current_gdf)

        from shapely.geometry import Point, LineString, Polygon

        # Calculate sensible default location based on existing dataset bounds
        if not self._current_gdf.empty and self._current_gdf.total_bounds is not None:
            try:
                minx, miny, maxx, maxy = self._current_gdf.total_bounds
                cx = (minx + maxx) / 2.0
                cy = (miny + maxy) / 2.0
                dx = max(abs(maxx - minx) * 0.05, 0.001)
                dy = max(abs(maxy - miny) * 0.05, 0.001)
            except Exception:
                cx, cy, dx, dy = 35.0, 39.0, 0.001, 0.001
        else:
            cx, cy, dx, dy = 35.0, 39.0, 0.01, 0.01

        if geom_type == "point":
            default_geom = Point(cx, cy)
        elif geom_type == "line":
            default_geom = LineString([(cx - dx, cy - dy), (cx + dx, cy + dy)])
        elif geom_type == "polygon":
            default_geom = Polygon([(cx - dx, cy - dy), (cx + dx, cy - dy), (cx + dx, cy + dy), (cx - dx, cy + dy), (cx - dx, cy - dy)])
        else:
            default_geom = Point(cx, cy)

        new_row = {col: None for col in self._current_gdf.columns if col != geom_col}
        new_row[geom_col] = default_geom

        for id_col in ["id", "ID", "fid", "FID", "gid", "objectid"]:
            if id_col in new_row:
                new_row[id_col] = len(self._current_gdf) + 1

        target_crs = self._current_gdf.crs or "EPSG:4326"
        row_gdf = gpd.GeoDataFrame([new_row], crs=target_crs)
        self._current_gdf = pd.concat([self._current_gdf, row_gdf], ignore_index=True)
        self.source_model.set_data(self._current_gdf)
        self.data_modified.emit(self._current_gdf)
        self._update_stats_label()

        new_idx = len(self._current_gdf) - 1
        src_idx = self.source_model.index(new_idx, 0)
        proxy_idx = self.proxy_model.mapFromSource(src_idx)
        if proxy_idx.isValid():
            self.table_view.scrollTo(proxy_idx)
            self.table_view.selectRow(proxy_idx.row())

    def _on_selection_changed(self, selected, deselected):
        indexes = self.table_view.selectionModel().selectedRows()
        count = len(indexes)
        has_sel = count > 0

        self.btn_del_selected.setEnabled(has_sel)
        self.btn_zoom_selected.setEnabled(has_sel)
        self.btn_edit_geom.setEnabled(count == 1)
        if has_sel:
            self.btn_del_selected.setToolTip(f"Seçili {count:,} Kaydı Sil (Del)")
            self.btn_zoom_selected.setToolTip(f"Haritada Seçili {count:,} Geometriye Yakınlaş")
            self.btn_stats.setToolTip(f"Sütun İstatistikleri (Seçili {count:,} kayıt için)")
            if count == 1:
                self.btn_edit_geom.setToolTip("Seçili Geometriyi Düzenle (WKT & Koordinatlar)")
            else:
                self.btn_edit_geom.setToolTip("Geometri düzenlemek için tek bir kayıt seçin")
        else:
            self.btn_del_selected.setToolTip("Seçili Kayıtları Sil (Del)")
            self.btn_zoom_selected.setToolTip("Haritada Seçilenlere Yakınlaş")
            self.btn_stats.setToolTip("Sütun İstatistikleri (Tüm katman için)")
            self.btn_edit_geom.setToolTip("Seçili Geometriyi Düzenle (WKT & Koordinatlar)")

        if self._block_selection_signals:
            return

        source_rows = []
        for proxy_idx in indexes:
            src_idx = self.proxy_model.mapToSource(proxy_idx)
            if src_idx.isValid():
                source_rows.append(src_idx.row())

        self.features_selected.emit(source_rows)
        if source_rows:
            self.feature_selected.emit(source_rows[0])

    def _delete_selected_rows(self):
        indexes = self.table_view.selectionModel().selectedRows()
        if not indexes:
            return
        source_rows = []
        for proxy_idx in indexes:
            src_idx = self.proxy_model.mapToSource(proxy_idx)
            if src_idx.isValid():
                source_rows.append(src_idx.row())
        if not source_rows:
            return

        count = len(source_rows)
        if count > 10:
            reply = QMessageBox.question(
                self, "Satırları Sil",
                f"{count:,} adet seçili öznitelik kaydını ve geometrisini silmek istediğinize emin misiniz?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self.delete_requested.emit(source_rows)

    def select_features(self, indices: list):
        if self._block_selection_signals:
            return
        self._block_selection_signals = True
        try:
            sel_model = self.table_view.selectionModel()
            sel_model.clearSelection()
            if not indices or self.source_model.rowCount() == 0:
                self.btn_del_selected.setEnabled(False)
                self.btn_del_selected.setToolTip("Seçili Kayıtları Sil (Del)")
                self.btn_zoom_selected.setEnabled(False)
                self.btn_zoom_selected.setToolTip("Haritada Seçilenlere Yakınlaş")
                self.btn_stats.setToolTip("Sütun İstatistikleri (Tüm katman için)")
                return

            col_count = self.proxy_model.columnCount()
            first_valid_proxy = None
            proxy_rows = []

            for idx in indices:
                if 0 <= idx < self.source_model.rowCount():
                    src_idx = self.source_model.index(idx, 0)
                    proxy_idx = self.proxy_model.mapFromSource(src_idx)
                    if proxy_idx.isValid():
                        if first_valid_proxy is None:
                            first_valid_proxy = proxy_idx
                        proxy_rows.append(proxy_idx.row())

            if proxy_rows:
                proxy_rows.sort()
                ranges = []
                start = proxy_rows[0]
                end = start
                for r in proxy_rows[1:]:
                    if r == end + 1:
                        end = r
                    else:
                        ranges.append((start, end))
                        start = r
                        end = r
                ranges.append((start, end))

                selection = QItemSelection()
                col_end = max(0, col_count - 1)
                for s_row, e_row in ranges:
                    tl = self.proxy_model.index(s_row, 0)
                    br = self.proxy_model.index(e_row, col_end)
                    selection.select(tl, br)

                sel_model.select(selection, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
            if first_valid_proxy:
                self.table_view.scrollTo(first_valid_proxy, QTableView.ScrollHint.PositionAtCenter)

            count = len(indices)
            self.btn_del_selected.setEnabled(count > 0)
            self.btn_zoom_selected.setEnabled(count > 0)
            if count > 0:
                self.btn_del_selected.setToolTip(f"Seçili {count:,} Kaydı Sil (Del)")
                self.btn_zoom_selected.setToolTip(f"Haritada Seçili {count:,} Geometriye Yakınlaş")
                self.btn_stats.setToolTip(f"Sütun İstatistikleri (Seçili {count:,} kayıt için)")
            else:
                self.btn_del_selected.setToolTip("Seçili Kayıtları Sil (Del)")
                self.btn_zoom_selected.setToolTip("Haritada Seçilenlere Yakınlaş")
                self.btn_stats.setToolTip("Sütun İstatistikleri (Tüm katman için)")
        finally:
            self._block_selection_signals = False

    def select_feature(self, index: int):
        self.select_features([index])

    def _show_column_statistics(self):
        if self._current_gdf is None or self._current_gdf.empty:
            QMessageBox.information(self, "Veri Yok", "Yüklü mekansal katman bulunamadı.")
            return

        cols = [c for c in self._current_gdf.columns if c != getattr(self._current_gdf, 'geometry', None).name]
        if not cols:
            QMessageBox.information(self, "Öznitelik Yok", "İstatistik hesaplanacak öznitelik sütunu bulunamadı.")
            return

        # Check if there are selected rows in the table
        indexes = self.table_view.selectionModel().selectedRows()
        selected_source_rows = []
        for proxy_idx in indexes:
            src_idx = self.proxy_model.mapToSource(proxy_idx)
            if src_idx.isValid():
                selected_source_rows.append(src_idx.row())

        if selected_source_rows:
            target_gdf = self._current_gdf.iloc[selected_source_rows]
            scope_desc = f"Seçili {len(selected_source_rows):,} Kayıt"
        else:
            target_gdf = self._current_gdf
            scope_desc = f"Tüm Katman ({len(self._current_gdf):,} Kayıt)"

        from ui.dialogs import ColumnStatisticsDialog
        dlg = ColumnStatisticsDialog(target_gdf, cols, scope_desc=scope_desc, parent=self)
        dlg.exec()

    def _calculate_geometry(self):
        if self._current_gdf is None or self._current_gdf.empty:
            QMessageBox.information(self, "Veri Yok", "Yüklü mekansal katman bulunamadı.")
            return

        try:
            updated_gdf = SpatialOps.calculate_geometry_attributes(self._current_gdf)
            self.load_data(updated_gdf)
            self.data_modified.emit(updated_gdf)
            QMessageBox.information(self, "Geometri Hesaplandı", "Alan (km²), uzunluk (km) ve koordinat sütunları başarıyla eklendi!")
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Geometri hesaplanamadı: {e}")

    def _export_csv(self):
        if self._current_gdf is None or self._current_gdf.empty:
            QMessageBox.information(self, "Veri Yok", "Dışa aktarılacak veri yok.")
            return

        path, _ = QFileDialog.getSaveFileName(self, "Öznitelik Tablosunu Dışa Aktar", "attributes.csv", "CSV Dosyaları (*.csv)")
        if not path:
            return

        try:
            clean_df = pd.DataFrame(self._current_gdf.drop(columns=[self._current_gdf.geometry.name], errors='ignore'))
            clean_df.to_csv(path, index=False, encoding='utf-8')
            QMessageBox.information(self, "Başarılı", f"Öznitelik tablosu kaydedildi:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"CSV kaydedilemedi: {str(e)}")

