import React, { useState, useMemo, useEffect } from 'react';
import { CorrelationMatrixData, Position } from '../../types/trading';
import { computeCorrelationMatrix, classifyCorrelation, getCorrelationRiskGuidance } from '../../utils/correlation';
import { SUPPORTED_SYMBOLS } from '../../data/marketData';
import { safeFetchJson } from '../../utils/api';
import {
  Grid,
  TrendingUp,
  TrendingDown,
  ShieldAlert,
  Info,
  Layers,
  ArrowRightLeft,
  Sliders,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  Eye,
  Activity
} from 'lucide-react';

interface TradeCorrelationCardProps {
  selectedSymbol: string;
  onSelectSymbol: (symbol: string) => void;
  positions?: Position[];
}

export const TradeCorrelationCard: React.FC<TradeCorrelationCardProps> = ({
  selectedSymbol,
  onSelectSymbol,
  positions = []
}) => {
  const [lookbackDays, setLookbackDays] = useState<number>(3);
  const [viewMode, setViewMode] = useState<'focused' | 'matrix'>('focused');
  const [hoveredPair, setHoveredPair] = useState<{ symA: string; symB: string; val: number } | null>(null);
  const [selectedPairDetail, setSelectedPairDetail] = useState<{ symA: string; symB: string; val: number } | null>(null);
  const [correlationData, setCorrelationData] = useState<CorrelationMatrixData | null>(null);
  const [loading, setLoading] = useState<boolean>(false);

  const symbols = useMemo(() => SUPPORTED_SYMBOLS.map(s => s.symbol), []);

  // Compute or fetch correlation matrix whenever lookbackDays changes or positions update
  useEffect(() => {
    let isMounted = true;
    const loadCorrelation = async () => {
      setLoading(true);
      try {
        const clientFallback = computeCorrelationMatrix(symbols, lookbackDays, 'M15', positions);
        const data = await safeFetchJson<CorrelationMatrixData>(
          `/api/market-data/correlation?days=${lookbackDays}&timeframe=M15`,
          undefined,
          clientFallback
        );
        if (isMounted && data) {
          setCorrelationData(data);
        }
      } catch (err) {
        const clientData = computeCorrelationMatrix(symbols, lookbackDays, 'M15', positions);
        if (isMounted) setCorrelationData(clientData);
      } finally {
        if (isMounted) setLoading(false);
      }
    };

    loadCorrelation();
    return () => {
      isMounted = false;
    };
  }, [lookbackDays, symbols, positions]);

  // Selected symbol specific correlations against other symbols
  const selectedSymbolCorrelations = useMemo(() => {
    if (!correlationData || !correlationData.matrix[selectedSymbol]) return [];
    
    return symbols
      .filter(sym => sym !== selectedSymbol)
      .map(otherSym => {
        const val = correlationData.matrix[selectedSymbol]?.[otherSym] ?? 0;
        const classification = classifyCorrelation(val);
        const riskNote = getCorrelationRiskGuidance(selectedSymbol, otherSym, val, positions);
        return {
          symbol: otherSym,
          val,
          classification,
          riskNote
        };
      })
      .sort((a, b) => b.val - a.val); // sort highest to lowest
  }, [correlationData, selectedSymbol, symbols, positions]);

  // Helper color function for correlation coefficient
  const getCorrelationColor = (val: number, isSelected: boolean = false) => {
    if (val >= 0.70) {
      return {
        bg: isSelected ? 'bg-emerald-500 text-slate-950 font-bold' : 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40 hover:bg-emerald-500/30',
        text: 'text-emerald-400',
        pill: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
        badge: 'STRONG POSITIVE',
        barColor: 'bg-emerald-500'
      };
    } else if (val >= 0.30) {
      return {
        bg: isSelected ? 'bg-teal-500 text-slate-950 font-bold' : 'bg-teal-500/20 text-teal-300 border-teal-500/40 hover:bg-teal-500/30',
        text: 'text-teal-400',
        pill: 'bg-teal-500/20 text-teal-300 border-teal-500/30',
        badge: 'MODERATE POSITIVE',
        barColor: 'bg-teal-400'
      };
    } else if (val > -0.30) {
      return {
        bg: isSelected ? 'bg-slate-700 text-slate-100 font-bold' : 'bg-slate-800/60 text-slate-400 border-slate-700/60 hover:bg-slate-800',
        text: 'text-slate-400',
        pill: 'bg-slate-800 text-slate-400 border-slate-700',
        badge: 'UNCORRELATED',
        barColor: 'bg-slate-500'
      };
    } else if (val > -0.70) {
      return {
        bg: isSelected ? 'bg-amber-500 text-slate-950 font-bold' : 'bg-amber-500/20 text-amber-300 border-amber-500/40 hover:bg-amber-500/30',
        text: 'text-amber-400',
        pill: 'bg-amber-500/20 text-amber-300 border-amber-500/30',
        badge: 'MODERATE INVERSE',
        barColor: 'bg-amber-400'
      };
    } else {
      return {
        bg: isSelected ? 'bg-rose-500 text-slate-950 font-bold' : 'bg-rose-500/20 text-rose-300 border-rose-500/40 hover:bg-rose-500/30',
        text: 'text-rose-400',
        pill: 'bg-rose-500/20 text-rose-300 border-rose-500/30',
        badge: 'STRONG INVERSE',
        barColor: 'bg-rose-500'
      };
    }
  };

  // Inspect pair details (selected pair or hovered pair)
  const activePairInspection = useMemo(() => {
    const pair = selectedPairDetail || hoveredPair;
    if (!pair) {
      // Default to top correlation against selectedSymbol
      if (selectedSymbolCorrelations.length > 0) {
        const top = selectedSymbolCorrelations[0];
        return {
          symA: selectedSymbol,
          symB: top.symbol,
          val: top.val
        };
      }
      return null;
    }
    return pair;
  }, [selectedPairDetail, hoveredPair, selectedSymbolCorrelations, selectedSymbol]);

  const activeInspectionDetails = useMemo(() => {
    if (!activePairInspection) return null;
    const { symA, symB, val } = activePairInspection;
    const classification = classifyCorrelation(val);
    const riskNote = getCorrelationRiskGuidance(symA, symB, val, positions);
    const posA = positions.find(p => p.symbol === symA && p.status === 'OPEN');
    const posB = positions.find(p => p.symbol === symB && p.status === 'OPEN');
    return {
      symA,
      symB,
      val,
      classification,
      riskNote,
      posA,
      posB
    };
  }, [activePairInspection, positions]);

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg space-y-4">
      {/* Header & Controls */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-3">
        <div className="flex items-center gap-2.5">
          <div className="p-2 bg-cyan-500/10 border border-cyan-500/30 rounded-lg text-cyan-400">
            <ArrowRightLeft className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
                <span>Trade Correlation & Exposure Matrix</span>
              </h3>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-cyan-300 border border-slate-700 font-semibold">
                Target: {selectedSymbol}
              </span>
              {loading && <RefreshCw className="w-3.5 h-3.5 text-cyan-400 animate-spin" />}
            </div>
            <p className="text-xs text-slate-400">
              Cross-asset price return correlation across the active watch-list
            </p>
          </div>
        </div>

        {/* View Switcher & Lookback Horizon Buttons */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Lookback Horizon */}
          <div className="flex items-center bg-slate-950 p-1 rounded-lg border border-slate-800 text-xs font-mono">
            <span className="text-slate-500 text-[10px] px-1.5 flex items-center gap-1">
              <Sliders className="w-3 h-3" />
              <span>Horizon:</span>
            </span>
            <button
              id="corr-horizon-1d"
              onClick={() => setLookbackDays(1)}
              className={`px-2 py-0.5 rounded transition text-[11px] font-semibold ${
                lookbackDays === 1
                  ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              1D (M15)
            </button>
            <button
              id="corr-horizon-3d"
              onClick={() => setLookbackDays(3)}
              className={`px-2 py-0.5 rounded transition text-[11px] font-semibold ${
                lookbackDays === 3
                  ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              3D (Session)
            </button>
            <button
              id="corr-horizon-7d"
              onClick={() => setLookbackDays(7)}
              className={`px-2 py-0.5 rounded transition text-[11px] font-semibold ${
                lookbackDays === 7
                  ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              7D (Weekly)
            </button>
          </div>

          {/* Mode Switcher */}
          <div className="flex items-center bg-slate-950 p-1 rounded-lg border border-slate-800 text-xs font-mono">
            <button
              id="corr-view-focused"
              onClick={() => setViewMode('focused')}
              className={`px-2.5 py-1 rounded transition flex items-center gap-1.5 text-[11px] font-semibold ${
                viewMode === 'focused'
                  ? 'bg-cyan-500 text-slate-950 shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Eye className="w-3.5 h-3.5" />
              <span>{selectedSymbol} Focus</span>
            </button>
            <button
              id="corr-view-matrix"
              onClick={() => setViewMode('matrix')}
              className={`px-2.5 py-1 rounded transition flex items-center gap-1.5 text-[11px] font-semibold ${
                viewMode === 'matrix'
                  ? 'bg-cyan-500 text-slate-950 shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Grid className="w-3.5 h-3.5" />
              <span>Full Matrix</span>
            </button>
          </div>
        </div>
      </div>

      {/* Main Content Area */}
      {viewMode === 'focused' ? (
        /* FOCUSED VIEW: Selected Symbol vs All Others */
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
          {/* Left Column: Horizontal Correlation Bars & Ranking */}
          <div className="lg:col-span-7 space-y-3">
            <div className="flex items-center justify-between text-xs font-mono text-slate-400 px-1">
              <span className="flex items-center gap-1.5">
                <span>Correlation of </span>
                <strong className="text-cyan-300">{selectedSymbol}</strong>
                <span> with Watch-List</span>
              </span>
              <span className="text-[11px] text-slate-500">Scale: -1.0 to +1.0</span>
            </div>

            <div className="space-y-2.5">
              {selectedSymbolCorrelations.map(item => {
                const style = getCorrelationColor(item.val);
                const isPositive = item.val >= 0;
                const absPercent = Math.min(100, Math.abs(item.val) * 100);
                const isHovered = activePairInspection?.symB === item.symbol;

                return (
                  <div
                    key={item.symbol}
                    onClick={() => {
                      setSelectedPairDetail({
                        symA: selectedSymbol,
                        symB: item.symbol,
                        val: item.val
                      });
                    }}
                    onMouseEnter={() => {
                      setHoveredPair({
                        symA: selectedSymbol,
                        symB: item.symbol,
                        val: item.val
                      });
                    }}
                    className={`bg-slate-950 p-3 rounded-lg border transition cursor-pointer ${
                      isHovered
                        ? 'border-cyan-500/80 bg-slate-950/90 shadow-md'
                        : 'border-slate-800/80 hover:border-slate-700'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2 mb-1.5 font-mono text-xs">
                      <div className="flex items-center gap-2">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            onSelectSymbol(item.symbol);
                          }}
                          className="font-bold text-slate-200 hover:text-cyan-300 transition flex items-center gap-1"
                          title={`Switch active terminal symbol to ${item.symbol}`}
                        >
                          <span>{item.symbol}</span>
                          <span className="text-[9px] text-slate-500 font-normal">({SUPPORTED_SYMBOLS.find(s => s.symbol === item.symbol)?.name.split('/')[0].trim()})</span>
                        </button>
                      </div>

                      <div className="flex items-center gap-2">
                        <span className={`text-[10px] font-mono px-1.5 py-0.2 rounded border font-semibold ${style.pill}`}>
                          {style.badge}
                        </span>
                        <span className={`font-mono font-bold text-xs ${style.text}`}>
                          {item.val >= 0 ? `+${item.val.toFixed(2)}` : item.val.toFixed(2)}
                        </span>
                      </div>
                    </div>

                    {/* Dual-Sided Correlation Visual Bar (-1.0 to +1.0 center line) */}
                    <div className="relative w-full h-2 bg-slate-900 rounded-full overflow-hidden flex">
                      {/* Negative half (left) */}
                      <div className="w-1/2 h-full flex justify-end">
                        {!isPositive && (
                          <div
                            className={`h-full rounded-l-full transition-all duration-300 ${style.barColor}`}
                            style={{ width: `${absPercent}%` }}
                          />
                        )}
                      </div>
                      {/* Center zero divider */}
                      <div className="w-[2px] h-full bg-slate-700 z-10" />
                      {/* Positive half (right) */}
                      <div className="w-1/2 h-full flex justify-start">
                        {isPositive && (
                          <div
                            className={`h-full rounded-r-full transition-all duration-300 ${style.barColor}`}
                            style={{ width: `${absPercent}%` }}
                          />
                        )}
                      </div>
                    </div>

                    {/* Risk Tag if present */}
                    {item.riskNote && (
                      <div className="mt-2 text-[10px] font-mono text-amber-300/90 bg-amber-500/10 border border-amber-500/20 px-2 py-1 rounded flex items-center gap-1.5">
                        <AlertTriangle className="w-3 h-3 text-amber-400 shrink-0" />
                        <span>{item.riskNote}</span>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Right Column: Selected Pair Correlation Detail & Risk Diagnostics */}
          <div className="lg:col-span-5 space-y-3">
            <div className="text-xs font-mono text-slate-400 px-1">
              Pairwise Risk & SMC Insight
            </div>

            {activeInspectionDetails ? (
              <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-4">
                {/* Header comparison */}
                <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-bold text-cyan-300 font-mono">
                      {activeInspectionDetails.symA}
                    </span>
                    <ArrowRightLeft className="w-3.5 h-3.5 text-slate-500" />
                    <span className="text-sm font-bold text-slate-200 font-mono">
                      {activeInspectionDetails.symB}
                    </span>
                  </div>
                  <span
                    className={`text-base font-bold font-mono ${
                      getCorrelationColor(activeInspectionDetails.val).text
                    }`}
                  >
                    {activeInspectionDetails.val >= 0
                      ? `+${activeInspectionDetails.val.toFixed(2)}`
                      : activeInspectionDetails.val.toFixed(2)}
                  </span>
                </div>

                {/* Classification Description */}
                <div className="space-y-1.5">
                  <span className="text-[10px] font-mono text-slate-400 uppercase tracking-wider">
                    Relationship Dynamics
                  </span>
                  <p className="text-xs text-slate-300 leading-relaxed font-mono bg-slate-900/60 p-2.5 rounded-lg border border-slate-800/80">
                    {activeInspectionDetails.classification.description}
                  </p>
                </div>

                {/* SMC & Execution Exposure Advice */}
                <div className="space-y-1.5">
                  <span className="text-[10px] font-mono text-slate-400 uppercase tracking-wider flex items-center gap-1">
                    <ShieldAlert className="w-3 h-3 text-cyan-400" />
                    <span>Portfolio Exposure Rule</span>
                  </span>
                  <div className="text-xs text-slate-300 leading-relaxed font-mono bg-slate-900/60 p-2.5 rounded-lg border border-slate-800/80 space-y-1">
                    {activeInspectionDetails.val >= 0.70 ? (
                      <p className="text-amber-300/90">
                        ⚡ <strong>High Directional Overlap</strong>: Simultaneous positions on both instruments in the same direction effectively double USD risk. Sizing should be reduced to 0.5R each.
                      </p>
                    ) : activeInspectionDetails.val <= -0.70 ? (
                      <p className="text-cyan-300/90">
                        🛡️ <strong>Natural Macro Hedge</strong>: Opposite price behavior provides hedge protection. Taking matching directional signals requires careful session confirmation.
                      </p>
                    ) : (
                      <p className="text-emerald-300/90">
                        ✨ <strong>Independent Asset Behavior</strong>: Low co-variance facilitates uncorrelated trade execution without stacking directional risk.
                      </p>
                    )}
                  </div>
                </div>

                {/* Active Positions Check */}
                {(activeInspectionDetails.posA || activeInspectionDetails.posB) && (
                  <div className="bg-slate-900/80 p-3 rounded-lg border border-slate-800 space-y-1.5">
                    <span className="text-[10px] font-mono text-slate-400 uppercase tracking-wider flex items-center gap-1">
                      <Activity className="w-3 h-3 text-emerald-400" />
                      <span>Live Active Exposure</span>
                    </span>
                    <div className="text-xs font-mono space-y-1">
                      {activeInspectionDetails.posA && (
                        <div className="flex justify-between text-slate-300">
                          <span>{activeInspectionDetails.symA}:</span>
                          <span className="font-bold text-cyan-300">
                            {activeInspectionDetails.posA.side} ({activeInspectionDetails.posA.volume} lots)
                          </span>
                        </div>
                      )}
                      {activeInspectionDetails.posB && (
                        <div className="flex justify-between text-slate-300">
                          <span>{activeInspectionDetails.symB}:</span>
                          <span className="font-bold text-cyan-300">
                            {activeInspectionDetails.posB.side} ({activeInspectionDetails.posB.volume} lots)
                          </span>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Quick Action Button */}
                <button
                  id="switch-selected-symbol-btn"
                  onClick={() => onSelectSymbol(activeInspectionDetails.symB)}
                  className="w-full py-2 bg-slate-900 hover:bg-slate-800 text-cyan-300 border border-cyan-500/30 rounded-lg text-xs font-mono font-semibold transition flex items-center justify-center gap-2"
                >
                  <span>Set Active Terminal to {activeInspectionDetails.symB}</span>
                  <ArrowRightLeft className="w-3.5 h-3.5" />
                </button>
              </div>
            ) : (
              <div className="bg-slate-950 p-6 rounded-xl border border-slate-800 text-center text-xs font-mono text-slate-500">
                Select a pair from the list to view detailed exposure diagnostics
              </div>
            )}
          </div>
        </div>
      ) : (
        /* MATRIX VIEW: Full Symmetrical Heatmap Grid */
        <div className="space-y-4">
          <div className="overflow-x-auto pb-2">
            <table className="w-full border-collapse font-mono text-xs text-center">
              <thead>
                <tr>
                  <th className="p-2 text-slate-500 text-left font-normal border-b border-slate-800">
                    Pair
                  </th>
                  {symbols.map(colSym => (
                    <th
                      key={colSym}
                      className={`p-2 border-b border-slate-800 font-bold cursor-pointer transition ${
                        colSym === selectedSymbol
                          ? 'text-cyan-300 bg-cyan-500/10'
                          : 'text-slate-400 hover:text-slate-200'
                      }`}
                      onClick={() => onSelectSymbol(colSym)}
                      title={`Select ${colSym}`}
                    >
                      {colSym}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {symbols.map(rowSym => (
                  <tr key={rowSym} className="border-b border-slate-800/40">
                    {/* Row Header */}
                    <td
                      onClick={() => onSelectSymbol(rowSym)}
                      className={`p-2.5 text-left font-bold cursor-pointer transition ${
                        rowSym === selectedSymbol
                          ? 'text-cyan-300 bg-cyan-500/10'
                          : 'text-slate-300 hover:text-cyan-300'
                      }`}
                      title={`Select ${rowSym}`}
                    >
                      {rowSym}
                    </td>

                    {/* Matrix Cells */}
                    {symbols.map(colSym => {
                      const isSelf = rowSym === colSym;
                      const val = isSelf ? 1.0 : correlationData?.matrix[rowSym]?.[colSym] ?? 0;
                      const isSelectedCell = rowSym === selectedSymbol || colSym === selectedSymbol;
                      const style = getCorrelationColor(val);

                      return (
                        <td
                          key={colSym}
                          onClick={() => {
                            if (!isSelf) {
                              setSelectedPairDetail({
                                symA: rowSym,
                                symB: colSym,
                                val
                              });
                            }
                          }}
                          onMouseEnter={() => {
                            if (!isSelf) {
                              setHoveredPair({
                                symA: rowSym,
                                symB: colSym,
                                val
                              });
                            }
                          }}
                          className={`p-1.5 transition ${
                            isSelectedCell ? 'bg-cyan-500/5' : ''
                          }`}
                        >
                          <div
                            className={`py-1.5 px-2 rounded font-mono font-bold text-xs border transition cursor-pointer ${
                              isSelf
                                ? 'bg-slate-800/40 text-slate-500 border-slate-800 cursor-default'
                                : style.bg
                            } ${
                              selectedPairDetail?.symA === rowSym && selectedPairDetail?.symB === colSym
                                ? 'ring-2 ring-cyan-400'
                                : ''
                            }`}
                          >
                            {isSelf ? '1.00' : val >= 0 ? `+${val.toFixed(2)}` : val.toFixed(2)}
                          </div>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Matrix Detail Box below */}
          {activeInspectionDetails && (
            <div className="bg-slate-950 p-3.5 rounded-lg border border-slate-800 flex flex-wrap items-center justify-between gap-3 text-xs font-mono">
              <div className="flex items-center gap-3">
                <span className="text-cyan-300 font-bold">{activeInspectionDetails.symA} ⇄ {activeInspectionDetails.symB}</span>
                <span className={`font-bold ${getCorrelationColor(activeInspectionDetails.val).text}`}>
                  {activeInspectionDetails.val >= 0 ? `+${activeInspectionDetails.val.toFixed(2)}` : activeInspectionDetails.val.toFixed(2)}
                </span>
                <span className="text-slate-400 text-[11px] hidden sm:inline">
                  {activeInspectionDetails.classification.description}
                </span>
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={() => onSelectSymbol(activeInspectionDetails.symB)}
                  className="px-2.5 py-1 bg-slate-900 hover:bg-slate-800 text-cyan-300 border border-cyan-500/30 rounded text-[11px] font-semibold transition"
                >
                  Select {activeInspectionDetails.symB}
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Footer Correlation Scale & Legend */}
      <div className="pt-2 border-t border-slate-800/80 flex flex-wrap items-center justify-between gap-3 text-[11px] font-mono text-slate-400">
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-slate-500 text-[10px] uppercase">Legend:</span>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded bg-emerald-500" />
            <span>Strong (+0.70 to +1.00)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded bg-teal-400" />
            <span>Moderate (+0.30 to +0.69)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded bg-slate-600" />
            <span>Neutral (-0.29 to +0.29)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded bg-amber-400" />
            <span>Inverse (-0.30 to -0.69)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded bg-rose-500" />
            <span>Strong Inverse (-0.70 to -1.00)</span>
          </div>
        </div>

        <div className="text-slate-500 text-[10px]">
          Updated live via M15 price returns
        </div>
      </div>
    </div>
  );
};
