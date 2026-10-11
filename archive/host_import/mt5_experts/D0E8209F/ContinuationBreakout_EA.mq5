//+------------------------------------------------------------------+
//|                                     ContinuationBreakout_EA.mq5  |
//|                                      Trend Continuation Strategy |
//+------------------------------------------------------------------+
#property copyright "Automated Trading"
#property link      ""
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>
#include <Trade\SymbolInfo.mqh>
#include <Trade\PositionInfo.mqh>

//--- Input Parameters
input group "=== Strategy Parameters ==="
input bool     InpEnableLongs       = true;     // Enable Longs
input bool     InpEnableShorts      = true;     // Enable Shorts
input double   InpMinRR             = 1.0;      // Minimum Reward-to-Risk Ratio
input double   InpMinSLPips         = 3.0;      // Minimum Stop Loss (Pips)
input double   InpMaxSLPips         = 30.0;     // Maximum Stop Loss (Pips)
input double   InpPipBuffer         = 1.0;      // SL Buffer Beyond Swing Extremes (Pips)

input group "=== Risk Management ==="
input double   InpRiskPercent       = 1.0;      // Risk Per Trade (% of Account Balance)
input ulong    InpMagicNumber       = 102233;   // Magic Number
input int      InpSlippage          = 10;       // Slippage in Points

//--- Global Variables
CTrade         m_trade;
CSymbolInfo    m_symbol;
CPositionInfo  m_position;

datetime       g_last_bar_time      = 0;
double         g_lowest_close       = 0.0;
bool           g_bear_pullback      = false;
double         g_bear_swing_high    = -1.0;

double         g_highest_close      = 0.0;
bool           g_bull_pullback      = false;
double         g_bull_swing_low     = 999999.0;

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   if(!m_symbol.Name(_Symbol))
   {
      Print("Error initializing symbol info for ", _Symbol);
      return INIT_FAILED;
   }
   
   m_symbol.Refresh();
   m_trade.SetExpertMagicNumber(InpMagicNumber);
   m_trade.SetDeviationInPoints(InpSlippage);
   m_trade.SetTypeFillingBySymbol(_Symbol);

   Print("EA initialized successfully for ", _Symbol, " on timeframe ", EnumToString(_Period));
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Check if an active position exists for this symbol & magic       |
//+------------------------------------------------------------------+
bool HasOpenPosition()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(m_position.SelectByIndex(i))
      {
         if(m_position.Symbol() == _Symbol && m_position.Magic() == InpMagicNumber)
            return true;
      }
   }
   return false;
}

//+------------------------------------------------------------------+
//| Calculate Lot Size based on % Risk and Stop Distance             |
//+------------------------------------------------------------------+
double CalculateLotSize(double sl_distance_price)
{
   if(sl_distance_price <= 0) return 0.0;
   
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double risk_amount = balance * (InpRiskPercent / 100.0);
   
   double tick_size = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double tick_value = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   
   if(tick_size <= 0 || tick_value <= 0) return SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   
   double ticks_at_risk = sl_distance_price / tick_size;
   double money_loss_per_lot = ticks_at_risk * tick_value;
   
   if(money_loss_per_lot <= 0) return SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   
   double lot_size = risk_amount / money_loss_per_lot;
   
   double lot_step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double min_lot  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double max_lot  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   
   lot_size = MathFloor(lot_size / lot_step) * lot_step;
   lot_size = MathMax(min_lot, MathMin(max_lot, lot_size));
   
   return NormalizeDouble(lot_size, 2);
}

