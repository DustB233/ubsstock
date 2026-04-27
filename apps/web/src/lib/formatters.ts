export function formatNumber(value: number | null, digits = 2): string {
  return value === null ? "—" : value.toFixed(digits);
}

export function formatPercent(value: number | null, digits = 1): string {
  if (value === null) {
    return "—";
  }

  const percentage = value * 100;
  const prefix = percentage > 0 ? "+" : "";
  return `${prefix}${percentage.toFixed(digits)}%`;
}

export function formatScore(value: number | null): string {
  return value === null ? "—" : value.toFixed(1);
}

export function formatCompactNumber(value: number | null, digits = 1): string {
  if (value === null) {
    return "—";
  }

  return new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: digits,
  }).format(value);
}

export function formatCurrency(
  value: number | null,
  currency: string,
  digits = 2,
): string {
  if (value === null) {
    return "—";
  }

  try {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency,
      maximumFractionDigits: digits,
    }).format(value);
  } catch {
    return `${value.toFixed(digits)} ${currency}`;
  }
}

export function formatCompactCurrency(
  value: number | null,
  currency: string,
  digits = 1,
): string {
  if (value === null) {
    return "—";
  }

  try {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency,
      notation: "compact",
      maximumFractionDigits: digits,
    }).format(value);
  } catch {
    return `${formatCompactNumber(value, digits)} ${currency}`;
  }
}

export function formatDate(
  value: string | null,
  options: Intl.DateTimeFormatOptions = {
    month: "short",
    day: "numeric",
    year: "numeric",
  },
): string {
  if (!value) {
    return "—";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat("en-US", options).format(date);
}

export function sentimentTone(label: string | null): "positive" | "negative" | "neutral" {
  if (label === "POSITIVE") {
    return "positive";
  }

  if (label === "NEGATIVE") {
    return "negative";
  }

  return "neutral";
}

