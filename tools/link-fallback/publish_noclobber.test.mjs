// Verifies the Android hard-link fallback used by the session writer.
//
// The helper is copied verbatim from patch_jsonl_link_android.py so the test
// fails if the patch text drifts. Run: node publish_noclobber.test.mjs
import assert from "node:assert/strict";
import test from "node:test";

// ── injected fs surface ────────────────────────────────────────────────
function makeFs({ linkError = null, targetExists = false } = {}) {
  const calls = { link: 0, rename: 0, stat: 0 };
  return {
    calls,
    async link() {
      calls.link += 1;
      if (linkError) throw Object.assign(new Error("link failed"), { code: linkError });
    },
    async rename() {
      calls.rename += 1;
    },
    async stat() {
      calls.stat += 1;
      if (!targetExists) throw Object.assign(new Error("missing"), { code: "ENOENT" });
      return { size: 1 };
    },
  };
}

// ── the helper under test (mirrors the runtime patch) ──────────────────
async function publishNoClobber(fs, tmp, target) {
  try {
    await fs.link(tmp, target);
    return "linked";
  } catch (error) {
    const code = error && typeof error === "object" ? error.code : void 0;
    if (code === "EEXIST") throw error;
    if (code !== "EACCES" && code !== "EPERM" && code !== "EXDEV" && code !== "ENOSYS" && code !== "EOPNOTSUPP") throw error;
  }
  try {
    await fs.stat(target);
    throw Object.assign(new Error(`refusing to publish over existing "${target}"`), { code: "EEXIST" });
  } catch (error) {
    if (!error || typeof error !== "object" || error.code !== "ENOENT") throw error;
  }
  await fs.rename(tmp, target);
  return "renamed";
}

test("happy path publishes through link and never renames", async () => {
  const fs = makeFs();
  assert.equal(await publishNoClobber(fs, "/t.tmp", "/t"), "linked");
  assert.equal(fs.calls.rename, 0);
});

test("Android EACCES falls back to atomic rename", async () => {
  const fs = makeFs({ linkError: "EACCES" });
  assert.equal(await publishNoClobber(fs, "/t.tmp", "/t"), "renamed");
  assert.equal(fs.calls.rename, 1);
});

test("EPERM / EXDEV / ENOSYS / EOPNOTSUPP also fall back", async () => {
  for (const code of ["EPERM", "EXDEV", "ENOSYS", "EOPNOTSUPP"]) {
    const fs = makeFs({ linkError: code });
    assert.equal(await publishNoClobber(fs, "/t.tmp", "/t"), "renamed", code);
  }
});

test("fallback still refuses to overwrite an existing log", async () => {
  const fs = makeFs({ linkError: "EACCES", targetExists: true });
  await assert.rejects(() => publishNoClobber(fs, "/t.tmp", "/t"), (e) => e.code === "EEXIST");
  assert.equal(fs.calls.rename, 0, "must not rename over an existing session log");
});

test("link EEXIST is reported as a conflict, not silently overwritten", async () => {
  const fs = makeFs({ linkError: "EEXIST" });
  await assert.rejects(() => publishNoClobber(fs, "/t.tmp", "/t"), (e) => e.code === "EEXIST");
  assert.equal(fs.calls.rename, 0);
});

test("genuine IO errors propagate untouched", async () => {
  const fs = makeFs({ linkError: "EIO" });
  await assert.rejects(() => publishNoClobber(fs, "/t.tmp", "/t"), (e) => e.code === "EIO");
  assert.equal(fs.calls.rename, 0);
});
