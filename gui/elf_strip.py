"""Minimal ELF section stripper for Android .so files.

Flutter's Android engine artifacts on this machine are unstripped: most of
libflutter.so is .debug_* sections. AGP cannot strip them without the NDK, so
the APK becomes hundreds of MB. This module removes non-runtime sections and
rebuilds a compact ELF without moving any allocated section (PT_LOAD segments
stay valid).
"""

from __future__ import annotations

import struct

ELF_HEADER_SIZE = 64
SECTION_HEADER_SIZE = 64
SHF_ALLOC = 0x2
SHT_NOBITS = 8


def strip_elf(data: bytes) -> bytes:
    """Return a compacted ELF, or the original bytes if anything is unexpected."""
    if len(data) < ELF_HEADER_SIZE or data[:4] != b"\x7fELF" or data[4] != 2 or data[5] != 1:
        return data

    e_shoff = struct.unpack_from("<Q", data, 0x28)[0]
    e_shentsize = struct.unpack_from("<H", data, 0x3A)[0]
    e_shnum = struct.unpack_from("<H", data, 0x3C)[0]
    e_shstrndx = struct.unpack_from("<H", data, 0x3E)[0]

    if e_shentsize != SECTION_HEADER_SIZE or e_shnum == 0 or e_shstrndx >= e_shnum:
        return data
    if e_shoff + e_shnum * e_shentsize > len(data):
        return data

    sections = []
    for index in range(e_shnum):
        offset = e_shoff + index * e_shentsize
        name, sh_type, flags, addr, sh_offset, size, link, info, align, entsize = struct.unpack_from(
            "<IIQQQQIIQQ", data, offset
        )
        sections.append({
            "name_off": name,
            "type": sh_type,
            "flags": flags,
            "offset": sh_offset,
            "size": size,
            "index": index,
            "raw_offset": offset,
        })

    shstr = sections[e_shstrndx]
    shstr_data = data[shstr["offset"]:shstr["offset"] + shstr["size"]]

    def section_name(section):
        start = section["name_off"]
        if start >= len(shstr_data):
            return ""
        end = shstr_data.find(b"\x00", start)
        if end < 0:
            end = len(shstr_data)
        try:
            return shstr_data[start:end].decode("ascii", "replace")
        except Exception:
            return ""

    keep = []
    for section in sections:
        name = section_name(section)
        if section["index"] == e_shstrndx or (section["flags"] & SHF_ALLOC):
            keep.append(section)

    if len(keep) < 2:
        return data

    # The loadable image ends at the last allocated byte.
    alloc_end = ELF_HEADER_SIZE
    for section in keep:
        if section["index"] == e_shstrndx:
            continue
        if section["type"] != SHT_NOBITS:
            alloc_end = max(alloc_end, section["offset"] + section["size"])
    if alloc_end > len(data):
        return data

    out = bytearray(data[:alloc_end])
    while len(out) % 8:
        out.append(0)

    shstr_is_alloc = bool(shstr["flags"] & SHF_ALLOC)
    if shstr_is_alloc:
        new_shstr_offset = shstr["offset"]
    else:
        new_shstr_offset = len(out)
        out.extend(shstr_data)
        while len(out) % 8:
            out.append(0)

    new_section_offset = len(out)
    new_index = {section["index"]: index for index, section in enumerate(keep)}
    for section in keep:
        raw = bytearray(data[section["raw_offset"]:section["raw_offset"] + SECTION_HEADER_SIZE])
        if section["index"] == e_shstrndx:
            struct.pack_into("<Q", raw, 24, new_shstr_offset)
        # Section indices in sh_link (and sh_info for relocations) changed when
        # non-allocated debug/symbol sections were dropped.
        old_link = struct.unpack_from("<I", raw, 40)[0]
        struct.pack_into("<I", raw, 40, new_index.get(old_link, 0))
        sh_type = struct.unpack_from("<I", raw, 4)[0]
        if sh_type in (4, 9):  # SHT_REL / SHT_RELA
            old_info = struct.unpack_from("<I", raw, 44)[0]
            struct.pack_into("<I", raw, 44, new_index.get(old_info, 0))
        out.extend(raw)

    struct.pack_into("<Q", out, 0x28, new_section_offset)
    struct.pack_into("<H", out, 0x3C, len(keep))
    struct.pack_into("<H", out, 0x3E, new_index[e_shstrndx])
    return bytes(out)
