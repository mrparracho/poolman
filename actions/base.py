from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any

@dataclass
class ActionExample:
    command: str
    intent: str
    params: Dict[str, Any]

class BaseAction(ABC):
    """Base interface for all actions"""
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of what the action does"""
        pass
    
    @property
    @abstractmethod
    def intent_name(self) -> str:
        """The name of the intent this action handles"""
        pass
    
    @property
    @abstractmethod
    def parameters(self) -> Dict[str, str]:
        """Dictionary of parameter names and their descriptions"""
        pass
    
    @property
    @abstractmethod
    def examples(self) -> list[ActionExample]:
        """List of example commands and their parsed form"""
        pass
    
    @abstractmethod
    def run(self, **kwargs) -> str:
        """Execute the action with given parameters"""
        pass 