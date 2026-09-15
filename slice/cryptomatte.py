"""Cryptomatte id decoding — pure Python so the arithmetic is unit-tested in CI and used verbatim
by the compositor (proposal §1 row 10; conventions.json → bundles CRYPTO_* parts).

A manifest maps a name to a 32-bit MurmurHash3 written as 8 hex digits; the rank channels
store that id converted uint32 → float32 (Blender's `conversion: "uint32_to_float32"`, the
Cryptomatte spec: the exponent is nudged so the bit pattern is a finite, non-denormal float).
Coverage of a name = sum over ranks of the coverage channel where the id channel equals the
name's float id exactly."""
from __future__ import annotations

import json
import struct


def float_id_from_hex(hex_id: str) -> float:
    """8 hex digits → the float32 the rank channels carry, per the Cryptomatte specification:
    clear the exponent's top bits when they would make the value inf/nan or denormal."""
    bits = int(hex_id, 16) & 0xFFFFFFFF
    exponent = (bits >> 23) & 0xFF
    if exponent == 0 or exponent == 255:
        bits ^= 1 << 23  # spec: flip the lowest exponent bit so the value is a normal float
    return struct.unpack("<f", struct.pack("<I", bits))[0]


def manifest_ids(manifest_json: str) -> dict[str, float]:
    return {name: float_id_from_hex(h) for name, h in json.loads(manifest_json).items()}
