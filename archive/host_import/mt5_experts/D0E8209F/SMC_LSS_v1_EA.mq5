//+------------------------------------------------------------------+
//|                                              SMC_LSS_v1_EA.mq5     |
//|   Smart-Money-Concepts Liquidity-Sweep Strategy — MT5 backtest EA |
//|   Pragmatic MVP port of SMC-LSS v1.2 spec (EURUSD)                |
//|                                                                    |
//|   Scope (MVP): D1 bias -> level marking -> M5 sweep -> displacement|
//|   -> FVG -> pullback entry, spread+bias gates, swept-level SL,     |
//|   3-tier TP (3R/40, <=4R/30, <=6R/30), BE, opposing-CHoCH &        |
//|   stagnation exits, fixed-fractional sizing, one position/symbol.  |
//|                                                                    |
//|   Divergences from the Python spec are noted in the accompanying   |
//|   response and inline where relevant. NOT financial advice; for    |
//|   research backtesting only. No live self-execution.               |
//+------------------------------------------------------------------+
#property copyright "SMC-LSS research MVP"
#property version   "1.01"
#property strict

#include <Trade/Trade.mqh>

//======================= INPUTS =====================================
input group "Risk & sizing"
input double InpRiskPercent        = 1.0;    // Risk % of balance per trade
input double InpCounterTrendMult   = 0.5;    // Size multiplier for counter-trend trades
input bool   InpAllowCounterTrend  = true;   // Allow counter-trend (needs D1-level sweep)
input double InpMaxDailyLossPct    = 5.0;    // Hard daily loss halt (% of day-start balance)

input group "D1 bias"
input int    InpBiasLookbackDays   = 10;     // D1 lookback for structure break
input int    InpFractalN           = 2;      // Fractal half-width (bars each side)

input group "Level marking"
input int    InpH1SwingLookback    = 10;     // H1 swings to mark
input double InpLevelTolPips       = 3.0;    // Tolerance to associate a sweep with a marked level

input group "Entry microstructure (M5)"
input double InpDisplacementATR    = 1.5;    // Displacement body >= x * ATR14(M5)
input double InpOuterClosePct      = 0.25;   // Close must be within outer x of candle range
input int    InpSweepLookback      = 6;      // Bars before displacement to find the sweep
input int    InpPullbackWindow     = 12;     // Bars to wait for pullback into FVG before expiring

input group "Stops & targets"
input double InpSLbufferATR        = 0.1;    // SL buffer = max(x*ATR, spread)
input double InpTP1_R              = 3.0;    // TP1 in R
input double InpTP1Pct             = 40.0;   // % closed at TP1
input double InpTP2capR            = 4.0;    // TP2 R cap
input double InpTP2Pct             = 30.0;   // % closed at TP2
input double InpTP3capR            = 6.0;    // TP3 R cap
input double InpTP3Pct             = 30.0;   // remainder at TP3

input group "Exits"
input int    InpStagnationBars     = 48;     // M5 bars (~4h) with no progress -> close
input double InpMaxSpreadPips      = 2.0;    // Spread gate (EURUSD)

input group "Misc"
input ulong  InpMagic              = 20260713;

//======================= GLOBALS ====================================
CTrade  trade;

int     hATR_M5;                 // ATR14 M5 handle
datetime lastD1Time = 0;
datetime lastM5Time = 0;

// Daily bias
int      g_bias = 0;             // 1 bull, -1 bear, 0 neutral

// Marked liquidity levels (prices) for current session
double   g_levels[];             // untapped marked levels
double   g_swings[];             // H1/D1 swing points (for TP3)

// Daily loss halt
double   g_dayStartBalance = 0;
datetime g_dayStamp        = 0;

// Pending setup (post-displacement, awaiting pullback into FVG)
struct SetupState
{
   bool     active;
   int      dir;          // +1 long, -1 short
   double   fvgTop;
   double   fvgBottom;
   double   sweptLevel;   // level whose sweep triggered the setup (for SL)
   bool     counterTrend;
   int      barsWaited;
};
SetupState g_setup;

