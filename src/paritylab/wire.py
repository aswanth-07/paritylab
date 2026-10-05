"""CRC-protected datagrams with JSON control fields and unmodified binary symbols."""
import json
import struct
import zlib

MAGIC = b"PL01"
PREFIX = struct.Struct("!4sIH")
MAX_DATAGRAM = 65507


def pack(message: dict) -> bytes:
    fields = dict(message)
    payload = fields.pop("payload", b"")
    if not isinstance(payload, bytes):
        raise ValueError("A symbol payload must be bytes")
    header = json.dumps(fields, separators=(",", ":"), allow_nan=False).encode()
    body = header + payload
    if len(header) > 4096 or len(body) + PREFIX.size > MAX_DATAGRAM:
        raise ValueError("Datagram exceeds the protocol limit")
    return PREFIX.pack(MAGIC, zlib.crc32(body), len(header)) + body


def unpack(wire: bytes) -> dict:
    if not PREFIX.size <= len(wire) <= MAX_DATAGRAM:
        raise ValueError("Invalid datagram length")
    magic, checksum, length = PREFIX.unpack_from(wire)
    body = wire[PREFIX.size:]
    if magic != MAGIC or not 0 < length <= min(4096, len(body)) or zlib.crc32(body) != checksum:
        raise ValueError("Invalid datagram framing or CRC")
    fields = json.loads(body[:length])
    if not isinstance(fields, dict) or not isinstance(fields.get("kind"), str):
        raise ValueError("Invalid control fields")
    fields["payload"] = body[length:]
    return fields


def integer(fields, key, low, high):
    value = fields.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f"Invalid {key}")
    return value
