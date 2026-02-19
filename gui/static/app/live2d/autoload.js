(function () {
  // Load live2d-widget from local assets to avoid CDN dependency.
  // Works in dev (/) and build base (/static/app/).

  function getBaseUrl() {
    const script = document.currentScript;
    if (script && script.src) {
      return script.src.replace(/\/live2d\/autoload\.js(\?.*)?$/, "/");
    }
    return "/";
  }

  const baseUrl = getBaseUrl();
  const live2dLocalBase = baseUrl + "live2d/vendor/";
  const DEFAULT_MODEL_ID = "24"; // Potion-Maker/Tia in model_list.json
  const DEFAULT_TEXTURE_ID = "0";
  const DEFAULT_MODEL_NAME = "Potion-Maker/Tia";

  function loadExternal(url, type) {
    return new Promise((resolve, reject) => {
      let tag;
      if (type === "css") {
        tag = document.createElement("link");
        tag.rel = "stylesheet";
        tag.href = url;
      } else {
        tag = document.createElement("script");
        tag.src = url;
      }
      tag.onload = () => resolve();
      tag.onerror = () => reject(new Error("Failed to load: " + url));
      document.head.appendChild(tag);
    });
  }

  Promise.all([
    loadExternal(live2dLocalBase + "waifu.css", "css"),
    loadExternal(live2dLocalBase + "live2d.min.js", "js"),
    loadExternal(live2dLocalBase + "waifu-tips.js", "js")
  ])
    .then(() => {
      if (typeof initWidget !== "function") return;

      // Expose Live2D model instance for mouth sync control.
      try {
        const L2D = window.Live2DModelWebGL;
        if (L2D && !L2D.__smartsisi_patched) {
          const orig = L2D.loadModel;
          L2D.loadModel = function (buf) {
            const model = orig.call(this, buf);
            try {
              window.__live2dModel = model;
              if (typeof window.__live2dMouthValue !== "number") window.__live2dMouthValue = 0;
              if (model && typeof model.update === "function" && !model.__smartsisi_mouth_patch) {
                const origUpdate = model.update;
                model.update = function () {
                  const res = origUpdate.apply(this, arguments);
                  try {
                    const v = window.__live2dMouthValue;
                    if (typeof v === "number") {
                      const vv = Math.max(0, Math.min(1, v));
                      const ids = [
                        "PARAM_MOUTH_OPEN_Y",
                        "PARAM_MOUTH_OPEN",
                        "ParamMouthOpenY",
                        "ParamMouthOpen",
                        "MOUTH_OPEN_Y",
                        "MOUTH_OPEN"
                      ];
                      for (const id of ids) {
                        try {
                          this.setParamFloat(id, vv);
                        } catch {}
                      }
                    }
                  } catch {}
                  return res;
                };
                model.__smartsisi_mouth_patch = true;
              }
            } catch {}
            return model;
          };
          L2D.__smartsisi_patched = true;
        }
      } catch {}

      // We hide the widget toggle/tools via CSS, so force "shown" every load.
      try {
        localStorage.removeItem("waifu-display");
      } catch {}

      // Force a deterministic default model on every load so motion/lipsync
      // behavior is predictable across machines and prior sessions.
      try {
        localStorage.setItem("modelId", DEFAULT_MODEL_ID);
        localStorage.setItem("modelTexturesId", DEFAULT_TEXTURE_ID);
        localStorage.setItem("smartsisi_live2d_default_model", DEFAULT_MODEL_NAME);
      } catch {}

      initWidget({
        waifuPath: baseUrl + "live2d/waifu-tips.json",
        cdnPath: baseUrl + "live2d/models/",
        // Keep tools off in-app; we render our own UI and hide the widget tips/tools via CSS.
        tools: ["switch-model", "switch-texture"]
      });
    })
    .catch(() => {});
})();
