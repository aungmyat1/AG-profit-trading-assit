//+------------------------------------------------------------------+
//|                              MT5_EA_1BullBear_ICT_SMC.mq5         |
//|            1BullBear(R) ICT/SMC Order Block Strategy - v5 engine   |
//|            Reconstructed from MT5_Strategy_Data.md spec           |
//|                                                                   |
//|  Style : Day/Swing. HTF context H4/D1, entries on H1.             |
//|  Attach to an H1 chart of EUR/USD, GBP/USD or XAU/USD.            |
//|                                                                   |
//|  NOTE: This EA reconstructs the documented logic for BACKTESTING  |
//|        / FORWARD-TESTING and education. The strategy has no       |
//|        proven statistical edge (see disclaimer in the spec).      |
//|        Do NOT trade live money unverified.                        |
//+------------------------------------------------------------------+
#property copyright "1BullBear ICT/SMC - educational reconstruction"
#property version   "5.00"
#property strict

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>

CTrade         trade;
CPositionInfo  posinfo;

//====================================================================
//  INPUT PARAMETERS
//====================================================================

//--- Risk Management -------------------------------------------------
input group "=== Risk Management ==="
input double InpRiskPercent      = 1.0;    // Risk % per trade (of equity)
input double InpMaxDailyDD       = 3.0;    // Max daily drawdown % (halt)
input double InpMaxWeeklyDD      = 6.0;    // Max weekly drawdown %
input int    InpMaxOpenTrades    = 2;      // Max simultaneous open trades
input double InpMinRR            = 1.0;    // Min R:R to enter

//--- Partial Close & Take Profit ------------------------------------
input group "=== Partial Close / TP ==="
input double InpPartialClosePct  = 50.0;   // % of position to close at TP1
input bool   InpMoveSLtoBE       = true;   // Move SL to entry after TP1
input int    InpMaxBarsHeld      = 80;     // Max bars to hold (time stop)

//--- Order Block Detection ------------------------------------------
input group "=== Order Block ==="
input int    InpOBLookback       = 80;     // Bars lookback for OB zone calc
input double InpDisplacementMult = 0.4;    // Displacement mult (0.4 FX / 0.8 Gold)
input int    InpOBExpiry         = 80;     // OB expires after N bars w/o retest
input int    InpMinBarsBetweenTrades = 8;  // Min bars between trades

//--- FVG Detection ---------------------------------------------------
input group "=== FVG ==="
input bool   InpRequireFVG       = true;   // Require FVG confluence

//--- Confluence Scoring ---------------------------------------------
input group "=== Confluence ==="
input int    InpMinConfluence    = 4;      // Min score to enter (2-8)

//--- Premium/Discount & OTE -----------------------------------------
input group "=== Zones ==="
input double InpOTE_Lower        = 0.58;   // OTE zone lower (Fib)
input double InpOTE_Upper        = 0.82;   // OTE zone upper (Fib)
input double InpDiscountMax      = 0.62;   // Discount max (below=buy only)
input double InpPremiumMin       = 0.38;   // Premium min (above=sell only)

//--- Swing Structure -------------------------------------------------
input group "=== Swings ==="
input int    InpSwingConfirmBars = 2;      // Bars each side to confirm swing
input int    InpSwingLookback    = 120;    // Lookback for swing detection

//--- Liquidity Sweep -------------------------------------------------
input group "=== Liquidity ==="
input int    InpLiqSweepLookback = 30;     // Bars to check liquidity sweep

//--- DOL (Draw on Liquidity) ----------------------------------------
input group "=== DOL ==="
input int    InpDOLLookback      = 60;     // Bars to search DOL target
input double InpEqualTolerance   = 0.001;  // Tolerance equal highs/lows (0.1%)

//--- Killzone Session Filter (UTC) ----------------------------------
input group "=== Killzone (UTC) ==="
input bool   InpUseKillzoneFilter = false; // Enable session filter
input int    InpLondonStart      = 7;
input int    InpLondonEnd        = 10;
input int    InpNYAMStart        = 13;
input int    InpNYAMEnd          = 17;
input int    InpNYPMBegin        = 17;
input int    InpNYPMEnd          = 21;

