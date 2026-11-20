"""Generate a reviewable diff for the explicitly coordinated integration files."""
from __future__ import annotations
import argparse
import difflib
import hashlib
import json
from pathlib import Path

FILES = [
    "README.md", "gradle.properties", "app/build.gradle.kts", "scripts/write-runtime-manifest.py",
    "app/src/main/cpp/CMakeLists.txt", "app/src/main/cpp/dsh_pty_exec.c",
    *["app/src/main/java/app/dsh/mobile/engine/" + name for name in (
        "EngineConfig.kt", "EngineModeSelector.kt", "EngineLog.kt", "EngineProcess.kt",
        "LogPolicy.kt", "BoundedLogBuffer.kt", "LogLinePump.kt", "AgentBridge.kt", "EngineTriage.kt",
        "EngineSupervisor.kt", "Privilege.kt", "BootTokenCapture.kt", "LocalEngineOwnership.kt")],
    *["app/src/main/java/app/dsh/mobile/update/" + name for name in (
        "AppUpdatePrefs.kt", "AppUpdateChecker.kt", "RuntimeUpdateService.kt")],
    "app/src/main/java/app/dsh/mobile/MainActivity.kt",
    "app/src/main/java/app/dsh/mobile/UpdateSettingsActivity.kt",
    "app/src/main/java/app/dsh/mobile/LinuxActivity.kt",
    *["app/src/main/res/" + name + "/strings.xml" for name in (
        "values", "values-zh-rCN", "values-de", "values-ru", "values-th", "values-pt-rBR")],
    *["app/src/test/java/app/dsh/mobile/engine/" + name for name in (
        "LogPolicyJvmTest.kt", "LogPolicyTest.kt", "EngineLogTest.kt", "BootTokenCaptureTest.kt",
        "LocalEngineOwnershipTest.kt")],
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / "integration.diff"
    summary_path = args.output_dir / "integration-summary.json"
    if output.exists() or summary_path.exists():
        raise FileExistsError("Review outputs already exist")
    diff, summary = [], []
    for name in FILES:
        old = args.original / name
        new = args.source / name
        if not new.is_file():
            raise FileNotFoundError("Expected integrated file missing: " + name)
        old_data = old.read_bytes() if old.exists() else b""
        new_data = new.read_bytes()
        if old_data == new_data:
            continue
        before = old_data.decode("utf-8").splitlines(keepends=True)
        after = new_data.decode("utf-8").splitlines(keepends=True)
        # Replaced upstream README is separately reviewed as user documentation;
        # keep its giant marketing deletion out of the implementation review.
        if name != "README.md":
            diff.extend(difflib.unified_diff(before, after, fromfile="a/" + name,
                                            tofile="b/" + name))
        summary.append({"path": name, "status": "modified" if old.exists() else "added",
                        "sha256": hashlib.sha256(new_data).hexdigest(),
                        "old_bytes": len(old_data), "new_bytes": len(new_data)})
    output.write_text("".join(diff), encoding="utf-8")
    summary_path.write_text(json.dumps({"files": summary, "implementation_diff": str(output),
        "proprietary_exclusions": ["app/src/main/cpp/dsh_alpine.c",
            "app/src/main/jniLibs/*/libdsh_alpine.so", "app/src/main/assets/linux/**"],
        "reference_source_is_pruned": True}, indent=2), encoding="utf-8")
    print("Reviewed integration files:", len(summary))
    print("Diff:", output)


if __name__ == "__main__":
    main()
