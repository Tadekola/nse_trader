"use client";

import { useEffect, useRef } from "react";
import type { TimeseriesResponse, ReportingMode } from "@/api/types";

interface Props {
  data: TimeseriesResponse;
  reporting: ReportingMode;
}

export function TimeseriesChart({ data, reporting }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<any>(null);

  useEffect(() => {
    if (!containerRef.current || data.series.length === 0) return;

    let chart: any;

    async function init() {
      const lc = await import("lightweight-charts");

      // Dispose previous chart
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
      }

      chart = lc.createChart(containerRef.current!, {
        layout: {
          background: { color: "transparent" },
          textColor: "#94a3b8",
          fontSize: 11,
          fontFamily: "JetBrains Mono, monospace",
        },
        grid: {
          vertLines: { color: "#1e293b" },
          horzLines: { color: "#1e293b" },
        },
        crosshair: {
          mode: lc.CrosshairMode.Normal,
          vertLine: { color: "#334155", width: 1, style: lc.LineStyle.Dashed },
          horzLine: { color: "#334155", width: 1, style: lc.LineStyle.Dashed },
        },
        rightPriceScale: {
          borderColor: "#1e293b",
        },
        timeScale: {
          borderColor: "#1e293b",
          timeVisible: false,
        },
        handleScroll: { vertTouchDrag: false },
      });

      chartRef.current = chart;

      // Value area series
      const areaSeries = chart.addAreaSeries({
        lineColor: "#3b82f6",
        topColor: "rgba(59, 130, 246, 0.2)",
        bottomColor: "rgba(59, 130, 246, 0.02)",
        lineWidth: 2,
        priceFormat: {
          type: "custom",
          formatter: (price: number) => {
            if (reporting === "USD") return `$${price.toFixed(0)}`;
            return `₦${(price / 1000).toFixed(0)}K`;
          },
        },
      });

      const seriesData = data.series
        .filter((p) => p.value != null)
        .map((p) => ({
          time: p.date as string,
          value: p.value as number,
        }));

      areaSeries.setData(seriesData);

      // Fit content
      chart.timeScale().fitContent();

      // Handle resize
      const ro = new ResizeObserver(() => {
        if (containerRef.current && chart) {
          chart.applyOptions({
            width: containerRef.current.clientWidth,
            height: containerRef.current.clientHeight,
          });
        }
      });
      ro.observe(containerRef.current!);

      return () => {
        ro.disconnect();
      };
    }

    init();

    return () => {
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
      }
    };
  }, [data, reporting]);

  return <div ref={containerRef} className="w-full h-full" />;
}
