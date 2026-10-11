//+------------------------------------------------------------------+
//|                                              SMC_Sniper_EA.mq5    |
//|   SMC method (bias -> POI -> sweep -> CHoCH) as an MT5 Expert     |
//|   Advisor. Port of the smc_bot signal layer.                     |
//|                                                                  |
//|   SAFETY: InpTradingEnabled defaults to FALSE (alert-only).      |
//|   Detectors are BETA, not a proven edge. Backtest in the         |
//|   Strategy Tester and run on a DEMO account before anything      |
//|   else. This is not financial advice.                            |
//+------------------------------------------------------------------+
#property copyright "SMC Sniper EA"
#property version   "1.00"
#property description "SMC: HTF bias + POI, LTF liquidity sweep + CHoCH entry. Signal-only by default."

#include <Trade/Trade.mqh>
CTrade trade;

//====================== INPUTS ======================================
input group "=== General (safety) ==="
input bool    InpTradingEnabled = false;     // FALSE = alert/log only (SAFE DEFAULT). true = place orders.
input double  InpRiskPercent    = 0.5;       // % of equity risked per trade
input ulong   InpMagic          = 550055;    // magic number (isolates this EA's trades)
input long    InpMaxSpreadPoints= 40;        // skip signal if current spread > this (points)
input double  InpMinSLPoints    = 120;       // fee-floor analog: skip if stop is tighter than this (points)

input group "=== Timeframes ==="
input ENUM_TIMEFRAMES InpHTF = PERIOD_H1;    // bias + POI (higher timeframe)
input ENUM_TIMEFRAMES InpLTF = PERIOD_M5;    // sweep + CHoCH entry (lower timeframe)

input group "=== Structure / detection ==="
input int     InpHTFSwing        = 5;        // fractal swing length on HTF
input int     InpLTFSwing        = 3;        // fractal swing length on LTF
input double  InpDisplacementATR = 1.5;      // OB displacement threshold (x ATR)
input int     InpOBLookback      = 60;       // HTF bars to scan for POI
input int     InpSweepLookback   = 50;       // LTF bars to scan for a sweep
input int     InpChochLookback   = 20;       // LTF bars for the CHoCH window
input int     InpATRPeriod       = 14;

input group "=== Risk / exit ==="
input double  InpTargetR         = 2.0;      // reward multiple (TP = R x stop distance)
input double  InpSLBufferPoints  = 20;       // buffer beyond sweep wick / OB (points)
input string  InpEntryMode       = "displacement_trap"; // displacement_trap | refined_ob

//====================== GLOBALS =====================================
datetime g_lastBarTime = 0;

//====================== HELPERS =====================================
// Fetch rates for a timeframe into a SERIES array (index 0 = current forming bar,
// index 1 = last closed bar, higher index = older). Returns bars copied or -1.
int GetRates(ENUM_TIMEFRAMES tf, int count, MqlRates &rates[])
{
   ArraySetAsSeries(rates, true);
   return CopyRates(_Symbol, tf, 0, count, rates);
}

// Simple ATR (mean true range) computed from a series array over `period`
// closed bars starting at series index `startShift` (1 = last closed).
double ComputeATR(const MqlRates &r[], int startShift, int period)
{
   int n = ArraySize(r);
   if(startShift + period + 1 >= n) return 0.0;
   double sum = 0.0;
   for(int i = startShift; i < startShift + period; i++)
   {
      double tr = MathMax(r[i].high - r[i].low,
                  MathMax(MathAbs(r[i].high - r[i+1].close),
                          MathAbs(r[i].low  - r[i+1].close)));
      sum += tr;
   }
   return sum / period;
}

// Fractal swing tests on a SERIES array. i-k are NEWER bars, i+k are OLDER.
bool IsSwingHigh(const MqlRates &r[], int i, int n)
{
   int size = ArraySize(r);
   if(i - n < 1 || i + n > size - 1) return false;   // needs n confirmed bars each side
   for(int k = 1; k <= n; k++)
      if(r[i].high <= r[i-k].high || r[i].high <= r[i+k].high) return false;
   return true;
}
bool IsSwingLow(const MqlRates &r[], int i, int n)
{
   int size = ArraySize(r);
   if(i - n < 1 || i + n > size - 1) return false;
   for(int k = 1; k <= n; k++)
      if(r[i].low >= r[i-k].low || r[i].low >= r[i+k].low) return false;
   return true;
}

// HTF bias: last two swing highs + lows. HH&HL=bullish, LH&LL=bearish, else neutral.
// Returns +1 bullish, -1 bearish, 0 neutral.
int GetBias(const MqlRates &r[], int n)
{
   int size = ArraySize(r);
   double hi[2]; int hiFound = 0;
   double lo[2]; int loFound = 0;
   for(int i = n + 1; i < size - n && (hiFound < 2 || loFound < 2); i++)
   {
      if(hiFound < 2 && IsSwingHigh(r, i, n)) { hi[hiFound++] = r[i].high; }
      if(loFound < 2 && IsSwingLow(r, i, n))  { lo[loFound++] = r[i].low;  }
   }
   if(hiFound < 2 || loFound < 2) return 0;
   bool HH = hi[0] > hi[1];   // hi[0] = most recent
   bool HL = lo[0] > lo[1];
   bool LH = hi[0] < hi[1];
   bool LL = lo[0] < lo[1];
   if(HH && HL) return +1;
   if(LH && LL) return -1;
   return 0;
}

