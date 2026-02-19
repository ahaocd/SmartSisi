import { useEventStore } from "../stores/eventStore";
import { useSystemStore } from "../stores/systemStore";

function pick(arr) {
  return arr[Math.floor(Math.random() * arr.length)];
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

export function startMockScenarios({ notify, mode = "current" } = {}) {
  const eventStore = useEventStore();
  const systemStore = useSystemStore();
  const timers = [];
  let aborted = false;

  function allowedSystem(system_id) {
    if (mode === "all") return true;
    return system_id === systemStore.currentSystemId;
  }

  // NOTE: This mock is intentionally not auto-started.
  // It exists only for manual UI testing of the Event Drawer.

  timers.push(
    setInterval(() => {
      if (aborted) return;
      const system_id = pick(["sisi", "liuye"]);
      const status = pick(["idle", "listening", "thinking", "speaking"]);
      systemStore.setAgentStatus(system_id, status);

      if (!allowedSystem(system_id)) return;
      eventStore.pushEvent({
        system_id,
        kind: "status",
        level: "info",
        title: "agent.status",
        message: `agent=${status}`,
        payload: { status }
      });

      if (status === "speaking" && systemStore.activeAudioSystemId !== system_id) {
        notify?.({
          system_id,
          kind: "audio",
          level: "warning",
          title: "Audio policy",
          message: "Blocked speaking: only audio-active system can output TTS."
        });
      }
    }, 7000)
  );

  (async () => {
    while (true) {
      if (aborted) return;
      await sleep(12000 + Math.random() * 6000);
      if (aborted) return;
      const system_id = pick(["sisi", "liuye"]);
      if (!allowedSystem(system_id)) continue;
      eventStore.pushEvent({
        system_id,
        kind: "debug",
        level: "info",
        title: "demo",
        message: "mock event",
        payload: { at: Date.now() }
      });
    }
  })();

  return () => {
    aborted = true;
    for (const id of timers) clearInterval(id);
  };
}

