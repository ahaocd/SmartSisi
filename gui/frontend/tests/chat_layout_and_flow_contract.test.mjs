import assert from "node:assert/strict";
import fs from "node:fs";

const chatPath = new URL("../src/components/ChatMessageList.vue", import.meta.url);
const composerPath = new URL("../src/components/ChatComposer.vue", import.meta.url);
const flowPath = new URL("../src/components/FlowChips.vue", import.meta.url);
const globalPath = new URL("../src/styles/global.css", import.meta.url);
const live2dPath = new URL("../src/components/Live2DSafeArea.vue", import.meta.url);
const appPath = new URL("../src/App.vue", import.meta.url);
const homePath = new URL("../src/pages/HomePage.vue", import.meta.url);
const inkFxPath = new URL("../src/components/InkFxCanvas.vue", import.meta.url);
const configPath = new URL("../src/stores/configStore.js", import.meta.url);
const sliderPath = new URL("../src/components/PixelSlider.vue", import.meta.url);
const drawerPath = new URL("../src/components/LeftDrawer.vue", import.meta.url);
const rowPath = new URL("../src/components/SettingRow.vue", import.meta.url);
const themePath = new URL("../src/theme/useThemeOverrides.js", import.meta.url);
const systemStorePath = new URL("../src/stores/systemStore.js", import.meta.url);
const rightDockPath = new URL("../src/components/RightDockPanel.vue", import.meta.url);

const chat = fs.readFileSync(chatPath, "utf8");
const composer = fs.readFileSync(composerPath, "utf8");
const flow = fs.readFileSync(flowPath, "utf8");
const globalCss = fs.readFileSync(globalPath, "utf8");
const live2d = fs.readFileSync(live2dPath, "utf8");
const app = fs.readFileSync(appPath, "utf8");
const home = fs.readFileSync(homePath, "utf8");
const inkFx = fs.readFileSync(inkFxPath, "utf8");
const configStore = fs.readFileSync(configPath, "utf8");
const slider = fs.readFileSync(sliderPath, "utf8");
const drawer = fs.readFileSync(drawerPath, "utf8");
const row = fs.readFileSync(rowPath, "utf8");
const theme = fs.readFileSync(themePath, "utf8");
const systemStore = fs.readFileSync(systemStorePath, "utf8");
const rightDock = fs.readFileSync(rightDockPath, "utf8");

assert.equal(chat.includes("openStreamMessageIdBySystem"), true, "Chat must bind streaming placeholder by openStreamMessageIdBySystem");
assert.equal(chat.includes("right: clamp(10px, var(--live2d-safe-right), 260px);"), true, "Chat scrollbar must honor live2d safe-right clamp");
assert.equal(chat.includes("padding-right: calc(12px + var(--live2d-safe-right));"), false, "Chat content should not be squeezed by safe-right");
assert.equal(chat.includes(":size=\"6\""), true, "Chat scrollbar size should be slim");
assert.equal(chat.includes("() => systemStore.currentSystemId"), true, "Chat must react to system switch for follow-scroll");
assert.equal(composer.includes("max-width: var(--chat-max-w);"), true, "Composer must share chat max width token");
assert.equal(composer.includes(".pill-mode {\n  flex: 0 0 auto;"), true, "Composer mode dropdown should not be squeezed out");
assert.equal(flow.includes("openStreamMessageIdBySystem"), true, "Flow chips must track active stream message");

assert.equal(globalCss.includes("--chat-max-w: 1230px;"), true, "Global chat max width should stay widened");
assert.equal(globalCss.includes("--shell-max-w: 1230px;"), true, "Shell width should stay widened");
assert.equal(globalCss.includes(".bg-photo::before"), true, "Background must provide dopamine overlay hook");
assert.equal(globalCss.includes(".bg-scanline {\n  position: fixed;\n  inset: 0;\n  z-index: -2;"), true, "Scanline should stay below ink layer");

assert.equal(live2d.includes("const chatPanel = document.querySelector(\".panel.chat\");"), true, "Live2D safe-right must compute against chat panel");
assert.equal(live2d.includes("[Live2D][safe-right]"), true, "Live2D safe-right diagnostics should stay enabled");