// Active trade plan
struct TradePlan
{
   bool     active;
   int      dir;
   double   entry;
   double   sl;
   double   Rdist;
   double   tp1, tp2, tp3;
   double   poiTop, poiBottom;   // FVG zone that produced the entry
   double   initVolume;
   bool     tp1Done, tp2Done;
   bool     beMoved;
   int      barsSince;
   double   invalidationLevel;   // opposing-CHoCH reference (pre-entry M5 swing)
};
TradePlan g_plan;

//======================= UTIL =======================================
double PipSize()
{
   // For 5/3-digit brokers a pip = 10 points; for 4/2-digit a pip = 1 point.
   int d = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   double pt = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   if(d == 3 || d == 5) return pt * 10.0;
   return pt;
}

double SpreadPrice()
{
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   return (ask - bid);
}

double ATR_M5(int shift)
{
   double buf[];
   if(CopyBuffer(hATR_M5, 0, shift, 1, buf) != 1) return 0.0;
   return buf[0];
}

bool IsNewBar(ENUM_TIMEFRAMES tf, datetime &store)
{
   datetime t = iTime(_Symbol, tf, 0);
   if(t != store) { store = t; return true; }
   return false;
}

void ArrPush(double &arr[], double v)
{
   int n = ArraySize(arr);
   ArrayResize(arr, n + 1);
   arr[n] = v;
}

//======================= INIT =======================================
int OnInit()
{
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetTypeFillingBySymbol(_Symbol);
   hATR_M5 = iATR(_Symbol, PERIOD_M5, 14);
   if(hATR_M5 == INVALID_HANDLE)
   {
      Print("Failed to create ATR handle");
      return INIT_FAILED;
   }
   g_setup.active = false;
   g_plan.active  = false;
   g_dayStartBalance = AccountInfoDouble(ACCOUNT_BALANCE);
   Print("SMC-LSS v1 EA initialised on ", _Symbol);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   if(hATR_M5 != INVALID_HANDLE) IndicatorRelease(hATR_M5);
}

//======================= D1 BIAS (Step 1/2) =========================
// Scan D1 bars in lookback, track fractal swings and the most recent
// confirmed structure break. Sets g_bias and fills g_swings (D1 part).
void UpdateDailyBias()
{
   int N   = InpFractalN;
   int look = InpBiasLookbackDays + 2 * N + 2;
   int bars = MathMin(look, iBars(_Symbol, PERIOD_D1) - 1);
   if(bars < 2 * N + 3) { g_bias = 0; return; }

   double runHigh = 0, runLow = 0;
   bool   haveHigh = false, haveLow = false;
   int    lastBreak = 0;

   // iterate oldest -> newest (skip forming bar 0)
   for(int shift = bars; shift >= 1; shift--)
   {
      // fractal centred at 'shift' needs N bars either side that are closed
      if(shift >= N + 1 && shift <= bars - N)
      {
         double hc = iHigh(_Symbol, PERIOD_D1, shift);
         double lc = iLow(_Symbol, PERIOD_D1, shift);
         bool isHigh = true, isLow = true;
         for(int k = 1; k <= N; k++)
         {
            if(iHigh(_Symbol, PERIOD_D1, shift + k) >= hc ||
               iHigh(_Symbol, PERIOD_D1, shift - k) >= hc) isHigh = false;
            if(iLow(_Symbol, PERIOD_D1, shift + k) <= lc ||
               iLow(_Symbol, PERIOD_D1, shift - k) <= lc) isLow = false;
         }
         if(isHigh) { runHigh = hc; haveHigh = true; }
         if(isLow)  { runLow  = lc; haveLow  = true; }
      }
      double c = iClose(_Symbol, PERIOD_D1, shift);
      if(haveHigh && c > runHigh) lastBreak = 1;
      if(haveLow  && c < runLow)  lastBreak = -1;
   }
   g_bias = lastBreak;

   // collect D1 swings for TP3 pool
   ArrayResize(g_swings, 0);
   for(int shift = bars - N; shift >= N + 1; shift--)
   {
      double hc = iHigh(_Symbol, PERIOD_D1, shift);
      double lc = iLow(_Symbol, PERIOD_D1, shift);
      bool isHigh = true, isLow = true;
      for(int k = 1; k <= N; k++)
      {
         if(iHigh(_Symbol, PERIOD_D1, shift + k) >= hc ||
            iHigh(_Symbol, PERIOD_D1, shift - k) >= hc) isHigh = false;
         if(iLow(_Symbol, PERIOD_D1, shift + k) <= lc ||
            iLow(_Symbol, PERIOD_D1, shift - k) <= lc) isLow = false;
      }
      if(isHigh) ArrPush(g_swings, hc);
      if(isLow)  ArrPush(g_swings, lc);
   }
}

