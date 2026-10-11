// Asian Session Liquidity & Range EA — Phase 2 DEMO/Strategy-Tester candidate
// M15 only. Times are UTC and converted with InpServerUtcOffsetHours.
#property strict
#include <Trade/Trade.mqh>
CTrade trade;

input long   InpMagic=18152023;
input bool   InpAllowLiveAccount=false;
input double InpRiskPercent=0.50;
input double InpFixedLots=0.0;
input int    InpServerUtcOffsetHours=3;
input bool   InpAutoDetectServerOffset=true;
input int    InpAsianStartUtc=0;
input int    InpAsianEndUtc=7;
input int    InpEntryEndUtc=18;
input double InpMinimumRangePips=10.0;
input double InpPiercePips=1.0;
input double InpMaxSpreadRiskFraction=0.20;
input int    InpMaxTradesPerSession=3;
input double InpMaxSessionLossR=-2.0;
input int    InpCooldownBars=4;

datetime dayKey=0,lastBar=0,cooldownUntil=0;
double asianHigh=0,asianLow=0,initialRisk=0,sessionR=0;
int sessionTrades=0; bool locked=false;

int ServerOffsetSeconds(){
  if(!InpAutoDetectServerOffset) return InpServerUtcOffsetHours*3600;
  int seconds=(int)(TimeTradeServer()-TimeGMT());
  int hours=(int)MathRound((double)seconds/3600.0);
  return ((hours==2||hours==3)?hours:InpServerUtcOffsetHours)*3600;
}
datetime UtcTime(datetime serverTime){ return serverTime-ServerOffsetSeconds(); }
datetime ServerTime(datetime utcTime){ return utcTime+ServerOffsetSeconds(); }
datetime DayStart(datetime utc){ MqlDateTime x; TimeToStruct(utc,x); x.hour=x.min=x.sec=0; return StructToTime(x); }
double Pip(){ return (_Digits==3||_Digits==5)?10*_Point:_Point; }

bool TradingEnvironmentOK(){
  long mode=AccountInfoInteger(ACCOUNT_TRADE_MODE);
  if(mode==ACCOUNT_TRADE_MODE_REAL && !InpAllowLiveAccount){ Print("Real account blocked; set InpAllowLiveAccount explicitly"); return false; }
  return true;
}
double Lots(double entry,double stop){
  if(InpFixedLots>0) return MathMax(SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN),InpFixedLots);
  double risk=AccountInfoDouble(ACCOUNT_EQUITY)*InpRiskPercent/100.0, tickValue=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_VALUE);
  double tickSize=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE), step=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_STEP);
  if(tickValue<=0||tickSize<=0||step<=0) return 0;
  double raw=risk/(MathAbs(entry-stop)/tickSize*tickValue);
  return MathFloor(raw/step)*step;
}
bool LockAsian(datetime utcDay){
  datetime a=ServerTime(utcDay+InpAsianStartUtc*3600), b=ServerTime(utcDay+InpAsianEndUtc*3600);
  MqlRates r[]; ArraySetAsSeries(r,false); int n=CopyRates(_Symbol,PERIOD_M15,a,b-1,r);
  if(n!=28) return false;
  asianHigh=r[0].high; asianLow=r[0].low;
  for(int i=1;i<n;i++){ asianHigh=MathMax(asianHigh,r[i].high); asianLow=MathMin(asianLow,r[i].low); }
  initialRisk=(asianHigh-asianLow)*0.25;
  return (asianHigh-asianLow)>=InpMinimumRangePips*Pip();
}
void ResetDay(datetime utcDay){ dayKey=utcDay; sessionTrades=0; sessionR=0; locked=false; cooldownUntil=0; asianHigh=asianLow=initialRisk=0; LockAsian(utcDay); }

