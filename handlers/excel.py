import os
import pandas as pd
from .base import BaseHandler


class ExcelHandler(BaseHandler):
    """Handler for reading and writing Excel spreadsheets (.xlsx, .xls)."""

    @property
    def is_spatial(self) -> bool:
        return False

    def read(self, file_path: str, **kwargs) -> dict:
        """
        Reads all sheets from an Excel workbook.
        Returns a dictionary mapping sheet names to pandas DataFrames.
        """
        try:
            with pd.ExcelFile(file_path) as excel_file:
                sheets = {}
                for sheet_name in excel_file.sheet_names:
                    df = pd.read_excel(excel_file, sheet_name=sheet_name)
                    sheets[sheet_name] = df
            return sheets
        except Exception as e:
            raise RuntimeError(f"Excel dosyası okunamadı ({os.path.basename(file_path)}): {e}")

    def write(self, file_path: str, sheets_data: dict, **kwargs) -> None:
        """
        Writes a dictionary of DataFrames to an Excel file (.xlsx).
        """
        try:
            with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
                for sheet_name, df in sheets_data.items():
                    if isinstance(df, pd.DataFrame):
                        df.to_excel(writer, sheet_name=sheet_name, index=False)
        except Exception as e:
            raise RuntimeError(f"Excel dosyası kaydedilemedi ({os.path.basename(file_path)}): {e}")
