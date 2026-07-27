from abc import ABC, abstractmethod

class BaseHandler(ABC):

    @property
    @abstractmethod
    def is_spatial(self) -> bool:
        pass

    @abstractmethod
    def read(self, file_path: str, **kwargs) -> str:
        pass

    @abstractmethod
    def write(self, file_path: str, content: str) -> None:
        pass