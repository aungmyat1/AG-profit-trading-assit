//+------------------------------------------------------------------+
//|                                  ContinuationBreakout_EA.mq5     |
//|                         Trend Continuation Strategy (MT5/MQL5)   |
//+------------------------------------------------------------------+
#property copyright "Automated Trading"
#property link      ""
#property version   "1.20"
#property strict

#include <Trade/Trade.mqh>
#include <Trade/SymbolInfo.mqh>
#include <Trade/PositionInfo.mqh>

input group "=== Runtime Safety ==="
input bool     InpEnableTrading      = false;   // Master execution switch
input bool     InpDemoOnly           = true;    // Reject non-demo accounts
input double   InpMaxSpreadPips      = 2.0;     // Maximum entry spread (pips)

input group "=== Strategy Parameters ==="
input bool     InpEnableLongs        = true;    // Enable long setups
input bool     InpEnableShorts       = true;    // Enable short setups
input double   InpMinRR              = 1.0;     // Minimum reward-to-risk ratio
input double   InpMinSLPips          = 3.0;     // Minimum stop distance (pips)
input double   InpMaxSLPips          = 30.0;    // Maximum stop distance (pips)
input double   InpPipBuffer          = 1.0;     // Buffer beyond pullback extreme

input group "=== Risk Management ==="
input double   InpRiskPercent        = 0.5;     // Risk per trade (% of equity)
input double   InpMaxDailyLossPct     = 2.0;     // Block after realized daily loss (%)
input double   InpMaxDrawdownPct      = 15.0;    // Block at equity high-water drawdown (%)
input ulong    InpMagicNumber        = 102233;  // Strategy magic number
input int      InpSlippage           = 10;      // Maximum deviation (points)

CTrade         g_trade;
CSymbolInfo    g_symbol;
CPositionInfo  g_position;

datetime g_last_bar_time   = 0;
double   g_lowest_close    = 0.0;
bool     g_bear_pullback   = false;
double   g_bear_swing_high = 0.0;
double   g_highest_close   = 0.0;
bool     g_bull_pullback   = false;
double   g_bull_swing_low  = 0.0;
string   g_equity_peak_key = "";

//+------------------------------------------------------------------+
double PipSize()
{
   return ((_Digits == 3 || _Digits == 5) ? _Point * 10.0 : _Point);
}

//+------------------------------------------------------------------+
int VolumeDigits(const double step)
{
   int digits = 0;
   double scaled = step;
   while(digits < 8 && MathAbs(scaled - MathRound(scaled)) > 1e-8)
   {
      scaled *= 10.0;
      digits++;
   }
   return digits;
}

//+------------------------------------------------------------------+
void ResetBearState()
{
   g_bear_pullback   = false;
   g_bear_swing_high = 0.0;
}

//+------------------------------------------------------------------+
void ResetBullState()
{
   g_bull_pullback  = false;
   g_bull_swing_low = 0.0;
}

//+------------------------------------------------------------------+
void ResetStructure()
{
   g_lowest_close  = 0.0;
   g_highest_close = 0.0;
   ResetBearState();
   ResetBullState();
}

//+------------------------------------------------------------------+
string EquityPeakKey()
{
   return StringFormat("CB_EQUITY_PEAK_%I64d_%I64d",
                       (long)AccountInfoInteger(ACCOUNT_LOGIN),
                       (long)InpMagicNumber);
}

//+------------------------------------------------------------------+
double RealizedTradingPnLToday()
{
   MqlDateTime parts;
   TimeToStruct(TimeTradeServer(), parts);
   parts.hour = 0;
   parts.min  = 0;
   parts.sec  = 0;
   const datetime day_start = StructToTime(parts);

   if(!HistorySelect(day_start, TimeTradeServer()))
      return 0.0;

   double pnl = 0.0;
   const int total = HistoryDealsTotal();
   for(int i = 0; i < total; i++)
   {
      const ulong ticket = HistoryDealGetTicket(i);
      if(ticket == 0)
         continue;

      const ENUM_DEAL_TYPE deal_type = (ENUM_DEAL_TYPE)HistoryDealGetInteger(ticket, DEAL_TYPE);
      if(deal_type != DEAL_TYPE_BUY && deal_type != DEAL_TYPE_SELL)
         continue;

      pnl += HistoryDealGetDouble(ticket, DEAL_PROFIT);
      pnl += HistoryDealGetDouble(ticket, DEAL_COMMISSION);
      pnl += HistoryDealGetDouble(ticket, DEAL_SWAP);
      pnl += HistoryDealGetDouble(ticket, DEAL_FEE);
   }
   return pnl;
}