//======================= LEVEL MARKING (Step 3) =====================
// PDH, PDL, daily open, and H1 swing highs/lows. Rebuilt once per D1.
void MarkLevels()
{
   ArrayResize(g_levels, 0);
   // Previous day high / low / open  (shift 1 = yesterday closed D1)
   double pdh = iHigh(_Symbol, PERIOD_D1, 1);
   double pdl = iLow(_Symbol,  PERIOD_D1, 1);
   double dop = iOpen(_Symbol, PERIOD_D1, 0);
   ArrPush(g_levels, pdh);
   ArrPush(g_levels, pdl);
   ArrPush(g_levels, dop);

   // H1 swing highs/lows (fractal N=2) over lookback
   int N = 2;
   int need = InpH1SwingLookback + 2 * N + 2;
   int bars = MathMin(need, iBars(_Symbol, PERIOD_H1) - 1);
   for(int shift = bars - N; shift >= N + 1; shift--)
   {
      double hc = iHigh(_Symbol, PERIOD_H1, shift);
      double lc = iLow(_Symbol,  PERIOD_H1, shift);
      bool isHigh = true, isLow = true;
      for(int k = 1; k <= N; k++)
      {
         if(iHigh(_Symbol, PERIOD_H1, shift + k) >= hc ||
            iHigh(_Symbol, PERIOD_H1, shift - k) >= hc) isHigh = false;
         if(iLow(_Symbol, PERIOD_H1, shift + k) <= lc ||
            iLow(_Symbol, PERIOD_H1, shift - k) <= lc) isLow = false;
      }
      if(isHigh) { ArrPush(g_levels, hc); ArrPush(g_swings, hc); }
      if(isLow)  { ArrPush(g_levels, lc); ArrPush(g_swings, lc); }
   }
}

// Was a marked level swept by candle at 'shift' (wick beyond, close back)?
// dir = +1 : looking for a swept LOW (bullish setup). Returns level price
// via &lvl, and whether the swept level was a D1-significant level.
bool DetectSweep(int shift, int dir, double &lvl, bool &isD1level)
{
   double tol = InpLevelTolPips * PipSize();
   double hi  = iHigh(_Symbol, PERIOD_M5, shift);
   double lo  = iLow(_Symbol,  PERIOD_M5, shift);
   double cl  = iClose(_Symbol, PERIOD_M5, shift);
   double pdh = iHigh(_Symbol, PERIOD_D1, 1);
   double pdl = iLow(_Symbol,  PERIOD_D1, 1);

   for(int i = 0; i < ArraySize(g_levels); i++)
   {
      double L = g_levels[i];
      if(dir > 0) // bullish: sweep a low -> wick below L, close back above
      {
         if(lo < L - tol && cl > L)
         {
            lvl = L;
            isD1level = (MathAbs(L - pdl) < tol || MathAbs(L - pdh) < tol);
            return true;
         }
      }
      else        // bearish: sweep a high -> wick above L, close back below
      {
         if(hi > L + tol && cl < L)
         {
            lvl = L;
            isD1level = (MathAbs(L - pdl) < tol || MathAbs(L - pdh) < tol);
            return true;
         }
      }
   }
   return false;
}