// Active POI: is `price` inside a demand (bias +1) / supply (-1) OB or FVG zone on HTF?
// Fills zoneLow/zoneHigh of the containing zone. Returns true if inside one.
bool GetActivePOI(const MqlRates &r[], int bias, double price, int lookback,
                  double dispATR, double &zoneLow, double &zoneHigh)
{
   int size = ArraySize(r);
   int scan = MathMin(lookback, size - InpATRPeriod - 3);
   for(int i = 1; i < scan; i++)
   {
      double atr = ComputeATR(r, i, InpATRPeriod);
      if(atr <= 0) continue;
      double body = MathAbs(r[i].close - r[i].open);

      // Order block: displacement candle in trade direction; OB = nearest OLDER opposite candle.
      if(body >= dispATR * atr)
      {
         if(bias > 0 && r[i].close > r[i].open)          // bullish displacement
         {
            for(int j = i + 1; j <= i + 6 && j < size; j++)
               if(r[j].close < r[j].open) {              // demand OB candle
                  if(price >= r[j].low && price <= r[j].high) { zoneLow=r[j].low; zoneHigh=r[j].high; return true; }
                  break;
               }
         }
         else if(bias < 0 && r[i].close < r[i].open)     // bearish displacement
         {
            for(int j = i + 1; j <= i + 6 && j < size; j++)
               if(r[j].close > r[j].open) {              // supply OB candle
                  if(price >= r[j].low && price <= r[j].high) { zoneLow=r[j].low; zoneHigh=r[j].high; return true; }
                  break;
               }
         }
      }

      // FVG: 3-candle imbalance (i newer, i+2 older).
      if(i + 2 < size)
      {
         if(bias > 0 && r[i].low > r[i+2].high)          // bullish FVG
            if(price >= r[i+2].high && price <= r[i].low) { zoneLow=r[i+2].high; zoneHigh=r[i].low; return true; }
         if(bias < 0 && r[i].high < r[i+2].low)          // bearish FVG
            if(price >= r[i].high && price <= r[i+2].low) { zoneLow=r[i].high; zoneHigh=r[i+2].low; return true; }
      }
   }
   return false;
}

// Liquidity sweep on LTF. Fills sweptLevel + wickExtreme + sweepShift (series index).
bool GetSweep(const MqlRates &r[], int bias, int lookback, int swingN,
              double &sweptLevel, double &wickExtreme, int &sweepShift)
{
   int size = ArraySize(r);
   int scan = MathMin(lookback, size - swingN - 1);
   // recent bars = small index; look for a bar that pierced a prior swing level and closed back.
   for(int k = 1; k < scan; k++)
   {
      // find a swing level OLDER than k
      for(int i = k + swingN + 1; i < size - swingN; i++)
      {
         if(bias > 0 && IsSwingLow(r, i, swingN))
         {
            double lvl = r[i].low;
            if(r[k].low < lvl && r[k].close > lvl)
            { sweptLevel=lvl; wickExtreme=r[k].low; sweepShift=k; return true; }
         }
         if(bias < 0 && IsSwingHigh(r, i, swingN))
         {
            double lvl = r[i].high;
            if(r[k].high > lvl && r[k].close < lvl)
            { sweptLevel=lvl; wickExtreme=r[k].high; sweepShift=k; return true; }
         }
      }
   }
   return false;
}

// CHoCH: after the sweep, last closed bar breaks the nearest minor swing since the sweep.
bool GetChoCH(const MqlRates &r[], int bias, int sweepShift, int lookback)
{
   int size = ArraySize(r);
   int minorN = MathMax(1, lookback / 8);
   double lastClose = r[1].close;                 // last CLOSED bar (series index 1)
   // nearest minor swing between the sweep (older, larger index) and now (index 1)
   for(int i = 2; i < sweepShift && i < size - minorN; i++)
   {
      if(bias > 0 && IsSwingHigh(r, i, minorN))
         return (lastClose > r[i].high);           // break nearest minor high
      if(bias < 0 && IsSwingLow(r, i, minorN))
         return (lastClose < r[i].low);
   }
   return false;
}

