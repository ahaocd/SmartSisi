export function useThemeOverrides() {
  return {
    common: {
      primaryColor: "var(--theme-primary)",
      primaryColorHover: "var(--theme-primary-hover)",
      primaryColorPressed: "var(--theme-primary-pressed)",
      borderRadius: "var(--r-panel)",
      fontFamily: "var(--font-ui)"
    },
    Card: {
      color: "rgba(12, 14, 22, 0.78)",
      borderColor: "rgba(255, 255, 255, 0.08)"
    },
    Drawer: {
      color: "rgba(12, 14, 22, 0.78)"
    },
    Button: {
      borderRadiusTiny: "10px",
      borderRadiusSmall: "10px",
      borderRadiusMedium: "12px",
      borderRadiusLarge: "12px"
    },
    Input: {
      borderRadius: "12px"
    },
    Select: {
      borderRadius: "12px"
    }
  };
}