//======================= SETUP DETECTION (Steps 4/6) ================
// Evaluated on each closed M5 bar. Displacement candle = shift 2 so the
// 3-candle FVG (shift3, shift2, shift1) is fully closed => no lookahead.
void ScanForSetup()
{
   double atr = ATR_M5(2);
   if(atr <= 0) return;

   double o2 = iOpen(_Symbol, PERIOD_M5, 2);
   double c2 = iClose(_Symbol, PERIOD_M5, 2);
   double h2 = iHigh(_Symbol, PERIOD_M5, 2);
   double l2 = iLow(_Symbol,  PERIOD_M5, 2);
   double body = MathAbs(c2 - o2);
   double rng  = h2 - l2;
   if(rng <= 0) return;

   int dir = (c2 > o2) ? 1 : -1;

   // Displacement test
   if(body < InpDisplacementATR * atr) return;
   double closePos = (dir > 0) ? (c2 - l2) / rng : (h2 - c2) / rng; // 1 = at extreme
   if(closePos < (1.0 - InpOuterClosePct)) return;

   // 3-candle FVG around displacement (shift3, shift2, shift1)
   double h3 = iHigh(_Symbol, PERIOD_M5, 3);
   double l3 = iLow(_Symbol,  PERIOD_M5, 3);
   double h1 = iHigh(_Symbol, PERIOD_M5, 1);
   double l1 = iLow(_Symbol,  PERIOD_M5, 1);
   double fvgTop, fvgBottom;
   if(dir > 0)
   {
      if(!(h3 < l1)) return;         // bullish FVG requires gap up
      fvgBottom = h3;
      fvgTop    = l1;
   }
   else
   {
      if(!(l3 > h1)) return;         // bearish FVG requires gap down
      fvgBottom = h1;
      fvgTop    = l3;
   }

   // Sweep must precede displacement and hit a marked level
   double lvl = 0.0; bool isD1level = false; bool found = false;
   for(int s = 2; s <= 2 + InpSweepLookback; s++)
   {
      if(DetectSweep(s, dir, lvl, isD1level)) { found = true; break; }
   }
   if(!found) return;

   // Bias gate (Step 2)
   bool counter = false;
   if(g_bias == 0) return;                       // neutral -> skip
   if(dir != g_bias)
   {
      if(!InpAllowCounterTrend) return;
      if(!isD1level) return;                      // counter-trend needs D1-level sweep
      counter = true;
   }

   // Register setup
   g_setup.active       = true;
   g_setup.dir          = dir;
   g_setup.fvgTop       = fvgTop;
   g_setup.fvgBottom    = fvgBottom;
   g_setup.sweptLevel   = lvl;
   g_setup.counterTrend = counter;
   g_setup.barsWaited   = 0;
}

//======================= TP LEVEL SELECTION (Step 8) ================
// nearest opposing marked level beyond 'entry' in trade direction
double NearestOpposingLevel(int dir, double entry)
{
   double best = 0; bool have = false;
   for(int i = 0; i < ArraySize(g_levels); i++)
   {
      double L = g_levels[i];
      if(dir > 0 && L > entry) { if(!have || L < best) { best = L; have = true; } }
      if(dir < 0 && L < entry) { if(!have || L > best) { best = L; have = true; } }
   }
   return have ? best : 0.0;
}

double NearestSwingBeyond(int dir, double refLevel)
{
   double best = 0; bool have = false;
   for(int i = 0; i < ArraySize(g_swings); i++)
   {
      double L = g_swings[i];
      if(dir > 0 && L > refLevel) { if(!have || L < best) { best = L; have = true; } }
      if(dir < 0 && L < refLevel) { if(!have || L > best) { best = L; have = true; } }
   }
   return have ? best : 0.0;
}

//======================= POSITION SIZING (Step 10) ==================
double CalcLots(double riskMoney, double stopPrice)
{
   double tickVal = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double tickSz  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tickSz <= 0 || tickVal <= 0 || stopPrice <= 0) return 0.0;
   double lossPerLot = (stopPrice / tickSz) * tickVal;
   if(lossPerLot <= 0) return 0.0;
   double lots = riskMoney / lossPerLot;

   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double vmin = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double vmax = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   lots = MathFloor(lots / step) * step;
   if(lots < vmin) lots = vmin;      // MVP: honour broker minimum
   if(lots > vmax) lots = vmax;
   return lots;
}

