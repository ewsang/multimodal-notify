# notify/base_connector.py
from abc import ABC, abstractmethod

class BaseConnector(ABC):
    @abstractmethod
    def handle(self, event):
        pass