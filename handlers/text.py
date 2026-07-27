from .base import BaseHandler

class TextHandler(BaseHandler):

    @property
    def is_spatial(self) -> bool:
        return False

    def read(self, file_path: str) -> str:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()

    def write(self, file_path: str, content: str) -> bool:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return True