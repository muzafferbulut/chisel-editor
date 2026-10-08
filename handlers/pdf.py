import os
from .base import BaseHandler


class PdfHandler(BaseHandler):
    """Handler for PDF documents."""

    @property
    def is_spatial(self) -> bool:
        return False

    def read(self, file_path: str, **kwargs) -> dict:
        """
        Validates PDF path and returns metadata.
        """
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"PDF dosyası bulunamadı: {file_path}")

        return {
            "file_path": file_path,
            "file_size": os.path.getsize(file_path),
            "file_name": os.path.basename(file_path)
        }

    def write(self, file_path: str, content: object, **kwargs) -> None:
        pass
