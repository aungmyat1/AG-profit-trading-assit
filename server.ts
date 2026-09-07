import express from "express";
import path from "path";
import { createServer as createViteServer } from "vite";
import {
  REGISTERED_STRATEGIES,
  INITIAL_DECISIONS,
  SMC_SURVEILLANCE_LIST,
  HISTORICAL_JOURNAL,
  EURUSD_ANALYSIS
} from "./src/data/tradingData";

async function startServer() {
  const app = express();
  const PORT = 3000;

  app.use(express.json());

  // In-memory runtime state for trade tickets and management
  const decisions = [...INITIAL_DECISIONS];
  const claimedTickets: Record<string, any> = {};

  // 1. Health check
  app.get("/api/health", (_req, res) => {
    res.json({
      status: "ok",
      application: "AG Profit Trading Assistant",
      runtime: "Node.js 22",
      mt5_gateway_mode: "SIMULATED_DEMO_GATED",
      session_time_utc: new Date().toISOString()
    });
  });

  // 2. Strategies registry
  app.get("/api/strategies", (_req, res) => {
    res.json({
      strategies: REGISTERED_STRATEGIES,
      authority_order: "Strategy YAML -> Strategy Engine -> Execution Engine -> MT5 (Advisory Agent Layer)"
    });
  });

  // 3. Active session decisions & complete entry tickets
  app.get("/api/decisions", (req, res) => {
    const { cycle, symbol } = req.query;
    let filtered = decisions;
    if (cycle) {
      filtered = filtered.filter(d => d.cycle === cycle);
    }
    if (symbol) {
      filtered = filtered.filter(d => d.symbol === symbol);
    }
    res.json({
      timestamp: new Date().toISOString(),
      activeCycle: "ASIAN_LONDON",
      decisions: filtered
    });
  });

  // 4. Large-SMC Surveillance Funnel
  app.get("/api/smc/surveillance", (_req, res) => {
    res.json({
      updatedAt: new Date().toISOString(),
      watchlist: SMC_SURVEILLANCE_LIST,
      totalWatched: SMC_SURVEILLANCE_LIST.length,
      activeAlerts: SMC_SURVEILLANCE_LIST.filter(i => i.alertStatus === "ALERT_ACTIVE").length
    });
  });

  // 5. Market Analysis & Structure Top-Down
  app.get("/api/analysis", (req, res) => {
    const symbol = (req.query.symbol as string) || "EURUSD";
    if (symbol === "EURUSD") {
      return res.json(EURUSD_ANALYSIS);
    }
    // Return generic fallback analysis for other symbols
    res.json({
      symbol,
      timeframe: (req.query.timeframe as string) || "M5",
      session: "London Open",
      trend: "RANGE",
      lastBOS: null,
      lastCHoCH: null,
      equilibrium50: 1.31300,
      premiumZone: [1.31300, 1.31500],
      discountZone: [1.31100, 1.31300],
      zones: [],
      matchingStrategy: null,
      eligibleSignal: false,
      signalNotes: `Market structure in consolidation for ${symbol}. Waiting for session liquidity sweep.`
    });
  });

  // 6. Trade Journal & Outcomes Ledger
  app.get("/api/journal", (_req, res) => {
    const totalTrades = HISTORICAL_JOURNAL.length;
    const wins = HISTORICAL_JOURNAL.filter(t => t.realizedR > 0).length;
    const totalR = HISTORICAL_JOURNAL.reduce((acc, t) => acc + t.realizedR, 0);
    const winRate = totalTrades > 0 ? (wins / totalTrades) * 100 : 0;

    res.json({
      records: HISTORICAL_JOURNAL,
      metrics: {
        totalTrades,
        winRate: winRate.toFixed(1) + "%",
        totalRealizedR: totalR.toFixed(2) + "R",
        profitFactor: "2.85",
        activeGatedClaims: Object.keys(claimedTickets).length
      }
    });
  });

  // 7. Risk Sizing Calculator
  app.post("/api/risk/calculate", (req, res) => {
    const { balance = 10000, riskPercent = 1.0, entryPrice, stopLoss, symbol = "EURUSD" } = req.body;
    if (!entryPrice || !stopLoss) {
      return res.status(400).json({ error: "entryPrice and stopLoss are required" });
    }

    const slDistance = Math.abs(entryPrice - stopLoss);
    const isJpy = symbol.includes("JPY");
    const isCrypto = symbol.includes("BTC") || symbol.includes("ETH");
    const pipMultiplier = isCrypto ? 1 : isJpy ? 100 : 10000;
    const slPips = slDistance * pipMultiplier;

    const riskAmount = (balance * (riskPercent / 100));
    // Approximate lot sizing: 1 standard FX lot = $10/pip
    let lotSize = 0;
    if (isCrypto) {
      lotSize = parseFloat((riskAmount / slDistance).toFixed(3));
    } else {
      lotSize = parseFloat((riskAmount / (slPips * 10)).toFixed(2));
    }

    res.json({
      symbol,
      balance,
      riskPercent,
      riskAmountUsd: parseFloat(riskAmount.toFixed(2)),
      slDistancePrice: parseFloat(slDistance.toFixed(5)),
      slPips: parseFloat(slPips.toFixed(1)),
      recommendedLotSize: Math.max(lotSize, 0.01),
      tp1_2_5R: entryPrice + (entryPrice > stopLoss ? 2.5 * slDistance : -2.5 * slDistance),
      tp2_5R: entryPrice + (entryPrice > stopLoss ? 5.0 * slDistance : -5.0 * slDistance)
    });
  });

  // 8. Claim Ticket (Manual Management Gate - Authority Rule 5)
  app.post("/api/tickets/claim", (req, res) => {
    const { ticketId } = req.body;
    if (!ticketId) {
      return res.status(400).json({ error: "ticketId is required" });
    }
    claimedTickets[ticketId] = {
      claimedAt: new Date().toISOString(),
      tp1Hit: false,
      beArmed: false,
      status: "CLAIMED_ACTIVE"
    };
    res.json({
      success: true,
      ticketId,
      message: `Ticket ${ticketId} claimed for Phase 6 trade management under independent safety gate.`
    });
  });

  // 9. Stubbed remaining routes per section 1.5 migration protocol
  app.all("/api/*", (_req, res) => {
    res.status(501).json({ error: "Not yet migrated to Node.js web runtime" });
  });

  // Vite integration middleware
  if (process.env.NODE_ENV !== "production") {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: "spa",
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), "dist");
    app.use(express.static(distPath));
    app.get("*", (_req, res) => {
      res.sendFile(path.join(distPath, "index.html"));
    });
  }

  app.listen(PORT, "0.0.0.0", () => {
    console.log(`[AG Profit Trading] Server running on http://0.0.0.0:${PORT}`);
  });
}

startServer();