//--- Misc ------------------------------------------------------------
input group "=== Misc ==="
input long   InpMagic            = 1120250714; // Magic number
input int    InpBrokerGMTOffset  = 0;      // Broker server GMT offset (hours)
input bool   InpVerboseLog       = false;  // Print debug logs

//====================================================================
//  PER-SYMBOL CONFIG  (pip buffer, half-spread, displacement)
//====================================================================
double g_pipBuffer  = 0.0018;   // resolved in OnInit
double g_halfSpread = 0.00008;  // resolved in OnInit
double g_dispMult   = 0.4;      // resolved in OnInit (Gold overrides input)

//====================================================================
//  DATA STRUCTURES
//====================================================================
enum ENUM_TREND { TREND_NONE=0, TREND_BULL=1, TREND_BEAR=-1 };

// An order block awaiting FVG registration then retest.
struct OrderBlock
{
   bool     used;          // slot occupied
   bool     registered;    // FVG check done (ready for retest)
   bool     isBull;        // bullish (long) OB
   datetime createTime;    // time of the OB candle
   double   obHigh;        // OB zone high (wick)
   double   obLow;         // OB zone low (wick)
   double   obMid;         // 50% of OB zone
   int      score;         // confluence score
   bool     fvgOK;         // FVG confirmed
   int      ageBars;       // bars since creation
};

#define MAX_OB 64
OrderBlock g_ob[MAX_OB];

//--- state -----------------------------------------------------------
datetime g_lastBarTime    = 0;
int      g_barsSinceTrade = 100000;

double   g_dayStartEquity  = 0.0;
double   g_weekStartEquity = 0.0;
int      g_curDay  = -1;
int      g_curWeek = -1;
bool     g_haltDay  = false;
bool     g_haltWeek = false;

//====================================================================
//  UTILITY
//====================================================================
void Log(string s){ if(InpVerboseLog) Print(s); }

int SymDigits(){ return (int)SymbolInfoInteger(_Symbol,SYMBOL_DIGITS); }

// Broker-time hour converted to UTC using configured offset.
int UTCHour(datetime t)
{
   MqlDateTime dt; TimeToStruct(t,dt);
   int h = dt.hour - InpBrokerGMTOffset;
   h = ((h % 24) + 24) % 24;
   return h;
}

//====================================================================
//  INIT / DEINIT
//====================================================================
int OnInit()
{
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(30);
   trade.SetTypeFillingBySymbol(_Symbol);

   string sym = _Symbol;
   if(StringFind(sym,"XAU")>=0 || StringFind(sym,"GOLD")>=0)
   {
      g_pipBuffer  = 3.0;
      g_halfSpread = 0.25;
      g_dispMult   = 0.8;   // Gold override
   }
   else if(StringFind(sym,"GBP")>=0)
   {
      g_pipBuffer  = 0.0020;
      g_halfSpread = 0.00010;
      g_dispMult   = InpDisplacementMult;
   }
   else // default EUR/USD-like FX
   {
      g_pipBuffer  = 0.0018;
      g_halfSpread = 0.00008;
      g_dispMult   = InpDisplacementMult;
   }

   for(int i=0;i<MAX_OB;i++) g_ob[i].used=false;

   g_dayStartEquity  = AccountInfoDouble(ACCOUNT_EQUITY);
   g_weekStartEquity = g_dayStartEquity;

   PrintFormat("1BullBear ICT/SMC EA init on %s  pipBuf=%.5f halfSpread=%.5f dispMult=%.2f",
               sym, g_pipBuffer, g_halfSpread, g_dispMult);
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason){}

//====================================================================
//  MAIN TICK  (manage every tick, decide on each new closed H1 bar)
//====================================================================
void OnTick()
{
   ManageOpenTrades();

   datetime curBar = iTime(_Symbol,PERIOD_H1,0);
   if(curBar==g_lastBarTime) return;
   g_lastBarTime = curBar;

   OnNewBar();
}

