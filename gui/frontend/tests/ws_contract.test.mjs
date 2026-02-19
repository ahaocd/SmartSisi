import assert from "node:assert/strict";
import { collectUnknownKeys } from "../src/api/wsUtils.js";

const known = ["panelMsg", "panelReply", "deviceList", "voiceList", "liveState", "is_connect", "isConnect"];
const payload = { panelMsg: "ok", deviceList: [], extraA: 1, extraB: 2 };

const unknown = collectUnknownKeys(payload, known);
assert.deepEqual(unknown.sort(), ["extraA", "extraB"].sort());
