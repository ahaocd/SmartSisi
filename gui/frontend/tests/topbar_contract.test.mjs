import assert from "node:assert/strict";
import fs from "node:fs";

const homePath = new URL("../src/pages/HomePage.vue", import.meta.url);
const home = fs.readFileSync(homePath, "utf8");

assert.equal(
  home.includes('import StatusBar from "../components/StatusBar.vue";'),
  false,
  "HomePage topbar must not import StatusBar"
);

assert.equal(
  home.includes("<StatusBar />"),
  false,
  "HomePage topbar must not render StatusBar"
);
