export function computeShellWidths({
  viewportW,
  dockW,
  leftOpen,
  leftOverlay = false,
  drawerOpen,
  pad = 14,
  gap = 14,
  chatMin = 360,
  leftMin = 260,
  leftMax = 360,
  drawerMin = 280,
  drawerMax = 420
}) {
  const v = Math.max(0, Number(viewportW) || 0);
  const dock = Math.max(0, Number(dockW) || 0);

  let leftW = leftOpen ? leftMax : 0;
  let drawerW = drawerOpen ? drawerMax : 0;
  let forceCloseLeft = false;
  const overlay = !!leftOverlay;

  function leftbarW() {
    return dock + (leftW > 0 && !overlay ? gap + leftW : 0);
  }

  function gridGapCount() {
    // Columns: leftbar + chat (+ drawer)
    return drawerW > 0 ? 2 : 1;
  }

  function chatW() {
    return v - 2 * pad - gridGapCount() * gap - leftbarW() - drawerW;
  }

  // Ensure chat has usable minimum width by shrinking side panels in order.
  if (chatW() < chatMin && leftW > 0) leftW = Math.max(leftMin, Math.min(leftW, leftMax));
  if (chatW() < chatMin && leftW > leftMin) leftW = leftMin;
  if (chatW() < chatMin && drawerW > 0) drawerW = Math.max(drawerMin, Math.min(drawerW, drawerMax));
  if (chatW() < chatMin && drawerW > drawerMin) drawerW = drawerMin;
  if (chatW() < chatMin && leftW > 0) {
    leftW = 0;
    forceCloseLeft = true;
  }

  return {
    dockW: dock,
    leftW,
    leftbarW: leftbarW(),
    drawerW,
    chatW: chatW(),
    forceCloseLeft
  };
}
