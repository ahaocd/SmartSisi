<script setup>
import { computed } from "vue";

const props = defineProps({
  modelValue: { type: Number, default: 0 },
  min: { type: Number, default: 0 },
  max: { type: Number, default: 100 },
  step: { type: Number, default: 1 },
  format: { type: Function, default: null },
  disabled: { type: Boolean, default: false },
  ariaLabel: { type: String, default: "slider" }
});

const emit = defineEmits(["update:modelValue"]);

const valueText = computed(() => {
  if (typeof props.format === "function") return props.format(props.modelValue);
  return String(props.modelValue);
});

const sliderPercent = computed(() => {
  const min = Number(props.min);
  const max = Number(props.max);
  const val = Number(props.modelValue);
  if (!Number.isFinite(min) || !Number.isFinite(max) || max <= min || !Number.isFinite(val)) return 0;
  const p = (val - min) / (max - min);
  return Math.max(0, Math.min(1, p));
});

const sliderStyle = computed(() => ({
  "--slider-percent": `${(sliderPercent.value * 100).toFixed(2)}%`
}));

function onInput(e) {
  const n = Number(e?.target?.value);
  emit("update:modelValue", Number.isFinite(n) ? n : props.modelValue);
}
</script>

<template>
  <div class="wrap" :data-disabled="disabled ? '1' : '0'">
    <input
      class="slider"
      type="range"
      :min="min"
      :max="max"
      :step="step"
      :value="modelValue"
      :disabled="disabled"
      :style="sliderStyle"
      :aria-label="ariaLabel"
      :aria-valuemin="min"
      :aria-valuemax="max"
      :aria-valuenow="modelValue"
      @input="onInput"
      @change="onInput"
    />
    <div class="val">{{ valueText }}</div>
  </div>
</template>

<style scoped>
.wrap {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.val {
  min-width: 52px;
  text-align: right;
  font-family: var(--font-pixel);
  font-size: 12px;
  color: rgba(255, 255, 255, 0.88);
}

.slider {
  width: 96px;
  accent-color: var(--slider-accent, rgba(127, 223, 255, 0.85));
  height: 18px;
  background: transparent;
  cursor: pointer;
  -webkit-appearance: none;
  appearance: none;
  outline: none;
  border-radius: 999px;
}

.slider:disabled {
  cursor: not-allowed;
}

.slider:focus-visible {
  box-shadow: 0 0 0 2px rgba(127, 223, 255, 0.42);
}

.wrap[data-disabled="1"] {
  opacity: 0.55;
}

/* Track */
.slider::-webkit-slider-runnable-track {
  height: 5px;
  border-radius: var(--r-pill);
  border: 1px solid rgba(255, 255, 255, 0.28);
  background: linear-gradient(
    90deg,
    var(--slider-accent, rgba(127, 223, 255, 0.85)) 0%,
    var(--slider-accent, rgba(127, 223, 255, 0.85)) var(--slider-percent),
    rgba(255, 255, 255, 0.16) var(--slider-percent),
    rgba(255, 255, 255, 0.16) 100%
  );
  box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.22);
}
.slider::-moz-range-track {
  height: 5px;
  border-radius: var(--r-pill);
  border: 1px solid rgba(255, 255, 255, 0.28);
  background: rgba(255, 255, 255, 0.16);
  box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.22);
}
.slider::-moz-range-progress {
  height: 5px;
  border-radius: var(--r-pill);
  background: var(--slider-accent, rgba(127, 223, 255, 0.85));
}

/* Thumb */
.slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 12px;
  height: 12px;
  margin-top: -4px;
  border-radius: var(--r-pill);
  border: 1px solid rgba(255, 255, 255, 0.78);
  background: linear-gradient(180deg, rgba(224, 248, 255, 0.96) 0%, rgba(153, 226, 255, 0.95) 100%);
  box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.28), 0 0 10px rgba(127, 223, 255, 0.45);
}
.slider::-moz-range-thumb {
  width: 12px;
  height: 12px;
  border-radius: var(--r-pill);
  border: 1px solid rgba(255, 255, 255, 0.78);
  background: linear-gradient(180deg, rgba(224, 248, 255, 0.96) 0%, rgba(153, 226, 255, 0.95) 100%);
  box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.28), 0 0 10px rgba(127, 223, 255, 0.45);
}
</style>