//====================================================================
//  NEW BAR PIPELINE
//====================================================================
void OnNewBar()
{
   g_barsSinceTrade++;

   UpdateDrawdownGuards();
   RegisterPendingFVG();          // P1 no-lookahead: FVG on next closed bar
   AgeAndExpireOBs();

   ENUM_TREND trend = DetermineTrend();
   DetectOrderBlock(trend);

   if(!g_haltDay && !g_haltWeek)
      CheckRetestEntries(trend);
}

//====================================================================
//  DRAWDOWN GUARDS  (daily / weekly)
//====================================================================
void UpdateDrawdownGuards()
{
   MqlDateTime dt; TimeToStruct(TimeCurrent(),dt);
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);

   if(dt.day_of_year != g_curDay)
   {
      g_curDay = dt.day_of_year;
      g_dayStartEquity = eq;
      g_haltDay = false;
   }
   int weekBucket = dt.year*53 + (dt.day_of_year/7);
   if(weekBucket != g_curWeek)
   {
      g_curWeek = weekBucket;
      g_weekStartEquity = eq;
      g_haltWeek = false;
   }

   if(g_dayStartEquity>0)
   {
      double ddDay = (g_dayStartEquity-eq)/g_dayStartEquity*100.0;
      if(ddDay >= InpMaxDailyDD){ if(!g_haltDay) Log("Daily DD hit -> halt"); g_haltDay=true; }
   }
   if(g_weekStartEquity>0)
   {
      double ddWk = (g_weekStartEquity-eq)/g_weekStartEquity*100.0;
      if(ddWk >= InpMaxWeeklyDD){ if(!g_haltWeek) Log("Weekly DD hit -> halt"); g_haltWeek=true; }
   }
}

//====================================================================
//  SWING STRUCTURE + TREND  (no lookahead: only confirmed swings)
//====================================================================
bool IsSwingHigh(int shift,int cb)
{
   double h = iHigh(_Symbol,PERIOD_H1,shift);
   for(int k=1;k<=cb;k++)
   {
      if(iHigh(_Symbol,PERIOD_H1,shift-k) >= h) return false; // more recent side
      if(iHigh(_Symbol,PERIOD_H1,shift+k) >  h) return false; // older side
   }
   return true;
}
bool IsSwingLow(int shift,int cb)
{
   double l = iLow(_Symbol,PERIOD_H1,shift);
   for(int k=1;k<=cb;k++)
   {
      if(iLow(_Symbol,PERIOD_H1,shift-k) <= l) return false;
      if(iLow(_Symbol,PERIOD_H1,shift+k) <  l) return false;
   }
   return true;
}

// Two most recent confirmed swing highs & lows -> trend.
ENUM_TREND DetermineTrend()
{
   int cb = InpSwingConfirmBars;
   double sh[2]; double sl[2];
   int nH=0, nL=0;
   for(int s=cb+1; s<=InpSwingLookback && (nH<2 || nL<2); s++)
   {
      if(nH<2 && IsSwingHigh(s,cb)){ sh[nH]=iHigh(_Symbol,PERIOD_H1,s); nH++; }
      if(nL<2 && IsSwingLow(s,cb)) { sl[nL]=iLow(_Symbol,PERIOD_H1,s);  nL++; }
   }
   if(nH<2 || nL<2) return TREND_NONE;

   bool hh = sh[0] > sh[1];
   bool hl = sl[0] > sl[1];
   bool lh = sh[0] < sh[1];
   bool ll = sl[0] < sl[1];

   if(hh && hl) return TREND_BULL;
   if(lh && ll) return TREND_BEAR;
   return TREND_NONE;
}

double LastSwingHigh(int startShift)
{
   int cb=InpSwingConfirmBars;
   for(int s=MathMax(cb+1,startShift); s<=InpSwingLookback; s++)
      if(IsSwingHigh(s,cb)) return iHigh(_Symbol,PERIOD_H1,s);
   return 0.0;
}
double LastSwingLow(int startShift)
{
   int cb=InpSwingConfirmBars;
   for(int s=MathMax(cb+1,startShift); s<=InpSwingLookback; s++)
      if(IsSwingLow(s,cb)) return iLow(_Symbol,PERIOD_H1,s);
   return 0.0;
}

