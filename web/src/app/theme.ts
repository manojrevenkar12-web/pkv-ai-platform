/** Numbers the components share. Colours and spacing live in tokens.css. */
export const motion = {
  grow: { duration: 0.45, ease: [0.2, 0.7, 0.2, 1] as const },
  open: { duration: 0.22 },
  stagger: 0.006,
};
export const routingOrder = ["classical_static", "platform_no_monitor", "platform"] as const;
export const routingVar: Record<string, string> = { classical_static: "--other", platform_no_monitor: "--other-strong", platform: "--platform" };
export const useCaseOrder = ["routing", "invoices", "assist"] as const;
export const chart = { width: 720, height: 200, pad: 28, low: 0.9 };
export const skeletonRows = 4;
export const skeletonStep = 12;
export const pct = (x: number, d = 1) => `${(x * 100).toFixed(d)}%`;
export const eur = (x: number, d = 0) => x.toLocaleString("en-IE", { style: "currency", currency: "EUR", maximumFractionDigits: d, minimumFractionDigits: d });
