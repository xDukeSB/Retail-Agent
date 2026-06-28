"use client";

import { FileText, CalendarDays, Download, Activity, Clock, Percent, TrendingUp, Lightbulb, CheckCircle2 } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/lib/api";
import { Skeleton, EmptyState } from "@/components/ui/index";
import { formatDuration } from "@/lib/utils";

export default function ReportsPage() {
  const { data: dailyReport, isLoading: isDailyLoading } = useQuery({ queryKey: ["report", "daily"], queryFn: () => api.getReportData("daily") });
  const { data: weeklyReport, isLoading: isWeeklyLoading } = useQuery({ queryKey: ["report", "weekly"], queryFn: () => api.getReportData("weekly") });
  const { data: monthlyReport, isLoading: isMonthlyLoading } = useQuery({ queryKey: ["report", "monthly"], queryFn: () => api.getReportData("monthly") });

  const getStats = (reportData: any) => ({
    v: reportData?.visitors ?? 0,
    c: reportData?.conversion_rate ? `${(reportData.conversion_rate * 100).toFixed(1)}%` : "0%",
    d: reportData?.avg_dwell_time ? formatDuration(reportData.avg_dwell_time) : "0m",
    p: reportData?.peak_hour ?? "N/A",
    cv: reportData?.conversions ?? 0
  });

  const dailyStats = getStats(dailyReport);
  const weeklyStats = getStats(weeklyReport);
  const monthlyStats = getStats(monthlyReport);

  const [downloading, setDownloading] = useState<string | null>(null);

  const handleDownload = (id: string, url: string) => {
    setDownloading(id);
    window.open(url, "_blank");
    setTimeout(() => setDownloading(null), 2000);
  };

  return (
    <div className="max-w-[1600px] mx-auto pb-10 space-y-6">
      
      {/* Top Section: Generate Report */}
      <div className="bg-white border border-gray-200 rounded-xl p-6 shadow-sm">
        <div className="flex items-center gap-2 mb-6">
          <FileText className="w-4 h-4 text-gray-500" />
          <h2 className="text-sm font-bold text-gray-900">Generate Report</h2>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {[
            { 
              title: "Daily Report", subtitle: "Today's performance summary", stats: dailyStats, loading: isDailyLoading,
              pdf: api.exportPDFUrl("daily", 1), excel: api.exportExcelUrl("daily", 1), csv: api.exportCSVUrl("daily", 1)
            },
            { 
              title: "Weekly Report", subtitle: "Last 7 days trends", stats: weeklyStats, loading: isWeeklyLoading,
              pdf: api.exportPDFUrl("weekly", 7), excel: api.exportExcelUrl("weekly", 7), csv: api.exportCSVUrl("weekly", 7)
            },
            { 
              title: "Monthly Report", subtitle: "Monthly business intelligence", stats: monthlyStats, loading: isMonthlyLoading,
              pdf: api.exportPDFUrl("monthly", 30), excel: api.exportExcelUrl("monthly", 30), csv: api.exportCSVUrl("monthly", 30)
            }
          ].map(r => (
            <div key={r.title} className="border border-gray-200 rounded-xl p-5 bg-gray-50/50">
              <div className="flex items-start justify-between mb-6">
                <div>
                  <h3 className="text-sm font-bold text-gray-900">{r.title}</h3>
                  <p className="text-[11px] text-gray-500 mt-0.5">{r.subtitle}</p>
                </div>
                <CalendarDays className="w-4 h-4 text-gray-400" />
              </div>
              
              {r.loading ? (
                <Skeleton className="h-16 w-full mb-6" />
              ) : (
                <div className="grid grid-cols-2 gap-4 mb-6">
                  <div>
                    <div className="text-[9px] font-bold text-gray-400 uppercase tracking-wider mb-1">Visitors</div>
                    <div className="text-sm font-bold text-gray-900">{r.stats.v}</div>
                  </div>
                  <div>
                    <div className="text-[9px] font-bold text-gray-400 uppercase tracking-wider mb-1">Conv.</div>
                    <div className="text-sm font-bold text-gray-900">{r.stats.c}</div>
                  </div>
                  <div>
                    <div className="text-[9px] font-bold text-gray-400 uppercase tracking-wider mb-1">Dwell</div>
                    <div className="text-sm font-bold text-gray-900">{r.stats.d}</div>
                  </div>
                  <div>
                    <div className="text-[9px] font-bold text-gray-400 uppercase tracking-wider mb-1">Peak</div>
                    <div className="text-sm font-bold text-gray-900">{r.stats.p}</div>
                  </div>
                </div>
              )}

              <div className="grid grid-cols-3 gap-2">
                <button 
                  onClick={() => handleDownload(`${r.title}-pdf`, r.pdf)}
                  className="py-2 rounded-lg bg-emerald-600 text-white text-[11px] font-bold shadow-sm hover:bg-emerald-700 transition-colors flex items-center justify-center"
                >
                  {downloading === `${r.title}-pdf` ? "..." : "PDF"}
                </button>
                <button 
                  onClick={() => handleDownload(`${r.title}-excel`, r.excel)}
                  className="py-2 rounded-lg bg-white border border-gray-200 text-gray-700 text-[11px] font-bold shadow-sm hover:bg-gray-50 transition-colors flex items-center justify-center"
                >
                  {downloading === `${r.title}-excel` ? "..." : "Excel"}
                </button>
                <button 
                  onClick={() => handleDownload(`${r.title}-csv`, r.csv)}
                  className="py-2 rounded-lg bg-white border border-gray-200 text-gray-700 text-[11px] font-bold shadow-sm hover:bg-gray-50 transition-colors flex items-center justify-center"
                >
                  {downloading === `${r.title}-csv` ? "..." : "CSV"}
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Middle Section: Daily Report Preview */}
      <div className="bg-white border border-gray-200 rounded-xl p-6 shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6 pb-6 border-b border-gray-100">
          <div>
            <h2 className="text-sm font-bold text-gray-900">Daily Business Report Preview</h2>
            <p className="text-[11px] text-gray-500 mt-0.5">{new Date().toLocaleDateString()} · {dailyStats.v} visitors</p>
          </div>
          <div className="flex items-center gap-1.5 px-3 py-1 bg-emerald-50 border border-emerald-100 rounded-full text-[10px] font-bold text-emerald-600">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
            Auto-generated
          </div>
        </div>

        {isDailyLoading ? (
           <Skeleton className="w-full h-64" />
        ) : dailyStats.v === 0 ? (
           <EmptyState icon={FileText} title="No Data Available" description="No visitors recorded for today yet." />
        ) : (
          <div className="flex flex-col xl:flex-row gap-8">
            {/* Left Column */}
            <div className="flex-1 space-y-6">
              
              {/* Visitor Trends */}
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <Activity className="w-3.5 h-3.5 text-gray-400" />
                  <h3 className="text-xs font-bold text-gray-900">Visitor Trends</h3>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="p-4 border border-gray-100 rounded-lg bg-gray-50/50">
                    <div className="text-[9px] font-bold text-gray-400 uppercase tracking-wider mb-1">Today</div>
                    <div className="flex items-end gap-2">
                      <span className="text-lg font-bold text-gray-900">{dailyStats.v}</span>
                    </div>
                  </div>
                  <div className="p-4 border border-gray-100 rounded-lg bg-gray-50/50">
                    <div className="text-[9px] font-bold text-gray-400 uppercase tracking-wider mb-1">Peak Hour</div>
                    <div className="text-lg font-bold text-gray-900">{dailyStats.p}</div>
                  </div>
                </div>
              </div>

              {/* Dwell Time */}
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <Clock className="w-3.5 h-3.5 text-gray-400" />
                  <h3 className="text-xs font-bold text-gray-900">Dwell Time Analysis</h3>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="p-4 border border-gray-100 rounded-lg bg-gray-50/50">
                    <div className="text-[9px] font-bold text-gray-400 uppercase tracking-wider mb-1">Average</div>
                    <div className="text-sm font-bold text-gray-900">{dailyStats.d}</div>
                  </div>
                </div>
              </div>

              {/* Conversion */}
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <Percent className="w-3.5 h-3.5 text-gray-400" />
                  <h3 className="text-xs font-bold text-gray-900">% Conversion Trends</h3>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="p-4 border border-gray-100 rounded-lg bg-gray-50/50">
                    <div className="text-[9px] font-bold text-gray-400 uppercase tracking-wider mb-1">Conversion Rate</div>
                    <div className="flex items-end gap-2">
                      <span className="text-sm font-bold text-gray-900">{dailyStats.c}</span>
                    </div>
                  </div>
                  <div className="p-4 border border-gray-100 rounded-lg bg-gray-50/50">
                    <div className="text-[9px] font-bold text-gray-400 uppercase tracking-wider mb-1">Confirmed</div>
                    <div className="text-sm font-bold text-gray-900">{dailyStats.cv}</div>
                  </div>
                </div>
              </div>

            </div>

            {/* Right Column */}
            <div className="flex-1 space-y-6">
              
              {/* Peak Hours CSS Chart */}
              <div className="border border-gray-200 rounded-xl p-5">
                <div className="flex items-center gap-2 mb-5">
                  <TrendingUp className="w-3.5 h-3.5 text-gray-400" />
                  <h3 className="text-xs font-bold text-gray-900">Peak Hours</h3>
                </div>
                <div className="space-y-3 text-xs text-gray-500">
                  Daily peak hour is observed at <strong>{dailyStats.p}</strong>. 
                  (Hour-by-hour distribution will be available once more data is collected).
                </div>
              </div>

            </div>
          </div>
        )}
      </div>

      {/* Bottom Section: Generated Reports Table */}
      <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-6 overflow-x-auto">
        <div className="mb-6">
          <h2 className="text-sm font-bold text-gray-900">Generated Reports</h2>
          <p className="text-[11px] text-gray-500 mt-0.5">Automated historic reports</p>
        </div>
        
        <EmptyState icon={FileText} title="No History Yet" description="Generated reports will appear here automatically." />
        
      </div>

    </div>
  );
}
