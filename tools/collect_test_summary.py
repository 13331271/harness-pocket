"""Collect completed JUnit XML counters without treating them as device tests."""
import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    names = ["LogPolicyTest", "EngineLogTest", "BootTokenCaptureTest", "LocalEngineOwnershipTest"]
    suites = []
    for name in names:
        path = args.results / ("TEST-app.dsh.mobile.engine." + name + ".xml")
        root = ET.parse(path).getroot()
        suites.append({"name": root.attrib["name"],
                       **{key: int(root.attrib[key]) for key in ("tests", "skipped", "failures", "errors")},
                       "time_seconds": float(root.attrib["time"]),
                       "source": str(path)})
    total = {key: sum(suite[key] for suite in suites) for key in ("tests", "skipped", "failures", "errors")}
    report = {"junit": {"total": total, "suites": suites},
              "additional_host_tests": {"flock_wrapper_and_no_clobber": 15,
                                        "pty_mock_and_source_guards": 25},
              "android_device_execution": "not verified"}
    if args.output.exists():
        raise FileExistsError("Test summary already exists")
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(total))
    if total["failures"] or total["errors"] or total["skipped"] or total["tests"] != 73:
        raise RuntimeError("Expected 73 passing, unskipped completed JUnit tests")


if __name__ == "__main__":
    main()
