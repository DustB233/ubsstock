"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { StockPricePoint } from "@/lib/types";
import { formatCurrency, formatDate, formatCompactNumber } from "@/lib/formatters";

function PriceTooltip({
  active,
  payload,
  label,
  currency,
}: {
  active?: boolean;
  payload?: Array<{ value?: number; payload?: { volume: number | null } }>;
  label?: string;
  currency: string;
}) {
  if (!active || !payload?.length) {
    return null;
  }

  const point = payload[0];
  const price = typeof point.value === "number" ? point.value : null;
  const volume = point.payload?.volume ?? null;

  return (
    <div className="rounded-[1.2rem] border border-white/10 bg-slate-950/90 px-4 py-3 shadow-[0_12px_30px_rgba(0,0,0,0.35)] backdrop-blur">
      <p className="text-xs uppercase tracking-[0.22em] text-slate-400">
        {formatDate(label ?? null)}
      </p>
      <p className="mt-2 text-base font-medium text-white">{formatCurrency(price, currency)}</p>
      <p className="mt-1 text-sm text-slate-300">Volume {formatCompactNumber(volume, 1)}</p>
    </div>
  );
}

export function StockPriceChart({
  points,
  currency,
}: {
  points: StockPricePoint[];
  currency: string;
}) {
  if (points.length === 0) {
    return (
      <div className="flex h-[320px] items-center justify-center rounded-[1.6rem] border border-white/8 bg-slate-950/45 text-sm text-slate-400">
        No price history is available for this range.
      </div>
    );
  }

  const data = points.map((point) => ({
    date: point.trading_date,
    close: point.close,
    volume: point.volume,
  }));

  return (
    <div className="h-[320px] rounded-[1.6rem] border border-white/8 bg-slate-950/40 p-4">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 12, right: 16, left: -16, bottom: 0 }}>
          <defs>
            <linearGradient id="priceArea" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor="rgba(251,191,36,0.85)" />
              <stop offset="100%" stopColor="rgba(251,191,36,0)" />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="rgba(255,255,255,0.08)" vertical={false} />
          <XAxis
            dataKey="date"
            axisLine={false}
            tickLine={false}
            tick={{ fill: "rgba(226,232,240,0.72)", fontSize: 11 }}
            tickFormatter={(value: string) =>
              formatDate(value, { month: "short", day: "numeric" })
            }
            minTickGap={24}
          />
          <YAxis
            axisLine={false}
            tickLine={false}
            tick={{ fill: "rgba(226,232,240,0.72)", fontSize: 11 }}
            tickFormatter={(value: number) => formatCurrency(value, currency, 0)}
            width={72}
          />
          <Tooltip content={<PriceTooltip currency={currency} />} />
          <Area
            type="monotone"
            dataKey="close"
            stroke="rgba(251,191,36,0.95)"
            strokeWidth={2}
            fill="url(#priceArea)"
            dot={false}
            activeDot={{ r: 4, fill: "#fbbf24", stroke: "#0f172a" }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

