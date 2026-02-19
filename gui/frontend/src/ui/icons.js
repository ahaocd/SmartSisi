/**
 * Icon registry - powered by lucide-vue-next.
 * Provides raw SVG strings for v-html usage and Vue component references.
 */
import {
  Volume2, Cpu, Wrench, ScrollText, CalendarClock,
  Palette, UserRound, Plus, Mic, Radio, ImagePlus,
  SendHorizonal, SkipForward, Shirt, RotateCcw,
  Settings, ChevronLeft, Trash2, Zap, Power,
  MessageSquare, BrainCircuit, AudioLines, Hammer,
  CircuitBoard, Sparkles, Shield, Bot
} from "lucide-vue-next";

/* ---- raw SVG for v-html (dock / composer / live2d buttons) ---- */

const svg = (d, opts = {}) => {
  const w = opts.w || 24;
  const sw = opts.sw || 2;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${w}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="${sw}" stroke-linecap="round" stroke-linejoin="round">${d}</svg>`;
};

const DockIcons = {
  audio:      svg('<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/>'),
  system:     svg('<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M7 7h.01"/><path d="M17 7h.01"/><path d="M7 17h.01"/><path d="M17 17h.01"/>'),
  tools:      svg('<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>'),
  logs:       svg('<path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/><line x1="16" x2="8" y1="13" y2="13"/><line x1="16" x2="8" y1="17" y2="17"/><line x1="10" x2="8" y1="9" y2="9"/>'),
  events:     svg('<rect width="18" height="18" x="3" y="4" rx="2" ry="2"/><line x1="16" x2="16" y1="2" y2="6"/><line x1="8" x2="8" y1="2" y2="6"/><line x1="3" x2="21" y1="10" y2="10"/><path d="m9 16 2 2 4-4"/>'),
  appearance: svg('<circle cx="13.5" cy="6.5" r=".5"/><circle cx="17.5" cy="10.5" r=".5"/><circle cx="8.5" cy="7.5" r=".5"/><circle cx="6.5" cy="12.5" r=".5"/><path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.926 0 1.648-.746 1.648-1.688 0-.437-.18-.835-.437-1.125-.29-.289-.438-.652-.438-1.125a1.64 1.64 0 0 1 1.668-1.668h1.996c3.051 0 5.555-2.503 5.555-5.554C21.965 6.012 17.461 2 12 2z"/>'),
  avatar:     svg('<circle cx="12" cy="8" r="5"/><path d="M20 21a8 8 0 0 0-16 0"/>')
};

export const ComposerIconMap = {
  plus: svg('<line x1="12" x2="12" y1="5" y2="19"/><line x1="5" x2="19" y1="12" y2="12"/>'),
  mic:  svg('<path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" x2="12" y1="19" y2="22"/>'),
  realtime: svg('<path d="M4.9 19.1C1 15.2 1 8.8 4.9 4.9"/><path d="M7.8 16.2c-2.3-2.3-2.3-6.1 0-8.5"/><circle cx="12" cy="12" r="2"/><path d="M16.2 7.8c2.3 2.3 2.3 6.1 0 8.5"/><path d="M19.1 4.9C23 8.8 23 15.1 19.1 19"/>'),
  image: svg('<rect width="18" height="18" x="3" y="3" rx="2" ry="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/>'),
  send: svg('<path d="m3 3 3 9-3 9 19-9Z"/><path d="M6 12h16"/>'),
  stop: svg('<rect x="6" y="6" width="12" height="12" rx="1"/>')
};

export const Live2DIconMap = {
  next:   svg('<polyline points="13 17 18 12 13 7"/><polyline points="6 17 11 12 6 7"/>'),
  outfit: svg('<path d="M20.38 3.46 16 2 12 5.5 8 2l-4.38 1.46a2 2 0 0 0-1.34 1.88v11.32a2 2 0 0 0 1.34 1.88L8 20l4-3.5L16 20l4.38-1.46a2 2 0 0 0 1.34-1.88V5.34a2 2 0 0 0-1.34-1.88Z"/>'),
  reset:  svg('<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>')
};

export function getIcon(kind, name) {
  const k = String(kind || "").toLowerCase();
  const n = String(name || "");
  if (k === "dock") return DockIcons[n] || DockIcons.system;
  if (k === "composer") return ComposerIconMap[n] || ComposerIconMap.plus;
  if (k === "live2d") return Live2DIconMap[n] || Live2DIconMap.next;
  return ComposerIconMap.plus;
}

/* ---- Vue component exports (for <component :is="..."> usage) ---- */
export const LucideComponents = {
  Volume2, Cpu, Wrench, ScrollText, CalendarClock,
  Palette, UserRound, Plus, Mic, Radio, ImagePlus,
  SendHorizonal, SkipForward, Shirt, RotateCcw,
  Settings, ChevronLeft, Trash2, Zap, Power,
  MessageSquare, BrainCircuit, AudioLines, Hammer,
  CircuitBoard, Sparkles, Shield, Bot
};