void DetectAndPlace(const MqlRates &b){
  if(locked||initialRisk<=0||sessionTrades>=InpMaxTradesPerSession||UtcTime(b.time)<cooldownUntil) return;
  MqlDateTime u; TimeToStruct(UtcTime(b.time),u); if(u.hour<InpAsianEndUtc||u.hour>=InpEntryEndUtc) return;
  double spread=SymbolInfoDouble(_Symbol,SYMBOL_ASK)-SymbolInfoDouble(_Symbol,SYMBOL_BID);
  if(spread>InpMaxSpreadRiskFraction*initialRisk) return;
  bool longSweep=b.low<=asianLow-InpPiercePips*Pip() && b.close>asianLow;
  bool shortSweep=b.high>=asianHigh+InpPiercePips*Pip() && b.close<asianHigh;
  if(longSweep==shortSweep) return;
  bool buy=longSweep; double entry=buy?asianLow:asianHigh, stop=buy?entry-initialRisk:entry+initialRisk;
  double target=buy?entry+5*initialRisk:entry-5*initialRisk, lots=Lots(entry,stop); if(lots<=0) return;
  trade.SetExpertMagicNumber(InpMagic);
  bool ok=buy?trade.BuyLimit(lots,entry,_Symbol,stop,target,ORDER_TIME_DAY,0,"ASIAN_LONG"):
              trade.SellLimit(lots,entry,_Symbol,stop,target,ORDER_TIME_DAY,0,"ASIAN_SHORT");
  if(ok) sessionTrades++;
}

void ManagePosition(){
  if(!PositionSelect(_Symbol)||PositionGetInteger(POSITION_MAGIC)!=InpMagic) return;
  double entry=PositionGetDouble(POSITION_PRICE_OPEN), volume=PositionGetDouble(POSITION_VOLUME);
  double sl=PositionGetDouble(POSITION_SL), current=PositionGetDouble(POSITION_PRICE_CURRENT);
  bool buy=PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY;
  double partial=buy?asianHigh:asianLow;
  if((buy&&current>=partial)||(!buy&&current<=partial)){
    if(MathAbs(sl-entry)>_Point){
      double closeVolume=volume*0.75, step=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_STEP);
      closeVolume=MathFloor(closeVolume/step)*step;
      if(closeVolume>=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN)) trade.PositionClosePartial(_Symbol,closeVolume);
      trade.PositionModify(_Symbol,entry,PositionGetDouble(POSITION_TP));
    }
  }
}

int OnInit(){ if(_Period!=PERIOD_M15||!TradingEnvironmentOK()) return INIT_FAILED; trade.SetExpertMagicNumber(InpMagic); return INIT_SUCCEEDED; }
void OnTick(){
  datetime utc=UtcTime(TimeCurrent()), d=DayStart(utc); if(d!=dayKey) ResetDay(d);
  ManagePosition();
  datetime bar=iTime(_Symbol,PERIOD_M15,0); if(bar==lastBar) return; lastBar=bar;
  MqlRates closed[]; ArraySetAsSeries(closed,true); if(CopyRates(_Symbol,PERIOD_M15,1,1,closed)!=1) return;
  DetectAndPlace(closed[0]);
}
void OnTradeTransaction(const MqlTradeTransaction &trans,const MqlTradeRequest &req,const MqlTradeResult &res){
  if(trans.type!=TRADE_TRANSACTION_DEAL_ADD||!HistoryDealSelect(trans.deal)) return;
  if(HistoryDealGetInteger(trans.deal,DEAL_MAGIC)!=InpMagic||HistoryDealGetInteger(trans.deal,DEAL_ENTRY)!=DEAL_ENTRY_OUT) return;
  double pnl=HistoryDealGetDouble(trans.deal,DEAL_PROFIT)+HistoryDealGetDouble(trans.deal,DEAL_COMMISSION)+HistoryDealGetDouble(trans.deal,DEAL_SWAP);
  double riskCash=AccountInfoDouble(ACCOUNT_EQUITY)*InpRiskPercent/100.0; if(riskCash>0) sessionR+=pnl/riskCash;
  if(pnl<0) cooldownUntil=UtcTime((datetime)HistoryDealGetInteger(trans.deal,DEAL_TIME))+InpCooldownBars*15*60;
  if(sessionR<=InpMaxSessionLossR) locked=true;
  if(pnl>0 && !PositionSelect(_Symbol)) locked=true; // completed winner locks the session
}