//+------------------------------------------------------------------+
bool AccountRiskLimitsAllowEntry()
{
   const double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   const double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   if(equity <= 0.0 || balance <= 0.0)
      return false;

   double peak = equity;
   if(GlobalVariableCheck(g_equity_peak_key))
      peak = MathMax(GlobalVariableGet(g_equity_peak_key), equity);

   if(!GlobalVariableSet(g_equity_peak_key, peak))
   {
      Print("Signal blocked: unable to persist equity high-water mark.");
      return false;
   }

   const double drawdown_pct = 100.0 * (peak - equity) / peak;
   if(drawdown_pct + 1e-8 >= InpMaxDrawdownPct)
   {
      Print("Signal blocked: equity drawdown ", DoubleToString(drawdown_pct, 2),
            "% reached limit ", DoubleToString(InpMaxDrawdownPct, 2), "%.");
      return false;
   }

   const double daily_pnl = RealizedTradingPnLToday();
   const double estimated_start_balance = balance - daily_pnl;
   if(estimated_start_balance <= 0.0)
      return false;

   const double daily_loss_pct = (daily_pnl < 0.0)
                                 ? (-daily_pnl / estimated_start_balance) * 100.0
                                 : 0.0;
   if(daily_loss_pct + 1e-8 >= InpMaxDailyLossPct)
   {
      Print("Signal blocked: realized daily loss ", DoubleToString(daily_loss_pct, 2),
            "% reached limit ", DoubleToString(InpMaxDailyLossPct, 2), "%.");
      return false;
   }
   return true;
}

//+------------------------------------------------------------------+
int OnInit()
{
   if(InpRiskPercent <= 0.0 || InpRiskPercent > 2.0 ||
      InpMaxDailyLossPct <= 0.0 || InpMaxDailyLossPct > 10.0 ||
      InpMaxDrawdownPct <= 0.0 || InpMaxDrawdownPct > 50.0 ||
      InpMinRR <= 0.0 || InpMinSLPips <= 0.0 ||
      InpMaxSLPips < InpMinSLPips || InpMaxSpreadPips <= 0.0)
   {
      Print("Invalid EA inputs. Risk must be > 0 and <= 2%; check RR, SL and spread limits.");
      return INIT_PARAMETERS_INCORRECT;
   }

   if(!g_symbol.Name(_Symbol))
   {
      Print("Unable to initialize symbol information for ", _Symbol);
      return INIT_FAILED;
   }

   g_symbol.Refresh();
   g_symbol.RefreshRates();
   g_equity_peak_key = EquityPeakKey();
   if(MQLInfoInteger(MQL_TESTER) || !GlobalVariableCheck(g_equity_peak_key))
      GlobalVariableSet(g_equity_peak_key, AccountInfoDouble(ACCOUNT_EQUITY));
   g_trade.SetExpertMagicNumber(InpMagicNumber);
   g_trade.SetDeviationInPoints(InpSlippage);
   g_trade.SetTypeFillingBySymbol(_Symbol);
   g_trade.SetAsyncMode(false);

   Print("ContinuationBreakout EA initialized for ", _Symbol,
         " on ", EnumToString(_Period),
         ". Execution=", (InpEnableTrading ? "ENABLED" : "DISABLED"),
         ", DemoOnly=", (InpDemoOnly ? "true" : "false"));
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
bool HasOpenPosition()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(g_position.SelectByIndex(i) &&
         g_position.Symbol() == _Symbol &&
         g_position.Magic() == InpMagicNumber)
         return true;
   }
   return false;
}

//+------------------------------------------------------------------+
bool RuntimeAuthorized()
{
   if(!InpEnableTrading)
   {
      Print("Signal blocked: InpEnableTrading=false.");
      return false;
   }

   if(InpDemoOnly && !MQLInfoInteger(MQL_TESTER) &&
      AccountInfoInteger(ACCOUNT_TRADE_MODE) != ACCOUNT_TRADE_MODE_DEMO)
   {
      Print("Signal blocked: EA is configured for demo accounts only.");
      return false;
   }

   if(!TerminalInfoInteger(TERMINAL_CONNECTED) ||
      !TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) ||
      !MQLInfoInteger(MQL_TRADE_ALLOWED) ||
      !AccountInfoInteger(ACCOUNT_TRADE_ALLOWED) ||
      !AccountInfoInteger(ACCOUNT_TRADE_EXPERT))
   {
      Print("Signal blocked: terminal/account algorithmic trading is unavailable.");
      return false;
   }
   return AccountRiskLimitsAllowEntry();
}

