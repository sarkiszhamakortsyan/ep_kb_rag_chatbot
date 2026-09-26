export const formatDateTime = (iso: string) =>
  new Date(iso).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });

export const formatSeconds = (ms: number | null) =>
  ms === null ? "–" : `${(ms / 1000).toFixed(1)} s`;

export const formatNumber = (n: number) => n.toLocaleString();

/** The inclusive UTC date range for the last `days` days, as the API expects it. */
export function lastDays(days: number): { from: string; to: string } {
  const to = new Date();
  const from = new Date(to.getTime() - (days - 1) * 86_400_000);
  return {
    from: from.toISOString().slice(0, 10),
    to: to.toISOString().slice(0, 10),
  };
}

/** Small amounts keep 4 decimals (a question costs about a cent). */
export const formatUsd = (usd: number) =>
  usd === 0
    ? "$0"
    : usd < 1
      ? `$${usd.toFixed(4)}`
      : `$${usd.toLocaleString(undefined, { maximumFractionDigits: 2, minimumFractionDigits: 2 })}`;
