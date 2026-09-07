import React, { useState, useMemo } from 'react';
import { AuditLog } from '../../types/trading';
import {
  ShieldCheck,
  AlertTriangle,
  Info,
  XCircle,
  Search,
  X,
  Filter,
  Copy,
  Check,
  ChevronDown,
  ChevronUp,
  FileText,
  RotateCcw
} from 'lucide-react';

interface AuditLogViewerProps {
  logs: AuditLog[];
}

export const AuditLogViewer: React.FC<AuditLogViewerProps> = ({ logs }) => {
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [selectedCategory, setSelectedCategory] = useState<string>('ALL');
  const [selectedStatus, setSelectedStatus] = useState<string>('ALL');
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [expandedLogIds, setExpandedLogIds] = useState<Set<string>>(new Set());

  // Derive all unique categories from the logs
  const categories = useMemo(() => {
    const set = new Set<string>();
    logs.forEach(l => {
      if (l.category) set.add(l.category.toUpperCase());
    });
    return ['ALL', ...Array.from(set)];
  }, [logs]);

  // Filter logs based on query, category, and status
  const filteredLogs = useMemo(() => {
    return logs.filter(log => {
      // Category filter
      if (selectedCategory !== 'ALL' && log.category.toUpperCase() !== selectedCategory) {
        return false;
      }

      // Status filter
      if (selectedStatus !== 'ALL' && log.status !== selectedStatus) {
        return false;
      }

      // Search query filter
      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase();
        const actionMatch = log.action.toLowerCase().includes(query);
        const categoryMatch = log.category.toLowerCase().includes(query);
        const idMatch = log.id.toLowerCase().includes(query);
        const detailsMatch = JSON.stringify(log.details).toLowerCase().includes(query);
        return actionMatch || categoryMatch || idMatch || detailsMatch;
      }

      return true;
    });
  }, [logs, selectedCategory, selectedStatus, searchQuery]);

  // Aggregate stats
  const stats = useMemo(() => {
    const successCount = logs.filter(l => l.status === 'SUCCESS').length;
    const warningCount = logs.filter(l => l.status === 'WARNING').length;
    const failClosedCount = logs.filter(l => l.status === 'FAIL_CLOSED').length;
    const infoCount = logs.filter(l => l.status === 'INFO').length;
    return { successCount, warningCount, failClosedCount, infoCount };
  }, [logs]);

  const toggleExpand = (id: string) => {
    setExpandedLogIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const handleCopyLog = (log: AuditLog) => {
    navigator.clipboard.writeText(JSON.stringify(log, null, 2));
    setCopiedId(log.id);
    setTimeout(() => {
      setCopiedId(null);
    }, 2000);
  };

  const clearFilters = () => {
    setSearchQuery('');
    setSelectedCategory('ALL');
    setSelectedStatus('ALL');
  };

  const getStatusIcon = (status: AuditLog['status']) => {
    switch (status) {
      case 'SUCCESS':
        return <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0" />;
      case 'WARNING':
        return <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />;
      case 'FAIL_CLOSED':
        return <XCircle className="w-4 h-4 text-rose-400 shrink-0" />;
      default:
        return <Info className="w-4 h-4 text-cyan-400 shrink-0" />;
    }
  };

  const getStatusBadge = (status: AuditLog['status']) => {
    switch (status) {
      case 'SUCCESS':
        return 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30';
      case 'WARNING':
        return 'bg-amber-500/10 text-amber-300 border-amber-500/30';
      case 'FAIL_CLOSED':
        return 'bg-rose-500/10 text-rose-300 border-rose-500/30';
      default:
        return 'bg-cyan-500/10 text-cyan-300 border-cyan-500/30';
    }
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl space-y-5">
      {/* Header with Title and Metric Badges */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <FileText className="w-4 h-4 text-cyan-400" />
            <h3 className="text-sm font-bold text-slate-200 uppercase tracking-wider font-mono">
              System Audit Logs & Journal
            </h3>
          </div>
          <p className="text-xs font-mono text-slate-400 mt-1">
            Deterministic, atomic, restart-safe decision records and execution telemetry
          </p>
        </div>

        {/* Quick Summary Pill Strips */}
        <div className="flex flex-wrap items-center gap-2 text-[11px] font-mono">
          <span className="px-2 py-0.5 rounded border border-slate-800 bg-slate-950 text-slate-300">
            Total: <span className="font-bold text-slate-100">{logs.length}</span>
          </span>
          <span className="px-2 py-0.5 rounded border border-emerald-500/30 bg-emerald-500/10 text-emerald-300">
            Success: <span className="font-bold">{stats.successCount}</span>
          </span>
          {stats.warningCount > 0 && (
            <span className="px-2 py-0.5 rounded border border-amber-500/30 bg-amber-500/10 text-amber-300">
              Warn: <span className="font-bold">{stats.warningCount}</span>
            </span>
          )}
          {stats.failClosedCount > 0 && (
            <span className="px-2 py-0.5 rounded border border-rose-500/30 bg-rose-500/10 text-rose-300">
              Fail-Closed: <span className="font-bold">{stats.failClosedCount}</span>
            </span>
          )}
        </div>
      </div>

      {/* Filter and Search Controls */}
      <div className="flex flex-col md:flex-row gap-3 items-stretch md:items-center justify-between">
        {/* Search Bar */}
        <div className="relative flex-1">
          <Search className="w-3.5 h-3.5 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            id="audit-log-search"
            type="text"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            placeholder="Search action, category, or payload attributes..."
            className="w-full pl-9 pr-8 py-2 bg-slate-950 border border-slate-800 rounded-lg text-xs font-mono text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500/50"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {/* Category Filter Chips */}
        <div className="flex flex-wrap items-center gap-1.5 font-mono text-[11px]">
          <span className="text-slate-500 flex items-center gap-1 mr-1">
            <Filter className="w-3 h-3" />
            <span>Category:</span>
          </span>
          {categories.map(cat => (
            <button
              key={cat}
              onClick={() => setSelectedCategory(cat)}
              className={`px-2 py-1 rounded transition-colors ${
                selectedCategory === cat
                  ? 'bg-cyan-500 text-slate-950 font-bold shadow-sm'
                  : 'bg-slate-950 text-slate-400 hover:text-slate-200 border border-slate-800'
              }`}
            >
              {cat}
            </button>
          ))}
        </div>

        {/* Status Filter */}
        <div className="flex items-center gap-1 font-mono text-[11px]">
          {(['ALL', 'SUCCESS', 'WARNING', 'FAIL_CLOSED'] as const).map(st => (
            <button
              key={st}
              onClick={() => setSelectedStatus(st)}
              className={`px-2 py-1 rounded transition-colors ${
                selectedStatus === st
                  ? 'bg-slate-700 text-white font-bold border border-slate-600'
                  : 'bg-slate-950 text-slate-400 hover:text-slate-200 border border-slate-800'
              }`}
            >
              {st}
            </button>
          ))}
        </div>
      </div>

      {/* Filter Active Indicator */}
      {(searchQuery || selectedCategory !== 'ALL' || selectedStatus !== 'ALL') && (
        <div className="flex items-center justify-between bg-slate-950/70 border border-slate-800/80 px-3 py-1.5 rounded-lg text-xs font-mono text-slate-400">
          <span>
            Showing <strong className="text-cyan-300">{filteredLogs.length}</strong> of {logs.length} entries
          </span>
          <button
            onClick={clearFilters}
            className="flex items-center gap-1 text-cyan-400 hover:text-cyan-300 transition text-[11px]"
          >
            <RotateCcw className="w-3 h-3" />
            <span>Reset filters</span>
          </button>
        </div>
      )}

      {/* Logs List */}
      <div className="space-y-2.5 font-mono text-xs max-h-[640px] overflow-y-auto pr-1">
        {filteredLogs.length === 0 ? (
          <div className="text-center py-12 bg-slate-950 rounded-xl border border-slate-800/80 space-y-2">
            <Info className="w-6 h-6 text-slate-500 mx-auto" />
            <div className="text-slate-300 font-bold">No Audit Log Entries Found</div>
            <p className="text-xs text-slate-500 max-w-sm mx-auto">
              No journal records match the active search and filter constraints.
            </p>
            <button
              onClick={clearFilters}
              className="mt-2 inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs transition"
            >
              Clear Filters
            </button>
          </div>
        ) : (
          filteredLogs.map(log => {
            const isExpanded = expandedLogIds.has(log.id);
            const isCopied = copiedId === log.id;
            const logDate = new Date(log.timestamp * 1000);

            return (
              <div
                key={log.id}
                id={`audit-log-${log.id}`}
                className="bg-slate-950 rounded-lg border border-slate-800/80 hover:border-slate-700/80 transition p-3.5 space-y-2"
              >
                {/* Row Header */}
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-start gap-2.5">
                    <div className="mt-0.5">{getStatusIcon(log.status)}</div>
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-bold text-slate-100">{log.action}</span>
                        <span
                          className={`text-[10px] px-2 py-0.5 rounded border font-mono ${getStatusBadge(
                            log.status
                          )}`}
                        >
                          {log.status}
                        </span>
                        <span className="text-[10px] px-2 py-0.5 rounded bg-slate-900 border border-slate-800 text-cyan-400 font-mono">
                          {log.category}
                        </span>
                      </div>
                      <div className="text-[10px] text-slate-500 mt-0.5 flex items-center gap-2">
                        <span>ID: {log.id}</span>
                        <span>•</span>
                        <span>
                          {logDate.toLocaleDateString()} {logDate.toLocaleTimeString()} UTC
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Actions: Copy & Expand Details */}
                  <div className="flex items-center gap-1.5 shrink-0">
                    <button
                      type="button"
                      onClick={() => handleCopyLog(log)}
                      className="p-1.5 rounded hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition"
                      title="Copy log entry JSON"
                    >
                      {isCopied ? (
                        <Check className="w-3.5 h-3.5 text-emerald-400" />
                      ) : (
                        <Copy className="w-3.5 h-3.5" />
                      )}
                    </button>
                    <button
                      type="button"
                      onClick={() => toggleExpand(log.id)}
                      className="p-1.5 rounded hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition flex items-center gap-1 text-[11px]"
                      title={isExpanded ? 'Collapse Payload' : 'Expand Payload'}
                    >
                      {isExpanded ? (
                        <ChevronUp className="w-3.5 h-3.5 text-slate-400" />
                      ) : (
                        <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
                      )}
                    </button>
                  </div>
                </div>

                {/* Details Payload Preview / Full View */}
                <div className="mt-2">
                  <pre
                    className={`text-[10px] bg-slate-900/90 border border-slate-800/70 p-2.5 rounded-lg text-slate-300 overflow-x-auto font-mono transition-all ${
                      isExpanded ? 'max-h-96' : 'max-h-24'
                    }`}
                  >
                    {JSON.stringify(log.details, null, 2)}
                  </pre>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