//+------------------------------------------------------------------+
bool SpreadIsAcceptable()
{
   if(!g_symbol.RefreshRates())
      return false;

   const double spread_pips = (g_symbol.Ask() - g_symbol.Bid()) / PipSize();
   if(spread_pips > InpMaxSpreadPips)
   {
      Print("Signal blocked: spread ", DoubleToString(spread_pips, 2),
            " pips exceeds limit ", DoubleToString(InpMaxSpreadPips, 2), ".");
      return false;
   }
   return true;
}

//+------------------------------------------------------------------+
bool PricesAreValid(const ENUM_ORDER_TYPE order_type,
                    const double entry,
                    const double sl,
                    const double tp)
{
   if(entry <= 0.0 || sl <= 0.0 || tp <= 0.0)
      return false;

   if(order_type == ORDER_TYPE_BUY && !(sl < entry && tp > entry))
      return false;
   if(order_type == ORDER_TYPE_SELL && !(sl > entry && tp < entry))
      return false;

   const long stops_level_points = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
   const double minimum_distance = (double)stops_level_points * _Point;
   if(MathAbs(entry - sl) + 1e-12 < minimum_distance ||
      MathAbs(tp - entry) + 1e-12 < minimum_distance)
   {
      Print("Signal blocked: SL or TP violates broker minimum stop distance.");
      return false;
   }
   return true;
}

//+------------------------------------------------------------------+
double CalculateLotSize(const ENUM_ORDER_TYPE order_type,
                        const double entry,
                        const double sl)
{
   const double equity      = AccountInfoDouble(ACCOUNT_EQUITY);
   const double risk_amount = equity * InpRiskPercent / 100.0;
   if(equity <= 0.0 || risk_amount <= 0.0)
      return 0.0;

   double one_lot_profit = 0.0;
   if(!OrderCalcProfit(order_type, _Symbol, 1.0, entry, sl, one_lot_profit))
   {
      Print("Lot calculation failed. OrderCalcProfit error=", GetLastError());
      return 0.0;
   }

   const double loss_per_lot = MathAbs(one_lot_profit);
   if(loss_per_lot <= 0.0)
      return 0.0;

   const double min_lot  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   const double max_lot  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   const double lot_step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   if(min_lot <= 0.0 || max_lot <= 0.0 || lot_step <= 0.0)
      return 0.0;

   double volume = MathFloor((risk_amount / loss_per_lot) / lot_step + 1e-10) * lot_step;
   volume = MathMin(volume, max_lot);

   // Never force the minimum volume if it would exceed the risk budget.
   if(volume + 1e-12 < min_lot)
   {
      Print("Signal blocked: broker minimum lot would exceed risk budget.");
      return 0.0;
   }

   return NormalizeDouble(volume, VolumeDigits(lot_step));
}

//+------------------------------------------------------------------+
bool MarginIsSufficient(const ENUM_ORDER_TYPE order_type,
                        const double volume,
                        const double entry)
{
   double margin_required = 0.0;
   if(!OrderCalcMargin(order_type, _Symbol, volume, entry, margin_required))
   {
      Print("Margin calculation failed. Error=", GetLastError());
      return false;
   }

   if(margin_required > AccountInfoDouble(ACCOUNT_MARGIN_FREE))
   {
      Print("Signal blocked: insufficient free margin.");
      return false;
   }
   return true;
}

//+------------------------------------------------------------------+
bool SubmitMarketOrder(const ENUM_ORDER_TYPE order_type,
                       const double sl,
                       const double tp,
                       const string comment)
{
   if(!RuntimeAuthorized() || HasOpenPosition() || !SpreadIsAcceptable())
      return false;

   const double entry = (order_type == ORDER_TYPE_BUY ? g_symbol.Ask() : g_symbol.Bid());
   if(!PricesAreValid(order_type, entry, sl, tp))
   {
      Print("Signal blocked: invalid entry/SL/TP geometry.");
      return false;
   }

   const double volume = CalculateLotSize(order_type, entry, sl);
   if(volume <= 0.0 || !MarginIsSufficient(order_type, volume, entry))
      return false;

   ResetLastError();
   bool submitted = false;
   // A zero market price lets MT5 use the current broker price.
   if(order_type == ORDER_TYPE_BUY)
      submitted = g_trade.Buy(volume, _Symbol, 0.0, sl, tp, comment);
   else
      submitted = g_trade.Sell(volume, _Symbol, 0.0, sl, tp, comment);

   const uint retcode = g_trade.ResultRetcode();
   if(!submitted || (retcode != TRADE_RETCODE_DONE &&
                     retcode != TRADE_RETCODE_DONE_PARTIAL &&
                     retcode != TRADE_RETCODE_PLACED))
   {
      Print("Order rejected/unknown. retcode=", retcode,
            " description=", g_trade.ResultRetcodeDescription(),
            " last_error=", GetLastError());
      return false;
   }

   Print(comment, " accepted: order=", g_trade.ResultOrder(),
         " deal=", g_trade.ResultDeal(),
         " volume=", DoubleToString(volume, VolumeDigits(SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP))),
         " broker_price=", DoubleToString(g_trade.ResultPrice(), _Digits),
         " SL=", DoubleToString(sl, _Digits),
         " TP=", DoubleToString(tp, _Digits),
         " retcode=", retcode);
   return true;
}

