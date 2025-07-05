from typing import Dict
from dataclasses import dataclass

@dataclass(frozen=True)
class Endpoint:
    address: str
    port: int

    def to_string(self):
        return f"{self.address}:{self.port}"

    def to_json(self):
        return {
            "address": self.address,
            "port": self.port
        }

    @staticmethod
    def from_json(data: Dict) -> 'Endpoint':
        return Endpoint(data['address'], data['port'])