//======================= ENTRY (Step 6/7/8) =========================
void TryEnter()
{
   if(!g_setup.active) return;

   int dir = g_setup.dir;
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);

   // pullback into FVG zone [fvgBottom, fvgTop]. If price blows fully through
   // the gap, the FVG is filled/invalid -> drop the setup (no chasing).
   bool touched = false;
   double lo1 = iLow(_Symbol,  PERIOD_M5, 1);
   double hi1 = iHigh(_Symbol, PERIOD_M5, 1);
   if(dir > 0)
   {
      if(lo1 < g_setup.fvgBottom) { g_setup.active = false; return; }
      if(lo1 <= g_setup.fvgTop)     touched = true;
   }
   else
   {
      if(hi1 > g_setup.fvgTop)    { g_setup.active = false; return; }
      if(hi1 >= g_setup.fvgBottom)  touched = true;
   }

   g_setup.barsWaited++;
   if(!touched)
   {
      if(g_setup.barsWaited > InpPullbackWindow) g_setup.active = false;
      return;
   }

   // Spread gate (Step 5)
   double spr = SpreadPrice();
   if(spr > InpMaxSpreadPips * PipSize()) { g_setup.active = false; return; }

   // Entry at FVG touch (near edge)
   double entry = (dir > 0) ? ask : bid;

   // SL = swept level -/+ max(0.1*ATR, spread)   (Step 7)
   double atr = ATR_M5(1);
   double buf = MathMax(InpSLbufferATR * atr, spr);
   double sl  = (dir > 0) ? (g_setup.sweptLevel - buf) : (g_setup.sweptLevel + buf);
   double Rdist = MathAbs(entry - sl);
   if(Rdist <= 0) { g_setup.active = false; return; }

   // TP tiers (Step 8)
   double tp1 = (dir > 0) ? entry + InpTP1_R * Rdist : entry - InpTP1_R * Rdist;

   double opp = NearestOpposingLevel(dir, entry);
   double tp2cap = (dir > 0) ? entry + InpTP2capR * Rdist : entry - InpTP2capR * Rdist;
   double tp2;
   if(opp == 0) tp2 = tp2cap;
   else tp2 = (dir > 0) ? MathMin(opp, tp2cap) : MathMax(opp, tp2cap);

   double swBeyond = NearestSwingBeyond(dir, tp2);
   double tp3cap = (dir > 0) ? entry + InpTP3capR * Rdist : entry - InpTP3capR * Rdist;
   double tp3;
   if(swBeyond == 0) tp3 = tp3cap;
   else tp3 = (dir > 0) ? MathMin(swBeyond, tp3cap) : MathMax(swBeyond, tp3cap);

   // Sizing
   double riskPct = InpRiskPercent * (g_setup.counterTrend ? InpCounterTrendMult : 1.0);
   double riskMoney = AccountInfoDouble(ACCOUNT_BALANCE) * riskPct / 100.0;
   double lots = CalcLots(riskMoney, Rdist);
   if(lots <= 0) { g_setup.active = false; return; }

   bool ok;
   if(dir > 0) ok = trade.Buy(lots, _Symbol, 0.0, sl, 0.0, "SMC-LSS");
   else        ok = trade.Sell(lots, _Symbol, 0.0, sl, 0.0, "SMC-LSS");
   if(!ok) { g_setup.active = false; return; }

   // Record plan
   g_plan.active   = true;
   g_plan.dir      = dir;
   g_plan.entry    = entry;
   g_plan.sl       = sl;
   g_plan.Rdist    = Rdist;
   g_plan.tp1      = tp1;
   g_plan.tp2      = tp2;
   g_plan.tp3      = tp3;
   g_plan.poiTop   = g_setup.fvgTop;
   g_plan.poiBottom= g_setup.fvgBottom;
   g_plan.initVolume = lots;
   g_plan.tp1Done  = false;
   g_plan.tp2Done  = false;
   g_plan.beMoved  = false;
   g_plan.barsSince= 0;
   g_plan.invalidationLevel = g_setup.sweptLevel;   // CHoCH proxy: failed reclaim of the swept level

   g_setup.active = false;
}

//======================= EXIT MANAGEMENT (Step 9) ===================
bool HasOpenPosition()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) == _Symbol &&
         PositionGetInteger(POSITION_MAGIC) == (long)InpMagic)
         return true;
   }
   return false;
}

double CurrentVolume()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) == _Symbol &&
         PositionGetInteger(POSITION_MAGIC) == (long)InpMagic)
         return PositionGetDouble(POSITION_VOLUME);
   }
   return 0.0;
}

