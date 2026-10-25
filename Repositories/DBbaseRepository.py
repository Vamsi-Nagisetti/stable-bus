from abc import ABC, abstractmethod

class DBbaseRepository(ABC):

    @abstractmethod
    def update(self):
        pass
    
    @abstractmethod
    def save(self):
        pass
    
    @abstractmethod
    def get(self):
        pass

    @abstractmethod
    def delete(self):
        pass