//====================================================================
//  ZONE / OTE HELPERS
//====================================================================
double FibPosition(double price,double rngLow,double rngHigh)
{
   if(rngHigh<=rngLow) return 0.5;
   double p = (price-rngLow)/(rngHigh-rngLow);
   if(p<0) p=0;
   if(p>1) p=1;
   return p;
}

double AvgBody(int startShift,int lookback)
{
   double sum=0; int n=0;
   for(int s=startShift; s<startShift+lookback; s++)
   {
      double o=iOpen(_Symbol,PERIOD_H1,s);
      double c=iClose(_Symbol,PERIOD_H1,s);
      sum += MathAbs(c-o); n++;
   }
   return (n>0)? sum/n : 0.0;
}

//====================================================================
//  LIQUIDITY SWEEP
//====================================================================
bool LiquiditySweptBull(int obShift)
{
   double obLow = iLow(_Symbol,PERIOD_H1,obShift);
   for(int s=obShift+1; s<=obShift+InpLiqSweepLookback; s++)
      if(obLow < iLow(_Symbol,PERIOD_H1,s)) return true;
   return false;
}
bool LiquiditySweptBear(int obShift)
{
   double obHigh = iHigh(_Symbol,PERIOD_H1,obShift);
   for(int s=obShift+1; s<=obShift+InpLiqSweepLookback; s++)
      if(obHigh > iHigh(_Symbol,PERIOD_H1,s)) return true;
   return false;
}

//====================================================================
//  ORDER BLOCK DETECTION  (impulse = shift 1, OB candle = shift 2)
//====================================================================
void DetectOrderBlock(ENUM_TREND trend)
{
   if(trend==TREND_NONE) return;

   int impulseShift = 1;
   int obShift      = 2;

   double impO=iOpen(_Symbol,PERIOD_H1,impulseShift);
   double impC=iClose(_Symbol,PERIOD_H1,impulseShift);
   double impBody=MathAbs(impC-impO);

   double avg=AvgBody(impulseShift+1, InpOBLookback);
   if(avg<=0) return;
   if(impBody < avg*g_dispMult) return;   // no displacement

   double obO=iOpen(_Symbol,PERIOD_H1,obShift);
   double obC=iClose(_Symbol,PERIOD_H1,obShift);
   double obHigh=iHigh(_Symbol,PERIOD_H1,obShift);
   double obLow =iLow(_Symbol,PERIOD_H1,obShift);

   double sh=LastSwingHigh(obShift);
   double sl=LastSwingLow(obShift);
   if(sh<=0 || sl<=0 || sh<=sl) return;

   if(trend==TREND_BULL)
   {
      if(!(impC>impO)) return;            // impulse must be bullish
      if(!(obC<obO))   return;            // OB candle must be bearish (opposing)
      if(!(impC>obHigh)) return;          // engulfing close beyond OB high

      double obMid=(obHigh+obLow)/2.0;
      double fib=FibPosition(obMid,sl,sh);
      if(fib > InpDiscountMax) return;    // must be in discount

      int score=2;
      double fibDisc = 1.0-fib;           // OTE measured from discount side
      if(fibDisc>=InpOTE_Lower && fibDisc<=InpOTE_Upper) score+=1;
      if(LiquiditySweptBull(obShift)) score+=1;

      StoreOB(true,obShift,obHigh,obLow,obMid,score);
   }
   else // TREND_BEAR
   {
      if(!(impC<impO)) return;
      if(!(obC>obO))   return;
      if(!(impC<obLow)) return;

      double obMid=(obHigh+obLow)/2.0;
      double fib=FibPosition(obMid,sl,sh);
      if(fib < InpPremiumMin) return;     // must be in premium

      int score=2;
      if(fib>=InpOTE_Lower && fib<=InpOTE_Upper) score+=1;
      if(LiquiditySweptBear(obShift)) score+=1;

      StoreOB(false,obShift,obHigh,obLow,obMid,score);
   }
}

