import { defineStore } from "pinia";
import { useUiStore } from "./uiStore";

function makeId() {
  return `${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

function nowIso() {
  return new Date().toISOString();
}

export const EVENT_KINDS = ["chat", "agent", "guild", "tool", "audio", "status", "debug"];

export const useEventStore = defineStore("events", {
  state: () => ({
    drawerOpen: false,
    filterSystemId: "current",
    filterKind: "all",
    events: []
  }),
  actions: {
    openDrawer() {
      try {
        const ui = useUiStore();
        ui.closeLeft();
      } catch {}
      this.drawerOpen = true;
    },
    closeDrawer() {
      this.drawerOpen = false;
    },
    setFilterSystem(systemId) {
      this.filterSystemId = systemId;
    },
    setFilterKind(kind) {
      this.filterKind = kind;
    },
    pushEvent({ system_id, kind, level = "info", title = "", message = "", payload = {} }) {
      this.events.unshift({
        id: makeId(),
        system_id,
        kind,
        level,
        title,
        message,
        payload,
        created_at: nowIso()
      });
    },
    clear() {
      this.events = [];
    }
  }
});
