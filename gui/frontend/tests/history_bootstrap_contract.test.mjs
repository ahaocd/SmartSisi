import assert from "node:assert/strict";
import fs from "node:fs";

const mainPath = new URL("../src/main.js", import.meta.url);
const storePath = new URL("../src/stores/systemStore.js", import.meta.url);

const main = fs.readFileSync(mainPath, "utf8");
const store = fs.readFileSync(storePath, "utf8");

assert.equal(main.includes("apiGetMsg"), true, "Startup should import apiGetMsg");
assert.equal(main.includes("syncHistoryFromBackend"), true, "Startup should define backend history sync");
assert.equal(main.includes("systemStore.hydrateHistoryFromBackend"), true, "Startup should hydrate store with backend history");

assert.equal(store.includes("hydrateHistoryFromBackend"), true, "System store should expose backend history hydrate action");
assert.equal(store.includes("mergeHistoryWithDedupe"), true, "System store should dedupe merged history");

