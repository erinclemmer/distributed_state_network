import json
from hashlib import sha256

def int_to_bytes(i: int) -> bytes:
    return i.to_bytes(4, 'little', signed=False)

def bytes_to_int(b: bytes) -> int:
    return int.from_bytes(b, 'little', signed=False)

def get_hash(data: str) -> str:
    hash = sha256(data.encode())
    return hash.hexdigest()

def get_dict_hash(data: dict):
    return get_hash(json.dumps(data))
