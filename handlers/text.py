from .base import BaseHandler
from core.io_utils import read_text_file, write_text_file


class TextHandler(BaseHandler):

    @property
    def is_spatial(self) -> bool:
        return False

    def read(self, file_path: str) -> str:
        return read_text_file(file_path)

    def write(self, file_path: str, content: str) -> bool:
        write_text_file(file_path, content)
        return True