assert.equal(app.includes("[BG][vars]"), true, "App should keep background diagnostics");
assert.equal(app.includes('style.setProperty("--chat-window-alpha"'), true, "App should map chat alpha token");
assert.equal(app.includes('style.setProperty("--bg-overlay"'), true, "App should map background overlay token");
assert.equal(app.includes('let uiRowBg = "rgba(0, 0, 0, 0.16)";'), true, "Default row background should be black tone");
assert.equal(app.includes('let uiHdrBg = "rgba(12, 14, 22, 0.88)";'), true, "Default header background should be black tone");
assert.equal(app.includes("pickDopaminePalette(colorwaySeed, colorwayVariant)"), true, "Palette selection should use seed+variant");
assert.equal(app.includes("const colorwayIntensity ="), false, "Unneeded colorway intensity slider code should be removed");
assert.equal(app.includes("const colorwaySpeed ="), false, "Unneeded colorway speed slider code should be removed");

assert.equal(home.includes('class="side-veil'), false, "Home must not render side veil overlays");
assert.equal(home.includes(".side-veil"), false, "Home must not define side veil styles");

assert.equal(configStore.includes("background_blur: 10"), true, "Background blur default should be 10");
assert.equal(configStore.includes("background_blur) || 10"), true, "Background blur fallback should be 10");
assert.equal(configStore.includes("inkfx_intensity: 1.2"), true, "Ink intensity default should stay 1.2");
assert.equal(configStore.includes("colorway_mode: \"default\""), true, "Default colorway mode should remain default");
assert.equal(configStore.includes("colorway_seed: 202"), true, "Colorway seed should stay 202");
assert.equal(configStore.includes("colorway_variant: 0"), true, "Colorway variant state should exist");
assert.equal(configStore.includes("colorway_intensity"), false, "Config should not keep unneeded colorway intensity");
assert.equal(configStore.includes("colorway_speed"), false, "Config should not keep unneeded colorway speed");

assert.equal(inkFx.includes("const count = 3 + Math.floor(Math.random() * 3);"), true, "Ink effect should keep denser blob spawn");

assert.equal(slider.includes("width: 96px;"), true, "Drawer sliders should be narrower");
assert.equal(slider.includes("height: 18px;"), true, "Drawer sliders should be slimmer");
assert.equal(slider.includes("accent-color: var(--slider-accent"), true, "Slider accent should stay theme-driven");
assert.equal(systemStore.includes("smartsisi_last_system_id_v1"), true, "Current system id should persist across reload");
assert.equal(systemStore.includes("window.addEventListener(\"storage\""), true, "History store should listen storage events for multi-window sync");
assert.equal(systemStore.includes("persistCurrentSystem"), true, "System store should persist current system");
assert.equal(rightDock.includes("transition: width 260ms cubic-bezier"), true, "Right dock width easing should be smooth and stable");
assert.equal(rightDock.includes("will-change: width;"), true, "Right dock should hint width animation for stability");
assert.equal(globalCss.includes("::-webkit-scrollbar { width: 10px; height: 10px; }"), true, "Global scrollbar should be narrowed");

assert.equal(drawer.includes("value=\"dopamine202\""), true, "Appearance panel should keep dopamine202 mode");
assert.equal(drawer.includes("cycleDopaminePalette"), true, "Appearance panel should keep one-click palette cycle action");
assert.equal(drawer.includes("colorway_intensity"), false, "Appearance panel should remove unneeded colorway intensity slider");
assert.equal(drawer.includes("colorway_speed"), false, "Appearance panel should remove unneeded colorway speed slider");
assert.equal(drawer.includes(':step="0.1"'), true, "Appearance panel should keep finer blur slider step");

assert.equal(row.includes("background: var(--ui-row-bg);"), true, "Setting rows should use unified token background");
assert.equal(theme.includes('primaryColor: "var(--theme-primary)"'), true, "Theme overrides should keep runtime primary token");

assert.equal(composer.includes("stroke: rgba(172, 180, 196, 0.86);"), true, "Composer icons should have gray stroke to avoid visual occlusion");
assert.equal(flow.includes("drop-shadow(0 0 0.8px rgba(172, 180, 196, 0.86))"), true, "Flow icons should have gray outline shadow");