//+------------------------------------------------------------------+
void OnTick()
{
   const datetime current_bar_time = iTime(_Symbol, _Period, 0);
   if(current_bar_time <= 0 || current_bar_time == g_last_bar_time)
      return;

   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   if(CopyRates(_Symbol, _Period, 1, 2, rates) != 2)
      return;

   g_last_bar_time = current_bar_time;
   if(!g_symbol.Refresh() || !g_symbol.RefreshRates())
      return;

   const MqlRates bar1 = rates[0]; // Most recently closed bar
   const MqlRates bar2 = rates[1]; // Previous closed bar
   const double pip_buffer = InpPipBuffer * PipSize();
   const bool in_position = HasOpenPosition();

   static bool was_in_position = false;
   if(was_in_position && !in_position)
      ResetStructure();
   was_in_position = in_position;

   if(in_position)
      return;

   // Bearish continuation: new low -> bullish pullback -> bearish break candle.
   if(InpEnableShorts)
   {
      if(g_lowest_close == 0.0 || bar1.close < g_lowest_close)
      {
         g_lowest_close = bar1.close;
         ResetBearState();
      }
      else if(bar1.close > bar1.open)
      {
         g_bear_pullback = true;
         if(g_bear_swing_high == 0.0)
            g_bear_swing_high = bar1.high;
         else
            g_bear_swing_high = MathMax(g_bear_swing_high, bar1.high);
      }
      else if(g_bear_pullback && bar1.close < bar1.open &&
              bar1.close < bar2.close && bar1.low < bar2.low)
      {
         const double entry = g_symbol.Bid();
         const double sl = NormalizeDouble(g_bear_swing_high + pip_buffer, _Digits);
         const double tp = NormalizeDouble(g_lowest_close, _Digits);
         const double risk = sl - entry;
         const double reward = entry - tp;
         const double risk_pips = risk / PipSize();

         if(risk > 0.0 && reward > 0.0 &&
            risk_pips >= InpMinSLPips && risk_pips <= InpMaxSLPips &&
            reward / risk >= InpMinRR)
         {
            if(SubmitMarketOrder(ORDER_TYPE_SELL, sl, tp, "CB Trend Short"))
            {
               ResetBearState();
               return;
            }
         }
         ResetBearState();
      }
   }

   // Bullish continuation: new high -> bearish pullback -> bullish break candle.
   if(InpEnableLongs && !HasOpenPosition())
   {
      if(g_highest_close == 0.0 || bar1.close > g_highest_close)
      {
         g_highest_close = bar1.close;
         ResetBullState();
      }
      else if(bar1.close < bar1.open)
      {
         g_bull_pullback = true;
         if(g_bull_swing_low == 0.0)
            g_bull_swing_low = bar1.low;
         else
            g_bull_swing_low = MathMin(g_bull_swing_low, bar1.low);
      }
      else if(g_bull_pullback && bar1.close > bar1.open &&
              bar1.close > bar2.close && bar1.high > bar2.high)
      {
         const double entry = g_symbol.Ask();
         const double sl = NormalizeDouble(g_bull_swing_low - pip_buffer, _Digits);
         const double tp = NormalizeDouble(g_highest_close, _Digits);
         const double risk = entry - sl;
         const double reward = tp - entry;
         const double risk_pips = risk / PipSize();

         if(risk > 0.0 && reward > 0.0 &&
            risk_pips >= InpMinSLPips && risk_pips <= InpMaxSLPips &&
            reward / risk >= InpMinRR)
         {
            if(SubmitMarketOrder(ORDER_TYPE_BUY, sl, tp, "CB Trend Long"))
            {
               ResetBullState();
               return;
            }
         }
         ResetBullState();
      }
   }
}
//+------------------------------------------------------------------+
