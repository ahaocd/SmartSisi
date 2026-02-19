import { onBeforeUnmount, onMounted, ref } from "vue";

export function useMediaQuery(query) {
  const matches = ref(false);
  let mql = null;
  let onChange = null;

  onMounted(() => {
    try {
      mql = window.matchMedia(query);
      matches.value = !!mql.matches;
      onChange = (e) => {
        matches.value = !!e.matches;
      };
      if (mql.addEventListener) mql.addEventListener("change", onChange);
      else mql.addListener(onChange);
    } catch {
      matches.value = false;
    }
  });

  onBeforeUnmount(() => {
    try {
      if (!mql || !onChange) return;
      if (mql.removeEventListener) mql.removeEventListener("change", onChange);
      else mql.removeListener(onChange);
    } catch {}
    mql = null;
    onChange = null;
  });

  return matches;
}

