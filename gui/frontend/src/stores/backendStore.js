import { defineStore } from "pinia";

export const useBackendStore = defineStore("backend", {
  state: () => ({
    wsConnected: false,
    wsUrl: "",
    lastMessageAt: null,

    deviceList: [],
    voiceList: [],
    liveState: null,
    isConnect: null,
    audioStatus: null,
    audioPlaying: false,
    audioLevel: 0,
    musicPlaying: false,
    musicInfo: null
  }),
  actions: {
    setWsConnected(v, url = "") {
      this.wsConnected = !!v;
      this.wsUrl = url || this.wsUrl;
      this.lastMessageAt = Date.now();
    },
    onMessage() {
      this.lastMessageAt = Date.now();
    },
    setDeviceList(list) {
      this.deviceList = Array.isArray(list) ? list : [];
    },
    setVoiceList(list) {
      this.voiceList = Array.isArray(list) ? list : [];
    },
    setLiveState(v) {
      this.liveState = typeof v === "number" ? v : v == null ? null : Number(v);
    },
    setIsConnect(v) {
      this.isConnect = typeof v === "number" ? v : v == null ? null : Number(v);
    },
    setAudioStatus(status) {
      this.audioStatus = status ?? null;
      if (status == null) return;
      if (typeof status === "string") {
        this.audioPlaying = status === "busy";
        return;
      }
      if (typeof status === "object") {
        const playing = !!status.playing || !!status.is_busy;
        const queueSize = Number(status.queue_size || 0);
        const sceneQueue = Number(status.scene_queue_size || 0);
        this.audioPlaying = playing || queueSize > 0 || sceneQueue > 0;
      }
    },
    setAudioPlaying(v) {
      this.audioPlaying = !!v;
    },
    setAudioLevel(v) {
      const n = Number(v);
      if (!Number.isFinite(n)) return;
      this.audioLevel = Math.max(0, Math.min(1, n));
    },
    setMusicState(playing, info = null) {
      this.musicPlaying = !!playing;
      this.musicInfo = info || null;
    }
  }
});
