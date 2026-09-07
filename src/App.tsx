import React, { useState } from 'react';
import { Header } from './components/Header';
import { DecisionMatrix } from './components/DecisionMatrix';
import { TopDownAnalysis } from './components/TopDownAnalysis';
import { SmcSurveillance } from './components/SmcSurveillance';
import { RiskCalculator } from './components/RiskCalculator';
import { JournalLedger } from './components/JournalLedger';
import { StrategyRegistryView } from './components/StrategyRegistryView';
import { INITIAL_DECISIONS } from './data/tradingData';
import { CheckCircle2 } from 'lucide-react';

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<string>('decisions');
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const handleClaimTicket = (ticketId: string) => {
    setToastMessage(`Ticket claimed! Initialized Phase 6 manual trade management for ${ticketId.split(':')[2] || 'trade'}.`);
    setTimeout(() => {
      setToastMessage(null);
    }, 4000);
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col selection:bg-emerald-500/30 selection:text-emerald-200">
      <Header activeTab={activeTab} setActiveTab={setActiveTab} />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {toastMessage && (
          <div className="mb-4 p-3 rounded-lg bg-emerald-950 border border-emerald-500/50 text-emerald-200 text-xs font-mono flex items-center space-x-2 shadow-lg animate-fade-in">
            <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0" />
            <span>{toastMessage}</span>
          </div>
        )}

        {activeTab === 'decisions' && (
          <DecisionMatrix
            decisions={INITIAL_DECISIONS}
            onClaimTicket={handleClaimTicket}
          />
        )}

        {activeTab === 'analysis' && <TopDownAnalysis />}

        {activeTab === 'funnel' && <SmcSurveillance />}

        {activeTab === 'risk' && <RiskCalculator />}

        {activeTab === 'journal' && <JournalLedger />}

        {activeTab === 'strategies' && <StrategyRegistryView />}
      </main>

      <footer className="border-t border-slate-900 bg-slate-950/80 py-4 text-center text-xs font-mono text-slate-500">
        <div className="max-w-7xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-2">
          <span>AG Profit Trading Assistant &bull; Deterministic Strategy Engine</span>
          <span>Fail-Closed Decision Architecture &bull; MT5 / Vantage-Demo</span>
        </div>
      </footer>
    </div>
  );
};

export default App;