void PartialClose(double pct)
{
   double vol = g_plan.initVolume * pct / 100.0;
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double vmin = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   vol = MathFloor(vol / step) * step;
   double cur = CurrentVolume();
   if(vol < vmin || vol >= cur) { trade.PositionClose(_Symbol); return; }
   trade.PositionClosePartial(_Symbol, vol);
}

void ManagePosition()
{
   if(!HasOpenPosition()) { g_plan.active = false; return; }
   if(!g_plan.active) return;

   int dir = g_plan.dir;
   double c1 = iClose(_Symbol, PERIOD_M5, 1);
   double h1 = iHigh(_Symbol, PERIOD_M5, 1);
   double l1 = iLow(_Symbol,  PERIOD_M5, 1);
   g_plan.barsSince++;

   bool progressed = false;

   // TP3 -> close remainder
   if(g_plan.tp1Done && g_plan.tp2Done)
   {
      if((dir > 0 && h1 >= g_plan.tp3) || (dir < 0 && l1 <= g_plan.tp3))
      { trade.PositionClose(_Symbol); g_plan.active = false; return; }
   }

   // TP2 -> close 30%
   if(g_plan.tp1Done && !g_plan.tp2Done)
   {
      if((dir > 0 && h1 >= g_plan.tp2) || (dir < 0 && l1 <= g_plan.tp2))
      { PartialClose(InpTP2Pct); g_plan.tp2Done = true; progressed = true; }
   }

   // TP1 -> close 40%, arm breakeven
   if(!g_plan.tp1Done)
   {
      if((dir > 0 && h1 >= g_plan.tp1) || (dir < 0 && l1 <= g_plan.tp1))
      {
         PartialClose(InpTP1Pct);
         g_plan.tp1Done = true;
         progressed = true;
      }
      else
      {
         // Opposing CHoCH before TP1 -> invalidation full close
         if((dir > 0 && c1 < g_plan.invalidationLevel) ||
            (dir < 0 && c1 > g_plan.invalidationLevel))
         { trade.PositionClose(_Symbol); g_plan.active = false; return; }
      }
   }

   // Breakeven: once a candle CLOSES beyond the POI/FVG zone in our favour,
   // move SL to entry (spec Step 8 — NOT gated on TP1; the earlier gating was
   // the bug). Cuts full-size SL losses on trades that extend then reverse.
   if(!g_plan.beMoved)
   {
      bool beyondPOI = (dir > 0 && c1 > g_plan.poiTop) || (dir < 0 && c1 < g_plan.poiBottom);
      if(beyondPOI)
      {
         if(trade.PositionModify(_Symbol, g_plan.entry, 0.0))
            g_plan.beMoved = true;
      }
   }

   // Stagnation exit
   if(!g_plan.tp1Done && !progressed && g_plan.barsSince >= InpStagnationBars)
   { trade.PositionClose(_Symbol); g_plan.active = false; return; }
}

//======================= DAILY LOSS HALT (Step 10) ==================
bool DailyHaltActive()
{
   datetime today = iTime(_Symbol, PERIOD_D1, 0);
   if(today != g_dayStamp)
   {
      g_dayStamp = today;
      g_dayStartBalance = AccountInfoDouble(ACCOUNT_BALANCE);
   }
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   double dd = g_dayStartBalance - eq;
   return (dd >= g_dayStartBalance * InpMaxDailyLossPct / 100.0);
}

//======================= MAIN LOOP ==================================
void OnTick()
{
   // Refresh D1-dependent context once per new D1 bar
   if(IsNewBar(PERIOD_D1, lastD1Time))
   {
      UpdateDailyBias();
      MarkLevels();
   }

   // Everything else acts on closed M5 bars only (no-lookahead)
   if(!IsNewBar(PERIOD_M5, lastM5Time)) return;

   // Manage any open position first
   if(HasOpenPosition()) { ManagePosition(); return; }
   else g_plan.active = false;

   // One position per instrument: no new entries while one is open (handled above)
   if(DailyHaltActive()) return;

   // Progress a pending setup (pullback -> entry), else look for a new one.
   // A setup registered on THIS bar waits for a genuine pullback next bar —
   // no same-bar entry at the FVG edge (that was entering at bad prices).
   if(g_setup.active) TryEnter();
   else               ScanForSetup();
}
//+------------------------------------------------------------------+