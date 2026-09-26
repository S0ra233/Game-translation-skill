"""Independent encoders for synthetic archive samples, reused from the original tests."""
import struct

def marshal_string(text):
    raw = text.encode("utf-8")
    length = bytes([len(raw) + 5]) if 0 < len(raw) < 123 else b"\x01" + bytes([len(raw)])
    if not raw:
        length = b"\x00"
    return b'"' + length + raw

def actor_blob(name):
    return (b"\x04\x08[\x07" + b"0o:\x0fRPG::Actor\x06:\x0a@name" + marshal_string(name))

def xor_payload(payload, key):
    # Independent fixture encoder, operating byte by byte.
    result = bytearray()
    for index, value in enumerate(payload):
        if index and index % 4 == 0:
            key = (key * 7 + 3) & 0xFFFFFFFF
        result.append(value ^ ((key >> (8 * (index % 4))) & 255))
    return bytes(result)

def archive_v3(name, payload):
    name = name.encode()
    seed, fkey = 17, 0xAAFF1259
    key = seed * 9 + 3
    offset = 8 + 4 + 16 + len(name) + 4
    encoded_name = bytes(b ^ ((key >> (8 * (i % 4))) & 255) for i, b in enumerate(name))
    return (b"RGSSAD\x00\x03" + struct.pack("<I", seed) +
            b"".join(struct.pack("<I", x ^ key) for x in (offset, len(payload), fkey, len(name))) +
            encoded_name + struct.pack("<I", key) + xor_payload(payload, fkey))

def archive_v1(files):
    result = bytearray(b"RGSSAD\x00\x01")
    key = 0xDEADCAFE
    advance = lambda k: (k * 7 + 3) & 0xFFFFFFFF
    for name, payload in files:
        name = name.encode()
        result.extend(struct.pack("<I", len(name) ^ key))
        key = advance(key)
        for byte in name:
            result.append(byte ^ (key & 255))
            key = advance(key)
        result.extend(struct.pack("<I", len(payload) ^ key))
        key = advance(key)
        result.extend(xor_payload(payload, key))
    return bytes(result)