//+------------------------------------------------------------------+
//| Expert tick function                                             |
//+------------------------------------------------------------------+
void OnTick()
{
   // Check for New Bar formation
   datetime current_bar_time = iTime(_Symbol, _Period, 0);
   if(current_bar_time == g_last_bar_time) return;
   
   // Ensure bar 1 is fully formed
   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   if(CopyRates(_Symbol, _Period, 1, 2, rates) < 2) return;
   
   g_last_bar_time = current_bar_time;
   m_symbol.Refresh();

   double pip = (_Digits == 3 || _Digits == 5) ? (_Point * 10) : _Point;
   double pip_buffer = InpPipBuffer * pip;

   MqlRates bar1 = rates[0]; // Bar 1 (most recently closed)
   MqlRates bar2 = rates[1]; // Bar 2 (prior closed)

   bool in_position = HasOpenPosition();

   // If a position just closed externally (TP/SL hit), reset structural benchmarks
   static bool was_in_position = false;
   if(was_in_position && !in_position)
   {
      g_lowest_close = 0.0;
      g_bear_pullback = false;
      g_highest_close = 0.0;
      g_bull_pullback = false;
   }
   was_in_position = in_position;

   if(in_position) return;

   // ==================== BEARISH SETUP (SHORTS) ====================
   if(InpEnableShorts)
   {
      if(g_lowest_close == 0.0 || bar1.close < g_lowest_close)
      {
         g_lowest_close = bar1.close;
         g_bear_pullback = false;
         g_bear_swing_high = -1.0;
      }
      else if(bar1.close > bar1.open)
      {
         g_bear_pullback = true;
         g_bear_swing_high = MathMax(g_bear_swing_high, bar1.high);
      }
      else if(g_bear_pullback && bar1.close < bar1.open && bar1.close < bar2.close && bar1.low < bar2.low)
      {
         double entry_price = m_symbol.Bid();
         double sl_price = NormalizeDouble(g_bear_swing_high + pip_buffer, _Digits);
         double tp_price = NormalizeDouble(g_lowest_close, _Digits);

         double risk = sl_price - entry_price;
         double reward = entry_price - tp_price;
         double risk_pips = risk / pip;

         if(risk > 0 && reward > 0 && risk_pips >= InpMinSLPips && risk_pips <= InpMaxSLPips)
         {
            double rr = reward / risk;
            if(rr >= InpMinRR)
            {
               double volume = CalculateLotSize(risk);
               if(m_trade.Sell(volume, _Symbol, entry_price, sl_price, tp_price, "Trend Short"))
               {
                  Print("SHORT order opened: Vol=", volume, " SL=", sl_price, " TP=", tp_price, " RR=", DoubleToString(rr, 2));
                  g_bear_pullback = false;
                  g_bear_swing_high = -1.0;
                  return;
               }
            }
         }
         g_bear_pullback = false;
         g_bear_swing_high = -1.0;
      }
   }

   // ==================== BULLISH SETUP (LONGS) ====================
   if(InpEnableLongs && !HasOpenPosition())
   {
      if(g_highest_close == 0.0 || bar1.close > g_highest_close)
      {
         g_highest_close = bar1.close;
         g_bull_pullback = false;
         g_bull_swing_low = 999999.0;
      }
      else if(bar1.close < bar1.open)
      {
         g_bull_pullback = true;
         g_bull_swing_low = MathMin(g_bull_swing_low, bar1.low);
      }
      else if(g_bull_pullback && bar1.close > bar1.open && bar1.close > bar2.close && bar1.high > bar2.high)
      {
         double entry_price = m_symbol.Ask();
         double sl_price = NormalizeDouble(g_bull_swing_low - pip_buffer, _Digits);
         double tp_price = NormalizeDouble(g_highest_close, _Digits);

         double risk = entry_price - sl_price;
         double reward = tp_price - entry_price;
         double risk_pips = risk / pip;

         if(risk > 0 && reward > 0 && risk_pips >= InpMinSLPips && risk_pips <= InpMaxSLPips)
         {
            double rr = reward / risk;
            if(rr >= InpMinRR)
            {
               double volume = CalculateLotSize(risk);
               if(m_trade.Buy(volume, _Symbol, entry_price, sl_price, tp_price, "Trend Long"))
               {
                  Print("LONG order opened: Vol=", volume, " SL=", sl_price, " TP=", tp_price, " RR=", DoubleToString(rr, 2));
                  g_bull_pullback = false;
                  g_bull_swing_low = 999999.0;
                  return;
               }
            }
         }
         g_bull_pullback = false;
         g_bull_swing_low = 999999.0;
      }
   }
}