// Position sizing by % risk given stop distance (price units).
double CalcLots(double entry, double sl)
{
   double riskMoney = AccountInfoDouble(ACCOUNT_EQUITY) * InpRiskPercent / 100.0;
   double slDist    = MathAbs(entry - sl);
   double tickVal   = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double tickSize  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(slDist <= 0 || tickVal <= 0 || tickSize <= 0) return 0.0;
   double lossPerLot = (slDist / tickSize) * tickVal;
   if(lossPerLot <= 0) return 0.0;
   double lots = riskMoney / lossPerLot;

   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double minL = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxL = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   if(step > 0) lots = MathFloor(lots / step) * step;
   lots = MathMax(minL, MathMin(maxL, lots));
   return lots;
}

bool HasOpenPosition()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) == _Symbol &&
         PositionGetInteger(POSITION_MAGIC) == (long)InpMagic)
         return true;
   }
   return false;
}

bool IsNewBar()
{
   datetime t = iTime(_Symbol, InpLTF, 0);
   if(t == g_lastBarTime) return false;
   g_lastBarTime = t;
   return true;
}

//====================== CORE: build + act ==========================
void ProcessSignal()
{
   if(HasOpenPosition()) return;                                   // one position at a time

   long spread = (long)SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
   if(spread > InpMaxSpreadPoints) return;                         // spread guard

   MqlRates htf[]; MqlRates ltf[];
   if(GetRates(InpHTF, InpOBLookback + InpATRPeriod + 10, htf) <= 0) return;
   if(GetRates(InpLTF, InpSweepLookback + InpChochLookback + 10, ltf) <= 0) return;

   int bias = GetBias(htf, InpHTFSwing);
   if(bias == 0) return;

   double price = (bias > 0) ? SymbolInfoDouble(_Symbol, SYMBOL_ASK)
                             : SymbolInfoDouble(_Symbol, SYMBOL_BID);

   double zLow, zHigh;
   if(!GetActivePOI(htf, bias, price, InpOBLookback, InpDisplacementATR, zLow, zHigh)) return;

   double sweptLevel, wickExtreme; int sweepShift;
   if(!GetSweep(ltf, bias, InpSweepLookback, InpLTFSwing, sweptLevel, wickExtreme, sweepShift)) return;

   if(!GetChoCH(ltf, bias, sweepShift, InpChochLookback)) return;

   // ---- entry / stop by mode ----
   double buffer = InpSLBufferPoints * _Point;
   double entry, sl;
   bool   isLimit = false;
   if(InpEntryMode == "refined_ob")
   {
      entry   = (zLow + zHigh) / 2.0;                              // limit at OB midpoint
      sl      = (bias > 0) ? zLow - buffer : zHigh + buffer;
      isLimit = true;
   }
   else // displacement_trap (default): market at CHoCH, stop beyond the sweep wick
   {
      entry = price;
      sl    = (bias > 0) ? wickExtreme - buffer : wickExtreme + buffer;
   }

   double slDist = MathAbs(entry - sl);
   if(slDist / _Point < InpMinSLPoints) return;                   // fee-floor analog: reject too-tight stop

   double tp = (bias > 0) ? entry + InpTargetR * slDist
                          : entry - InpTargetR * slDist;

   string dir = (bias > 0) ? "BUY" : "SELL";
   string msg = StringFormat("SMC %s %s  entry=%.5f sl=%.5f tp=%.5f  slPts=%.0f  mode=%s",
                             dir, _Symbol, entry, sl, tp, slDist/_Point, InpEntryMode);

   if(!InpTradingEnabled)                                         // SIGNAL-ONLY default
   {
      Print("[SIGNAL-ONLY] ", msg);
      Comment("[SIGNAL-ONLY] ", msg);
      return;
   }

   double lots = CalcLots(entry, sl);
   if(lots <= 0) { Print("lot calc failed, skip: ", msg); return; }

   trade.SetExpertMagicNumber(InpMagic);
   bool ok = false;
   if(bias > 0)
      ok = isLimit ? trade.BuyLimit(lots, entry, _Symbol, sl, tp, ORDER_TIME_GTC, 0, "smc")
                   : trade.Buy(lots, _Symbol, 0.0, sl, tp, "smc");
   else
      ok = isLimit ? trade.SellLimit(lots, entry, _Symbol, sl, tp, ORDER_TIME_GTC, 0, "smc")
                   : trade.Sell(lots, _Symbol, 0.0, sl, tp, "smc");

   Print(ok ? "[PLACED] " : "[FAILED] ", msg, "  ret=", trade.ResultRetcode());
}

//====================== EVENT HANDLERS =============================
int OnInit()
{
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetTypeFillingBySymbol(_Symbol);
   PrintFormat("SMC_Sniper_EA init. TradingEnabled=%s  HTF=%s LTF=%s  mode=%s",
               (InpTradingEnabled ? "TRUE" : "FALSE"),
               EnumToString(InpHTF), EnumToString(InpLTF), InpEntryMode);
   if(InpTradingEnabled)
      Print("WARNING: live order placement is ENABLED. Confirm this is a DEMO account.");
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason) { Comment(""); }

void OnTick()
{
   if(!IsNewBar()) return;      // act once per closed LTF bar
   ProcessSignal();
}
//+------------------------------------------------------------------+
