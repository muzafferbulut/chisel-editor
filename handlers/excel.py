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
        Reads all sheets from an Excel workbook or tabular data from a CSV file.
        Returns a dictionary mapping sheet names to pandas DataFrames.
        """
        ext = os.path.splitext(file_path)[1].lower()
        if ext == '.csv':
            try:
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
                sheet_name = os.path.splitext(os.path.basename(file_path))[0] or "CSV_Veri"
                return {sheet_name: df}
            except Exception as e:
                raise RuntimeError(f"CSV dosyası okunamadı ({os.path.basename(file_path)}): {e}")

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
        Writes a dictionary of DataFrames to an Excel file (.xlsx) or CSV file (.csv).
        """
        ext = os.path.splitext(file_path)[1].lower()
        if ext == '.csv':
            try:
                first_df = list(sheets_data.values())[0] if isinstance(sheets_data, dict) and sheets_data else pd.DataFrame()
                if isinstance(first_df, pd.DataFrame):
                    first_df.to_csv(file_path, index=False, encoding='utf-8')
                return
            except Exception as e:
                raise RuntimeError(f"CSV dosyası kaydedilemedi ({os.path.basename(file_path)}): {e}")

        try:
            with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
                for sheet_name, df in sheets_data.items():
                    if isinstance(df, pd.DataFrame):
                        df.to_excel(writer, sheet_name=sheet_name, index=False)
        except Exception as e:
            raise RuntimeError(f"Excel dosyası kaydedilemedi ({os.path.basename(file_path)}): {e}")
