"use client";

import { useEffect, useState } from "react";
import type { NicheListResponse } from "@/lib/types";
import { getNiches, deleteNiche } from "@/lib/api";
import { IconTarget, IconSearch } from "@/components/icons";

export default function ResearchPage() {
  const [data, setData] = useState<NicheListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchNiches = () => {
    setLoading(true);
    getNiches()
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchNiches();
  }, []);

  const handleDelete = async (id: string, keyword: string) => {
    if (!confirm(`Delete niche "${keyword}"?`)) return;
    try {
      await deleteNiche(id);
      fetchNiches();
    } catch (e) {
      alert(`Failed: ${(e as Error).message}`);
    }
  };

  const getDemandColor = (level: string | null) => {
    switch (level) {
      case "VALIDATED":
        return "bg-green-100 text-green-700";
      case "MODERATE":
        return "bg-yellow-100 text-yellow-700";
      case "NO_DEMAND":
        return "bg-red-100 text-red-700";
      case "BRAND_LOCKED":
        return "bg-purple-100 text-purple-700";
      default:
        return "bg-gray-100 text-gray-600";
    }
  };

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Niche Research</h1>
          <p className="text-sm text-slate-500 mt-1">
            BSR-validated market opportunities for Amazon KDP
          </p>
        </div>
        <button
          disabled
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white opacity-50 cursor-not-allowed"
          title="Coming in Phase 6"
        >
          Run Research Scan
        </button>
      </div>

      {/* Info Banner */}
      <div className="rounded-xl border border-blue-200 bg-blue-50 p-4 mb-6">
        <div className="flex items-start gap-3">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-blue-100">
            <IconTarget className="w-4 h-4 text-blue-600" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-blue-800">
              BSR Demand Validation
            </h3>
            <p className="text-xs text-blue-600 mt-1">
              Every niche is validated against real Amazon Best Sellers Rank
              data. Only niches with BSR &lt; 100,000 (indicating actual sales)
              are approved. Low competition alone is NOT enough — it often means
              no demand.
            </p>
          </div>
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-12">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-500 border-t-transparent" />
        </div>
      ) : error ? (
        <div className="text-center py-12 text-red-500">{error}</div>
      ) : !data || data.niches.length === 0 ? (
        <div className="text-center py-16">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-slate-100">
            <IconSearch className="w-6 h-6 text-slate-400" />
          </div>
          <h2 className="text-lg font-semibold text-slate-900">No niches researched yet</h2>
          <p className="text-sm text-slate-500 mt-1">
            The research engine will scan Amazon for profitable book niches
          </p>
          <p className="text-xs text-slate-400 mt-2">
            Autonomous research runs weekly (Phase 6) or can be triggered
            manually
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {data.niches.map((niche) => (
            <div
              key={niche.id}
              className="rounded-xl border border-slate-200 bg-white p-5"
            >
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="text-sm font-semibold text-slate-900">{niche.keyword}</h3>
                  <span
                    className={`mt-1 inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${getDemandColor(niche.data.demand_level)}`}
                  >
                    {niche.data.demand_level || "Unknown"}
                  </span>
                </div>
                {niche.data.opportunity_score !== null && (
                  <div className="text-right">
                    <p className="text-2xl font-bold text-blue-600">
                      {niche.data.opportunity_score.toFixed(0)}
                    </p>
                    <p className="text-[10px] text-slate-400 uppercase">Score</p>
                  </div>
                )}
              </div>

              <div className="mt-3 grid grid-cols-3 gap-3 text-center">
                {niche.data.top_bsr && (
                  <div>
                    <p className="text-xs text-slate-400">Top BSR</p>
                    <p className="text-sm font-semibold text-slate-900">
                      #{niche.data.top_bsr.toLocaleString()}
                    </p>
                  </div>
                )}
                {niche.data.estimated_monthly_sales && (
                  <div>
                    <p className="text-xs text-slate-400">Est. Sales/mo</p>
                    <p className="text-sm font-semibold text-slate-900">
                      {niche.data.estimated_monthly_sales.toLocaleString()}
                    </p>
                  </div>
                )}
                {niche.data.competition_level && (
                  <div>
                    <p className="text-xs text-slate-400">Competition</p>
                    <p className="text-sm font-semibold text-slate-900">
                      {niche.data.competition_level}
                    </p>
                  </div>
                )}
              </div>

              {niche.data.analysis_notes && (
                <p className="mt-3 text-xs text-slate-500 line-clamp-2">
                  {niche.data.analysis_notes}
                </p>
              )}

              {niche.data.rejection_reason && (
                <div className="mt-3 rounded-lg bg-red-50 px-3 py-2">
                  <p className="text-xs text-red-600">
                    Rejected: {niche.data.rejection_reason}
                  </p>
                </div>
              )}

              <div className="mt-3 flex items-center justify-between border-t border-slate-100 pt-3">
                <span className="text-[10px] text-slate-400">
                  {new Date(niche.created_at).toLocaleDateString()}
                </span>
                <button
                  onClick={() => handleDelete(niche.id, niche.keyword)}
                  className="text-xs text-red-400 hover:text-red-600"
                >
                  Remove
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