void StoreOB(bool isBull,int obShift,double obHigh,double obLow,double obMid,int score)
{
   datetime ct=iTime(_Symbol,PERIOD_H1,obShift);
   for(int i=0;i<MAX_OB;i++)
      if(g_ob[i].used && g_ob[i].createTime==ct) return;   // dedupe

   for(int i=0;i<MAX_OB;i++)
   {
      if(!g_ob[i].used)
      {
         g_ob[i].used       = true;
         g_ob[i].registered = false;     // FVG deferred to next bar
         g_ob[i].isBull     = isBull;
         g_ob[i].createTime = ct;
         g_ob[i].obHigh     = obHigh;
         g_ob[i].obLow      = obLow;
         g_ob[i].obMid      = obMid;
         g_ob[i].score      = score;
         g_ob[i].fvgOK      = false;
         g_ob[i].ageBars    = 0;
         Log(StringFormat("New OB %s @ %s score=%d mid=%.5f",
             (isBull?"BULL":"BEAR"),TimeToString(ct),score,obMid));
         return;
      }
   }
}

//====================================================================
//  FVG REGISTRATION  (P1 no-lookahead)
//====================================================================
void RegisterPendingFVG()
{
   for(int i=0;i<MAX_OB;i++)
   {
      if(!g_ob[i].used || g_ob[i].registered) continue;

      bool fvg = HasFVG(g_ob[i].isBull);
      g_ob[i].fvgOK = fvg;
      if(fvg) g_ob[i].score += 1;

      if(InpRequireFVG && !fvg)
      {
         g_ob[i].used=false;             // discard: FVG required
         Log("OB discarded: no FVG confluence");
         continue;
      }
      g_ob[i].registered = true;
   }
}

// 3-candle FVG on most recent closed bars (shift 1..3).
bool HasFVG(bool isBull)
{
   double h1=iHigh(_Symbol,PERIOD_H1,1);
   double l1=iLow (_Symbol,PERIOD_H1,1);
   double h3=iHigh(_Symbol,PERIOD_H1,3);
   double l3=iLow (_Symbol,PERIOD_H1,3);
   if(isBull) return (l1 > h3);          // gap up
   else       return (h1 < l3);          // gap down
}

//====================================================================
//  AGE / EXPIRE / INVALIDATE ORDER BLOCKS
//====================================================================
void AgeAndExpireOBs()
{
   double c1=iClose(_Symbol,PERIOD_H1,1);
   for(int i=0;i<MAX_OB;i++)
   {
      if(!g_ob[i].used) continue;
      g_ob[i].ageBars++;
      if(g_ob[i].ageBars > InpOBExpiry){ g_ob[i].used=false; continue; }
      if(g_ob[i].isBull  && c1 < g_ob[i].obLow ){ g_ob[i].used=false; }
      if(!g_ob[i].isBull && c1 > g_ob[i].obHigh){ g_ob[i].used=false; }
   }
}

//====================================================================
//  DOL  (Draw on Liquidity) -> TP2 target
//====================================================================
double FindDOL(bool isBull,double refPrice)
{
   int cb=InpSwingConfirmBars;
   double best=0.0;
   double bestDist=DBL_MAX;
   if(isBull)
   {
      for(int s=cb+1; s<=InpDOLLookback; s++)
         if(IsSwingHigh(s,cb))
         {
            double h=iHigh(_Symbol,PERIOD_H1,s);
            if(h>refPrice && (h-refPrice)<bestDist){ bestDist=h-refPrice; best=h; }
         }
   }
   else
   {
      for(int s=cb+1; s<=InpDOLLookback; s++)
         if(IsSwingLow(s,cb))
         {
            double l=iLow(_Symbol,PERIOD_H1,s);
            if(l<refPrice && (refPrice-l)<bestDist){ bestDist=refPrice-l; best=l; }
         }
   }
   return best;
}

//====================================================================
//  KILLZONE FILTER
//====================================================================
bool InKillzone()
{
   if(!InpUseKillzoneFilter) return true;
   int h=UTCHour(TimeCurrent());
   if(h>=InpLondonStart && h<InpLondonEnd) return true;
   if(h>=InpNYAMStart   && h<InpNYAMEnd)   return true;
   if(h>=InpNYPMBegin   && h<InpNYPMEnd)   return true;
   return false;
}

