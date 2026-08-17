from PyQt6.QtCore import QThread, pyqtSignal
from handlers.factory import HandlerFactory
import os


class FileLoadWorker(QThread):
    finished = pyqtSignal(str, str, bool, str)

    def __init__(self, file_path: str, **kwargs):
        super().__init__(**kwargs)
        self.file_path = file_path
        self.kwargs = kwargs

    def run(self):
        try:
            handler = HandlerFactory.get_handler(self.file_path)
            content = handler.read(self.file_path, **self.kwargs)
            self.finished.emit(self.file_path, content, handler.is_spatial, "")
        except Exception as e:
            self.finished.emit(self.file_path, "", False, str(e))