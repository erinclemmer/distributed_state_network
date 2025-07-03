from typing import Dict
from dataclasses import dataclass

@dataclass(frozen=True)
class Endpoint:
    address: str
    port: int

    @staticmethod
    def from_json(data: Dict) -> 'Endpoint':
        return Endpoint(data['address'], data['port'])