//====================================================================
//  COUNT OPEN POSITIONS FOR THIS EA
//====================================================================
int CountOpen()
{
   int n=0;
   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      ulong tk=PositionGetTicket(i);
      if(tk==0) continue;
      if(PositionGetInteger(POSITION_MAGIC)==InpMagic &&
         PositionGetString(POSITION_SYMBOL)==_Symbol) n++;
   }
   return n;
}

//====================================================================
//  RETEST ENTRIES
//====================================================================
void CheckRetestEntries(ENUM_TREND trend)
{
   if(!InKillzone()) return;
   if(CountOpen() >= InpMaxOpenTrades) return;
   if(g_barsSinceTrade < InpMinBarsBetweenTrades) return;

   for(int i=0;i<MAX_OB;i++)
   {
      if(!g_ob[i].used || !g_ob[i].registered) continue;
      if(g_ob[i].score < InpMinConfluence) continue;
      if(g_ob[i].isBull  && trend!=TREND_BULL) continue;
      if(!g_ob[i].isBull && trend!=TREND_BEAR) continue;

      double o1=iOpen (_Symbol,PERIOD_H1,1);
      double c1=iClose(_Symbol,PERIOD_H1,1);
      double h1=iHigh (_Symbol,PERIOD_H1,1);
      double l1=iLow  (_Symbol,PERIOD_H1,1);

      if(g_ob[i].isBull)
      {
         bool tapped = (l1 <= g_ob[i].obHigh);
         bool confirm= (c1 > o1) && (c1 > g_ob[i].obLow);
         if(tapped && confirm && OpenTrade(true,i)){ g_ob[i].used=false; return; }
      }
      else
      {
         bool tapped = (h1 >= g_ob[i].obLow);
         bool confirm= (c1 < o1) && (c1 < g_ob[i].obHigh);
         if(tapped && confirm && OpenTrade(false,i)){ g_ob[i].used=false; return; }
      }
   }
}

//====================================================================
//  OPEN TRADE  (entry / SL / TP with both-side spread, 50/50 split)
//====================================================================
bool OpenTrade(bool isBull,int obIdx)
{
   double hs  = g_halfSpread;
   double buf = g_pipBuffer;
   double obMid = g_ob[obIdx].obMid;
   double obHigh= g_ob[obIdx].obHigh;
   double obLow = g_ob[obIdx].obLow;

   double entry,slChart,slFill,risk,tp1Chart,tp2Chart;

   if(isBull)
   {
      entry   = obMid + hs;              // buy at ask
      slChart = obLow - buf;
      slFill  = slChart - hs;            // sell at bid if stopped
      risk    = entry - slFill;
      if(risk<=0) return false;
      tp1Chart= entry + risk + hs;       // 1:1 RR
      double dol = FindDOL(true, entry);
      tp2Chart = (dol>entry)? dol : tp1Chart + risk;   // fallback ~2R
   }
   else
   {
      entry   = obMid - hs;              // sell at bid
      slChart = obHigh + buf;
      slFill  = slChart + hs;            // buy at ask if stopped
      risk    = slFill - entry;
      if(risk<=0) return false;
      tp1Chart= entry - risk - hs;
      double dol = FindDOL(false, entry);
      tp2Chart = (dol>0 && dol<entry)? dol : tp1Chart - risk;
   }

   double rr = MathAbs(tp2Chart-entry)/risk;
   if(rr < InpMinRR) return false;

   double lots = CalcLots(risk);
   if(lots<=0) return false;

   double lotStep = SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_STEP);
   double lotMin  = SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN);
   double halfLot = MathFloor((lots*InpPartialClosePct/100.0)/lotStep)*lotStep;
   if(halfLot<lotMin) halfLot=lotMin;
   double restLot = lots - halfLot;
   if(restLot<lotMin) restLot=0;

   int dg=SymDigits();
   slChart = NormalizeDouble(slChart,dg);
   tp1Chart= NormalizeDouble(tp1Chart,dg);
   tp2Chart= NormalizeDouble(tp2Chart,dg);

   ENUM_ORDER_TYPE ot = isBull? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   double px = isBull? SymbolInfoDouble(_Symbol,SYMBOL_ASK)
                     : SymbolInfoDouble(_Symbol,SYMBOL_BID);

   bool ok=false;
   if(halfLot>0 && trade.PositionOpen(_Symbol,ot,halfLot,px,slChart,tp1Chart,"1BB-TP1"))
      ok=true;
   if(restLot>0 && trade.PositionOpen(_Symbol,ot,restLot,px,slChart,tp2Chart,"1BB-TP2"))
      ok=true;

   if(ok)
   {
      g_barsSinceTrade=0;
      Log(StringFormat("OPEN %s px~%.5f SL %.5f TP1 %.5f TP2 %.5f RR %.2f lots %.2f",
          (isBull?"BUY":"SELL"),px,slChart,tp1Chart,tp2Chart,rr,lots));
   }
   return ok;
}

