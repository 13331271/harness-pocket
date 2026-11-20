#!/usr/bin/env python3
"""Patch the session-persistence JSONL writer for Android hard-link denial.

Android (SELinux app_data_file) rejects link(2) inside /data/user/0/<pkg> with
EACCES, so the engine's "publish without clobbering" step fails when the first
session snapshot is materialised:

    EACCES: permission denied, link '...session.v4.jsonl.zstd.<hex>.tmp'
                                     -> '...session.v4.jsonl.zstd'

Fix: keep link() as the preferred path (it is the strongest no-clobber
primitive), but on the specific errnos that mean "this filesystem/domain will
not link" fall back to an atomic rename guarded by a last-moment existence
check. EEXIST from either path still means "a log already exists" and is
propagated unchanged, so the no-clobber contract survives.

Applied by derive_android_runtime.py at build time; never edit the runtime ZIP
by hand.
"""
from __future__ import annotations

OLD_IMPORT = (
    'import { rename as link, lstat, mkdir, mkdtemp, open, readFile, readdir, '
    'realpath, rm, stat, truncate } from "node:fs/promises";'
)
NEW_IMPORT = (
    'import { link, lstat, mkdir, mkdtemp, open, readFile, readdir, realpath, '
    'rename, rm, stat, truncate } from "node:fs/promises";'
)

HELPER = '''
/**
 * [dsh-android] Publish `tmp` at `target` without clobbering, tolerating
 * Android's hard-link denial.
 *
 * SELinux on Android refuses link(2) for files under the app's data directory
 * (EACCES), which broke session materialisation outright. link() stays the
 * preferred primitive; when the kernel/domain refuses it we fall back to an
 * atomic rename, guarded by an existence check so an existing log is still
 * reported as a conflict instead of being overwritten.
 */
async function publishNoClobber(tmp, target) {
  try {
    await link(tmp, target);
    return;
  } catch (error) {
    const code = error && typeof error === "object" ? error.code : void 0;
    if (code === "EEXIST") throw error;
    if (code !== "EACCES" && code !== "EPERM" && code !== "EXDEV" && code !== "ENOSYS" && code !== "EOPNOTSUPP") throw error;
  }
  try {
    await stat(target);
    throw Object.assign(new Error(`refusing to publish over existing "${target}"`), { code: "EEXIST" });
  } catch (error) {
    if (!error || typeof error !== "object" || error.code !== "ENOENT") throw error;
  }
  await rename(tmp, target);
}
'''

OLD_MATERIALIZE = """		let linked = false;
		try {
			await link(tmp, finalPath);
			linked = true;
		} finally {
			/* v8 ignore next -- link failure is the TOCTOU/IO race guarded above; not reachable in test */
			if (!linked) await rm(tmp, { force: true });
		}"""
NEW_MATERIALIZE = """		try {
			await publishNoClobber(tmp, finalPath);
		} catch (error) {
			await rm(tmp, { force: true });
			throw error;
		}"""

OLD_CURRENT = "		await internals.fs.link(staged, currentPath);"
NEW_CURRENT = "		await publishNoClobber(staged, currentPath);"

ANCHORS = (OLD_IMPORT, OLD_MATERIALIZE, OLD_CURRENT)


def patch(source: str) -> str:
    for anchor in ANCHORS:
        if source.count(anchor) != 1:
            raise ValueError(f"JSONL Android-fallback anchor changed ({source.count(anchor)} hits): {anchor[:60]}")
    source = source.replace(OLD_IMPORT, NEW_IMPORT, 1)
    # Helper goes right after the import block so it is module-scope.
    marker = NEW_IMPORT + "\n"
    source = source.replace(marker, marker + HELPER, 1)
    source = source.replace(OLD_MATERIALIZE, NEW_MATERIALIZE, 1)
    source = source.replace(OLD_CURRENT, NEW_CURRENT, 1)
    return source
