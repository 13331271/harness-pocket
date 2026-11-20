"""Extract only bounded public package metadata from the verified runtime ZIP."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import zipfile


PUBLISHER_SHA256 = "fab5cd6689840e1e86625080924c3aa0fdbcb7bee6db3ef98aaee2ecdc1b0394"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    with args.archive.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != PUBLISHER_SHA256:
        raise ValueError("Input does not match the pinned publisher digest")
    args.output.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.archive) as source:
        if source.testzip() is not None:
            raise ValueError("Runtime ZIP CRC check failed")
        names = source.namelist()
        roots = sorted({name.split("/")[0] for name in names})
        forbidden = [name for name in names if any(term in name.lower()
                     for term in ("dsh_alpine", "libdsh_alpine", "framesrv"))]
        for name in ("BUILD.json",):
            if name in names:
                entry = source.getinfo(name)
                if entry.file_size > 512 * 1024:
                    raise ValueError("Unexpectedly large runtime build metadata")
                destination = args.output / name
                if not destination.exists():
                    destination.write_bytes(source.read(entry))
        # Metadata only: classify shipped native payload names without executing them.
        native_names = [name for name in names if name.endswith((".so", ".node", ".node.bin"))]
        (args.output / "native-payload-paths.json").write_text(
            json.dumps(native_names, indent=2), encoding="utf-8")
        manifests = []
        suffixes = (
            "node_modules/@deepseek-ai/dsh/package.json",
            "node_modules/@deepseek-ai/dsh-session-persistence-jsonl/package.json",
            "node_modules/@deepseek-ai/dsh-agent-loop/package.json",
            "node_modules/node-addon-system/package.json",
        )
        for name in names:
            if not name.endswith(suffixes):
                continue
            entry = source.getinfo(name)
            if entry.file_size > 512 * 1024:
                raise ValueError("Unexpectedly large package manifest")
            data = source.read(entry)
            package = json.loads(data)
            short_name = package["name"].split("/")[-1]
            destination = args.output / (short_name + ".package.json")
            if destination.exists():
                raise FileExistsError("Refusing to overwrite extracted metadata")
            destination.write_bytes(data)
            manifests.append({"entry": name, "name": package["name"],
                              "version": package["version"], "path": str(destination)})
        elf = []
        for name in names:
            if name.endswith("/bin/node") or name in ("bin/node", "node"):
                with source.open(name) as stream:
                    header = stream.read(64)
                if header[:4] != b"\x7fELF":
                    raise ValueError("Embedded Node is not an ELF executable")
                endian = "<" if header[5] == 1 else ">"
                elf.append({"entry": name, "elf_class": header[4],
                            "machine": struct.unpack(endian + "H", header[18:20])[0],
                            "size": source.getinfo(name).file_size})
        report = {"sha256": digest, "size": args.archive.stat().st_size,
                  "entries": len(names), "roots": roots,
                  "forbidden_container_entries": forbidden,
                  "manifests": manifests, "node_elf": elf,
                  "first_entries": names[:30],
                  "native_addon_entries": [name for name in names if name.endswith(".node")][:40],
                  "top_metadata": [name for name in names if name.count("/") <= 1
                                   and name.endswith((".json", ".txt", ".properties"))][:30]}
        destination = args.output / "summary.json"
        if destination.exists():
            raise FileExistsError("Runtime inspection report already exists")
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Validated runtime metadata at {destination}", flush=True)


if __name__ == "__main__":
    main()
