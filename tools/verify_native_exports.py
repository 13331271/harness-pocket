"""Read-only ELF compatibility evidence for the embedded Node and Android addon."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import struct
import zipfile


def symbols(data: bytes):
    if data[:6] != b"\x7fELF\x02\x01":
        raise ValueError("Expected ELF64 little-endian")
    machine = struct.unpack_from("<H", data, 18)[0]
    shoff = struct.unpack_from("<Q", data, 40)[0]
    shentsize, shnum = struct.unpack_from("<HH", data, 58)
    if shentsize < 64 or not 0 < shnum < 4096 or shoff + shentsize * shnum > len(data):
        raise ValueError("Invalid ELF section table")
    sections = [struct.unpack_from("<IIQQQQIIQQ", data, shoff + i * shentsize)
                for i in range(shnum)]
    defined, undefined = set(), set()
    for section in sections:
        if section[1] != 11:
            continue
        offset, size, link, entsize = section[4], section[5], section[6], section[9]
        if not 0 <= link < shnum or entsize < 24 or offset + size > len(data):
            raise ValueError("Invalid ELF dynamic symbol section")
        strings = sections[link]
        names = data[strings[4]:strings[4] + strings[5]]
        for cursor in range(offset, offset + size, entsize):
            name_offset, info, other, index, value, sym_size = struct.unpack_from("<IBBHQQ", data, cursor)
            if name_offset >= len(names):
                raise ValueError("Invalid ELF symbol name offset")
            end = names.find(b"\x00", name_offset)
            if end < 0:
                raise ValueError("Unterminated ELF symbol name")
            name = names[name_offset:end].decode("ascii", "replace")
            if name:
                (undefined if index == 0 else defined).add(name)
    return machine, defined, undefined


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--addon", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    with args.runtime.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != "fab5cd6689840e1e86625080924c3aa0fdbcb7bee6db3ef98aaee2ecdc1b0394":
        raise ValueError("Unexpected source runtime")
    with zipfile.ZipFile(args.runtime) as source:
        info = source.getinfo("bin/node")
        if info.file_size > 100 * 1024 * 1024:
            raise ValueError("Unexpectedly large Node binary")
        node = source.read(info)
    addon = args.addon.read_bytes()
    node_machine, node_defined, _ = symbols(node)
    addon_machine, addon_defined, addon_undefined = symbols(addon)
    required = sorted(name for name in addon_undefined
                      if name.startswith(("napi_", "node_api_")))
    missing = sorted(set(required) - node_defined)
    report = {
        "runtime_sha256": digest,
        "node_elf_machine": node_machine,
        "addon_elf_machine": addon_machine,
        "addon_sha256": hashlib.sha256(addon).hexdigest(),
        "node_api_imports": required,
        "node_api_exports_missing": missing,
        "addon_init_exported": "napi_register_module_v1" in addon_defined,
        "real_flock_syscall_imported": "flock" in addon_undefined,
        "static_symbol_compatibility": node_machine == addon_machine == 183 and not missing
                                     and "napi_register_module_v1" in addon_defined,
        "device_execution": "not verified; real loading, contention and crash release require an Android device",
    }
    if args.output.exists():
        raise FileExistsError("Native export report already exists")
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["static_symbol_compatibility"] or not report["real_flock_syscall_imported"]:
        raise RuntimeError("Native addon failed static compatibility checks")


if __name__ == "__main__":
    main()
