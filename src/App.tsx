import React, { useState, useEffect } from 'react';
import {
  SymbolName,
  MarketSession,
  TradeProposal,
  OpenPosition,
  TradeDeal,
} from './types/trading';
import {
  INITIAL_BROKER_STATUS,
  INITIAL_DEALS,
  INITIAL_POSITIONS,
  INITIAL_PROPOSALS,
  INITIAL_OPPORTUNITY,
  BACKTEST_EVIDENCE,
  generateCandlesForSymbol,
} from './services/tradingStore';
import { Navbar } from './components/Navbar';
import { MarketChart } from './components/Terminal/MarketChart';
import { ProposalsPanel } from './components/Terminal/ProposalsPanel';
import { OwnerAnalysisBridge } from './components/Terminal/OwnerAnalysisBridge';
import { ExecutionCockpit } from './components/Terminal/ExecutionCockpit';
import { BrokerDiagnostic } from './components/Terminal/BrokerDiagnostic';
import { ResearchLab } from './components/Terminal/ResearchLab';
import {
  LayoutDashboard,
  FileText,
  Compass,
  Sliders,
  FlaskConical,
  Server,
  Bell,
} from 'lucide-react';

export const App: React.FC = () => {
  const [activeSymbol, setActiveSymbol] = useState<SymbolName>('EURUSD');
  const [activeTab, setActiveTab] = useState<
    'terminal' | 'proposals' | 'owner-desk' | 'execution' | 'research' | 'broker'
  >('terminal');
  const [apiMode, setApiMode] = useState<'mock' | 'real'>('mock');

  // Market & Simulation Data
  const [marketData, setMarketData] = useState(() => generateCandlesForSymbol('EURUSD'));
  const [proposals, setProposals] = useState<TradeProposal[]>(INITIAL_PROPOSALS);
  const [selectedProposal, setSelectedProposal] = useState<TradeProposal | null>(
    INITIAL_PROPOSALS[0]
  );
  const [positions, setPositions] = useState<OpenPosition[]>(INITIAL_POSITIONS);
  const [deals, setDeals] = useState<TradeDeal[]>(INITIAL_DEALS);
  const [brokerStatus, setBrokerStatus] = useState(INITIAL_BROKER_STATUS);
  const [decisionResult, setDecisionResult] = useState<{
    status: 'CONFIRMED' | 'REJECTED';
    commandTemplate?: string;
  } | null>(null);
  const [notification, setNotification] = useState<string | null>(null);

  // Time & Session Tracker
  const [currentTimeUtc, setCurrentTimeUtc] = useState('');
  const [activeSession, setActiveSession] = useState<MarketSession>('LONDON');

  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      const hour = now.getUTCHours();
      const mins = now.getUTCMinutes().toString().padStart(2, '0');
      const secs = now.getUTCSeconds().toString().padStart(2, '0');
      setCurrentTimeUtc(`${hour.toString().padStart(2, '0')}:${mins}:${secs}`);

      if (hour >= 0 && hour < 8) {
        setActiveSession('ASIAN');
      } else if (hour >= 7 && hour < 15) {
        setActiveSession('LONDON');
      } else if (hour >= 13 && hour < 21) {
        setActiveSession('NEW_YORK');
      } else {
        setActiveSession('CLOSED');
      }
    };

    updateTime();
    const timer = setInterval(updateTime, 1000);
    return () => clearInterval(timer);
  }, []);

  // Symbol switch handler
  const handleSelectSymbol = (s: SymbolName) => {
    setActiveSymbol(s);
    setMarketData(generateCandlesForSymbol(s));
    const match = proposals.find((p) => p.symbol === s);
    if (match) setSelectedProposal(match);
  };

  // Live price tick simulator (every 3 seconds)
  useEffect(() => {
    const interval = setInterval(() => {
      setPositions((prev) =>
        prev.map((pos) => {
          const delta = (Math.random() - 0.49) * 0.0001;
          const newPrice = +(pos.currentPrice + delta).toFixed(
            pos.symbol.includes('USDT') || pos.symbol === 'USDJPY' ? 2 : 5
          );
          const pipsDelta =
            (newPrice - pos.openPrice) *
            (pos.type === 'BUY' ? 1 : -1) *
            (pos.symbol.includes('JPY') ? 100 : pos.symbol.includes('USDT') ? 1 : 10000);
          const pnlDelta = +(pipsDelta * pos.lots * 10).toFixed(2);
          return {
            ...pos,
            currentPrice: newPrice,
            pips: +pipsDelta.toFixed(1),
            pnl: pnlDelta,
          };
        })
      );
    }, 3000);
    return () => clearInterval(interval);
  }, []);

  const triggerNotification = (msg: string) => {
    setNotification(msg);
    setTimeout(() => setNotification(null), 4000);
  };

  // Trade management handlers
  const handleSetBreakeven = (ticket: number) => {
    setPositions((prev) =>
      prev.map((pos) => {
        if (pos.ticket === ticket) {
          return {
            ...pos,
            sl: pos.openPrice,
            isBreakeven: true,
          };
        }
        return pos;
      })
    );
    triggerNotification(`Position #${ticket} Stop Loss moved to Breakeven (${brokerStatus.broker}).`);
  };

  const handlePartialClose = (ticket: number) => {
    const pos = positions.find((p) => p.ticket === ticket);
    if (!pos) return;

    const closedLots = +(pos.lots / 2).toFixed(2);
    const realizedProfit = +(pos.pnl / 2).toFixed(2);

    setPositions((prev) =>
      prev.map((p) => {
        if (p.ticket === ticket) {
          return {
            ...p,
            lots: +(p.lots - closedLots).toFixed(2),
            pnl: realizedProfit,
          };
        }
        return p;
      })
    );

    // Record deal
    const newDeal: TradeDeal = {
      ticket: Math.floor(9105000 + Math.random() * 1000),
      order: Math.floor(8494000 + Math.random() * 1000),
      time: new Date().toISOString().replace('T', ' ').substring(0, 19),
      symbol: pos.symbol,
      type: pos.type,
      entry: 'OUT',
      lots: closedLots,
      price: pos.currentPrice,
      profit: realizedProfit,
      commission: -1.2,
      swap: 0.0,
      comment: 'PARTIAL_CLOSE:50%',
    };

    setDeals((prev) => [newDeal, ...prev]);
    setBrokerStatus((prev) => ({
      ...prev,
      balance: +(prev.balance + realizedProfit).toFixed(2),
      equity: +(prev.equity + realizedProfit).toFixed(2),
    }));

    triggerNotification(`Secured partial profit of $${realizedProfit} USD on #${ticket} (50% closed).`);
  };

  const handleClosePosition = (ticket: number) => {
    const pos = positions.find((p) => p.ticket === ticket);
    if (!pos) return;

    setPositions((prev) => prev.filter((p) => p.ticket !== ticket));

    const newDeal: TradeDeal = {
      ticket: Math.floor(9105000 + Math.random() * 1000),
      order: Math.floor(8494000 + Math.random() * 1000),
      time: new Date().toISOString().replace('T', ' ').substring(0, 19),
      symbol: pos.symbol,
      type: pos.type,
      entry: 'OUT',
      lots: pos.lots,
      price: pos.currentPrice,
      profit: pos.pnl,
      commission: -1.5,
      swap: 0.0,
      comment: 'MANUAL_CLOSE',
    };

    setDeals((prev) => [newDeal, ...prev]);
    setBrokerStatus((prev) => ({
      ...prev,
      balance: +(prev.balance + pos.pnl).toFixed(2),
      equity: +(prev.equity + pos.pnl).toFixed(2),
    }));

    triggerNotification(`Closed position #${ticket}. Realized P&L: $${pos.pnl} USD.`);
  };

  const handleClaimTicket = (ticket: number) => {
    triggerNotification(`Ticket #${ticket} claimed into deterministic position management.`);
  };

  const handleSubmitOrder = (order: {
    symbol: SymbolName;
    type: 'BUY' | 'SELL';
    lots: number;
    sl: number;
    tp: number;
    userConfirmed: boolean;
  }) => {
    const curPrice = marketData.candles[marketData.candles.length - 1]?.close || 1.1600;
    const newPos: OpenPosition = {
      ticket: Math.floor(9104700 + Math.random() * 500),
      symbol: order.symbol,
      type: order.type,
      lots: order.lots,
      openPrice: curPrice,
      currentPrice: curPrice,
      sl: order.sl || (order.type === 'BUY' ? curPrice - 0.002 : curPrice + 0.002),
      tp: order.tp || (order.type === 'BUY' ? curPrice + 0.006 : curPrice - 0.006),
      pnl: 0.0,
      pips: 0.0,
      openTime: new Date().toISOString().replace('T', ' ').substring(0, 19) + ' UTC',
      isBreakeven: false,
      claimed: true,
    };

    setPositions((prev) => [newPos, ...prev]);
    triggerNotification(`Order #${newPos.ticket} executed on VantageMarkets-Demo (${order.symbol} ${order.type} ${order.lots} lots).`);
  };

  // Owner Decision Desk handlers
  const handleConfirmDecision = (proposalId: string, ownerKey: string) => {
    const p = proposals.find((x) => x.id === proposalId);
    if (!p) return;

    const command = `# EXECUTABLE TRADE COMMAND TEMPLATE (PREPARED / UNCONFIRMED)
# Authority: AGENTS.md rule 3 (assistant.commands.execute_command)
# Owner Authorization Key: SHA256(...) [VERIFIED]
# Ticket ID: ${p.id}
# Strategy: ${p.strategyId} (v${p.strategyVersion})

command = {
    "action": "OPEN",
    "symbol": "${p.symbol}",
    "direction": "${p.direction}",
    "lots": ${p.lotSize},
    "entry_price": ${p.entryPrice},
    "sl": ${p.stopLoss},
    "tp": ${p.target2},
    "risk_usd": ${p.riskAmount},
    "environment": "DEMO",
    "user_confirmed": False  # MUST BE EXPLICITLY CONFIRMED PER TURN
}
result = assistant.commands.execute_command(command, user_confirmed=False)
`;

    setDecisionResult({
      status: 'CONFIRMED',
      commandTemplate: command,
    });

    setProposals((prev) =>
      prev.map((item) =>
        item.id === proposalId
          ? {
              ...item,
              ownerDecision: 'CONFIRMED',
              ownerDecisionTime: new Date().toISOString(),
              status: 'READY',
            }
          : item
      )
    );

    triggerNotification(`Proposal confirmed by owner. Prepared execution template generated.`);
  };

  const handleRejectDecision = (proposalId: string, ownerKey: string) => {
    setDecisionResult({
      status: 'REJECTED',
      commandTemplate: `# Proposal ${proposalId} REJECTED by owner (${new Date().toISOString()}). No order command emitted.`,
    });

    setProposals((prev) =>
      prev.map((item) =>
        item.id === proposalId
          ? {
              ...item,
              ownerDecision: 'REJECTED',
              ownerDecisionTime: new Date().toISOString(),
              status: 'REJECTED',
            }
          : item
      )
    );

    triggerNotification(`Proposal rejected. Ticket disposition recorded.`);
  };

  const navTabs = [
    { id: 'terminal', label: 'Terminal & Chart', icon: LayoutDashboard },
    { id: 'proposals', label: 'Session Proposals', icon: FileText },
    { id: 'owner-desk', label: 'Owner Decision Desk', icon: Compass },
    { id: 'execution', label: 'Execution & Positions', icon: Sliders },
    { id: 'research', label: 'Research & Evidence', icon: FlaskConical },
    { id: 'broker', label: 'Broker Status', icon: Server },
  ] as const;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
      <Navbar
        activeSymbol={activeSymbol}
        onSelectSymbol={handleSelectSymbol}
        activeSession={activeSession}
        brokerStatus={brokerStatus}
        currentTimeUtc={currentTimeUtc}
        apiMode={apiMode}
        onToggleApiMode={() => setApiMode((m) => (m === 'mock' ? 'real' : 'mock'))}
      />

      {/* Toast Notification */}
      {notification && (
        <div className="fixed bottom-5 right-5 z-50 bg-emerald-500 text-slate-950 font-mono text-xs font-bold px-4 py-2.5 rounded-lg shadow-xl flex items-center gap-2 border border-emerald-400 animate-bounce">
          <Bell className="w-4 h-4 shrink-0" />
          <span>{notification}</span>
        </div>
      )}

      {/* Main Tab Navigation */}
      <div className="border-b border-slate-800 bg-slate-900/60 sticky top-16 z-40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <nav className="flex space-x-1 sm:space-x-4 overflow-x-auto py-2">
            {navTabs.map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-mono font-medium transition whitespace-nowrap ${
                    isActive
                      ? 'bg-slate-800 text-emerald-400 border border-slate-700 shadow-sm'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/40'
                  }`}
                >
                  <Icon className={`w-4 h-4 ${isActive ? 'text-emerald-400' : 'text-slate-400'}`} />
                  <span>{tab.label}</span>
                  {tab.id === 'proposals' && (
                    <span className="ml-1 px-1.5 py-0.2 rounded-full text-[10px] bg-emerald-950 text-emerald-300 border border-emerald-800">
                      {proposals.filter((p) => p.status === 'READY').length} Ready
                    </span>
                  )}
                  {tab.id === 'execution' && positions.length > 0 && (
                    <span className="ml-1 px-1.5 py-0.2 rounded-full text-[10px] bg-blue-950 text-blue-300 border border-blue-800">
                      {positions.length}
                    </span>
                  )}
                </button>
              );
            })}
          </nav>
        </div>
      </div>

      {/* Main Workspace Body */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 flex-1 w-full">
        {activeTab === 'terminal' && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            <div className="lg:col-span-8 flex flex-col gap-6">
              <MarketChart
                symbol={activeSymbol}
                candles={marketData.candles}
                boxes={marketData.boxes}
                smc={marketData.smc}
              />
              <ExecutionCockpit
                positions={positions}
                onSetBreakeven={handleSetBreakeven}
                onPartialClose={handlePartialClose}
                onClosePosition={handleClosePosition}
                onClaimTicket={handleClaimTicket}
                onSubmitOrder={handleSubmitOrder}
                activeSymbol={activeSymbol}
              />
            </div>

            <div className="lg:col-span-4 flex flex-col gap-6">
              <ProposalsPanel
                proposals={proposals}
                selectedProposalId={selectedProposal?.id}
                onSelectProposal={(p) => {
                  setSelectedProposal(p);
                  setActiveSymbol(p.symbol);
                }}
                onSendToDecisionDesk={(p) => {
                  setSelectedProposal(p);
                  setActiveSymbol(p.symbol);
                  setActiveTab('owner-desk');
                }}
                activeSymbol={activeSymbol}
              />
              <BrokerDiagnostic
                brokerStatus={brokerStatus}
                deals={deals.slice(0, 5)}
                onRefresh={() => {}}
                apiMode={apiMode}
              />
            </div>
          </div>
        )}

        {activeTab === 'proposals' && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            <div className="lg:col-span-7">
              <ProposalsPanel
                proposals={proposals}
                selectedProposalId={selectedProposal?.id}
                onSelectProposal={(p) => {
                  setSelectedProposal(p);
                  setActiveSymbol(p.symbol);
                }}
                onSendToDecisionDesk={(p) => {
                  setSelectedProposal(p);
                  setActiveSymbol(p.symbol);
                  setActiveTab('owner-desk');
                }}
                activeSymbol={activeSymbol}
              />
            </div>
            <div className="lg:col-span-5">
              <OwnerAnalysisBridge
                selectedProposal={selectedProposal}
                opportunity={INITIAL_OPPORTUNITY[activeSymbol] || null}
                symbol={activeSymbol}
                onConfirmDecision={handleConfirmDecision}
                onRejectDecision={handleRejectDecision}
                decisionResult={decisionResult}
              />
            </div>
          </div>
        )}

        {activeTab === 'owner-desk' && (
          <div className="flex flex-col gap-6 max-w-5xl mx-auto">
            <OwnerAnalysisBridge
              selectedProposal={selectedProposal}
              opportunity={INITIAL_OPPORTUNITY[activeSymbol] || null}
              symbol={activeSymbol}
              onConfirmDecision={handleConfirmDecision}
              onRejectDecision={handleRejectDecision}
              decisionResult={decisionResult}
            />
          </div>
        )}

        {activeTab === 'execution' && (
          <div className="flex flex-col gap-6">
            <ExecutionCockpit
              positions={positions}
              onSetBreakeven={handleSetBreakeven}
              onPartialClose={handlePartialClose}
              onClosePosition={handleClosePosition}
              onClaimTicket={handleClaimTicket}
              onSubmitOrder={handleSubmitOrder}
              activeSymbol={activeSymbol}
            />
            <BrokerDiagnostic
              brokerStatus={brokerStatus}
              deals={deals}
              onRefresh={() => {}}
              apiMode={apiMode}
            />
          </div>
        )}

        {activeTab === 'research' && (
          <div className="flex flex-col gap-6">
            <ResearchLab backtest={BACKTEST_EVIDENCE} />
          </div>
        )}

        {activeTab === 'broker' && (
          <div className="max-w-4xl mx-auto flex flex-col gap-6 w-full">
            <BrokerDiagnostic
              brokerStatus={brokerStatus}
              deals={deals}
              onRefresh={() => {}}
              apiMode={apiMode}
            />
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-800 bg-slate-900/60 py-4 px-4 text-center text-xs text-slate-500 font-mono">
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-2">
          <span>AG Profit Trading Assistant &bull; Deterministic Session Sweeps & SMC Surveillance</span>
          <span>Environment: VantageMarkets-Demo &bull; Account: ****2746 &bull; Read-Only Safety Active</span>
        </div>
      </footer>
    </div>
  );
};

export default App;
