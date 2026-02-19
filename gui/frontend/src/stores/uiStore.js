import { defineStore } from "pinia";

export const LEFT_SECTIONS = ["audio", "system", "tools", "logs", "events", "appearance", "avatar"];
export const RIGHT_SECTIONS = ["avatar"];

export const useUiStore = defineStore("ui", {
  state: () => ({
    leftExpanded: false,
    leftSection: "audio",
    rightPanelOpen: false,
    rightSection: "avatar"
  }),
  actions: {
    openLeft(section) {
      if (LEFT_SECTIONS.includes(section)) this.leftSection = section;
      if (section === "avatar") this.rightPanelOpen = false;
      this.leftExpanded = true;
    },
    toggleLeft(section) {
      if (LEFT_SECTIONS.includes(section)) {
        if (this.leftExpanded && this.leftSection === section) {
          this.leftExpanded = false;
          return;
        }
        this.leftSection = section;
      }
      if (section === "avatar") this.rightPanelOpen = false;
      this.leftExpanded = true;
    },
    closeLeft() {
      this.leftExpanded = false;
    },
    openRight(section) {
      if (RIGHT_SECTIONS.includes(section)) this.rightSection = section;
      this.rightPanelOpen = true;
    },
    toggleRight(section) {
      if (RIGHT_SECTIONS.includes(section)) {
        if (this.rightPanelOpen && this.rightSection === section) {
          this.rightPanelOpen = false;
          return;
        }
        this.rightSection = section;
      }
      this.rightPanelOpen = true;
    },
    closeRight() {
      this.rightPanelOpen = false;
    }
  }
});