//--- lots so that price risk == RiskPercent of equity
double CalcLots(double riskPriceDist)
{
   double equity=AccountInfoDouble(ACCOUNT_EQUITY);
   double riskMoney=equity*InpRiskPercent/100.0;

   double tickVal=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_VALUE);
   double tickSz =SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE);
   if(tickSz<=0 || tickVal<=0) return 0;

   double lossPerLot=(riskPriceDist/tickSz)*tickVal;
   if(lossPerLot<=0) return 0;

   double lots=riskMoney/lossPerLot;

   double lotStep=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_STEP);
   double lotMin =SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN);
   double lotMax =SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MAX);
   lots=MathFloor(lots/lotStep)*lotStep;
   if(lots<lotMin) lots=lotMin;
   if(lots>lotMax) lots=lotMax;
   return lots;
}

//====================================================================
//  MANAGE OPEN TRADES  (move runner to BE once TP1 leg gone; time stop)
//====================================================================
void ManageOpenTrades()
{
   bool tp1LegAlive=false, tp2LegAlive=false;
   ulong tp2Ticket=0; double tp2Entry=0; bool tp2IsBull=false;

   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      ulong tk=PositionGetTicket(i);
      if(tk==0) continue;
      if(PositionGetInteger(POSITION_MAGIC)!=InpMagic) continue;
      if(PositionGetString(POSITION_SYMBOL)!=_Symbol)  continue;

      string cmt=PositionGetString(POSITION_COMMENT);
      if(StringFind(cmt,"TP1")>=0) tp1LegAlive=true;
      if(StringFind(cmt,"TP2")>=0)
      {
         tp2LegAlive=true;
         tp2Ticket=tk;
         tp2Entry =PositionGetDouble(POSITION_PRICE_OPEN);
         tp2IsBull=(PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY);
      }

      datetime opened=(datetime)PositionGetInteger(POSITION_TIME);
      int barsHeld=(int)((TimeCurrent()-opened)/PeriodSeconds(PERIOD_H1));
      if(barsHeld>=InpMaxBarsHeld)
      {
         trade.PositionClose(tk);
         Log("Time stop close ticket "+(string)tk);
      }
   }

   if(!tp1LegAlive && tp2LegAlive && InpMoveSLtoBE && tp2Ticket>0)
   {
      double be = tp2IsBull ? tp2Entry + g_halfSpread : tp2Entry - g_halfSpread;
      be=NormalizeDouble(be,SymDigits());
      double curSL=0, curTP=0;
      if(posinfo.SelectByTicket(tp2Ticket)){ curSL=posinfo.StopLoss(); curTP=posinfo.TakeProfit(); }
      bool need = tp2IsBull ? (curSL < be-_Point) : (curSL==0 || curSL > be+_Point);
      if(need && trade.PositionModify(tp2Ticket,be,curTP))
         Log("Runner SL -> BE @ "+DoubleToString(be,SymDigits()));
   }
}
//+------------------------------------------------------------------+
