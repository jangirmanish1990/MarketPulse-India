"""Generate placeholder PWA icons using only Python stdlib (no Pillow needed)."""
import os
import struct
import zlib


def make_png(width: int, height: int, r: int, g: int, b: int) -> bytes:
    def crc32(data: bytes) -> bytes:
        return struct.pack(">I", zlib.crc32(data) & 0xFFFFFFFF)

    def chunk(tag: bytes, data: bytes) -> bytes:
        payload = tag + data
        return struct.pack(">I", len(data)) + payload + crc32(payload)

    sig  = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))

    # Each scanline: filter byte 0x00 followed by RGB triples
    row  = bytes([0x00] + [r, g, b] * width)
    raw  = row * height
    idat = chunk(b"IDAT", zlib.compress(raw, 9))
    iend = chunk(b"IEND", b"")

    return sig + ihdr + idat + iend


if __name__ == "__main__":
    out_dir = os.path.join(
        os.path.dirname(__file__), "..", "frontend", "public", "icons"
    )
    os.makedirs(out_dir, exist_ok=True)

    # Saffron: #FF9500
    R, G, B = 0xFF, 0x95, 0x00

    for size, name in [(192, "icon-192.png"), (512, "icon-512.png")]:
        path = os.path.join(out_dir, name)
        data = make_png(size, size, R, G, B)
        with open(path, "wb") as fh:
            fh.write(data)
        print(f"  {name}: {size}x{size}  {len(data):,} bytes")

    print("Done.")
