import assert from "node:assert/strict";
import { computeShellWidths } from "../src/ui/layout.js";

function runCase(viewportW, { leftOpen, drawerOpen }) {
  return computeShellWidths({
    viewportW,
    dockW: 150,
    leftOpen,
    drawerOpen,
    pad: 14,
    gap: 14,
    chatMin: 360,
    leftMin: 260,
    leftMax: 360,
    drawerMin: 280,
    drawerMax: 420
  });
}

for (const viewportW of [980, 1366, 1920, 2560]) {
  for (const leftOpen of [false, true]) {
    for (const drawerOpen of [false, true]) {
      const r = runCase(viewportW, { leftOpen, drawerOpen });
      assert.ok(r.chatW >= 0, `chatW should be non-negative (viewport=${viewportW})`);
      assert.ok(r.leftW >= 0 && r.leftW <= 360, `leftW in range (viewport=${viewportW})`);
      assert.ok(r.drawerW >= 0 && r.drawerW <= 420, `drawerW in range (viewport=${viewportW})`);
      if (viewportW >= 1366) {
        assert.ok(r.chatW >= 360, `chatW >= chatMin on typical desktops (viewport=${viewportW})`);
      }
    }
  }
}

