---
name: multi-asset-conventions
description: Define correct market conventions and P&L mechanics for multi-asset research across equities/ETFs, FX, crypto spot/perpetuals, and futures. Use when a backtest needs calendars, sessions, contract multipliers, tick or pip values, quote/base currencies, rolls, funding, borrow, dividends, leverage, or cross-currency conversion.
---

# Multi-Asset Conventions

Before calculating positions or P&L, create an instrument master. Never assume one formula fits every asset class.

## Instrument master fields

Record, when relevant:

- stable instrument ID and vendor symbols;
- asset class and venue;
- quote, base, settlement, and account currencies;
- timezone, session, holidays, and 24/7 status;
- price scale, minimum tick, lot size, and contract multiplier;
- expiry, first notice, last trade, and roll policy;
- funding, financing, borrow, dividends, and corporate actions;
- margin method and leverage cap;
- data adjustment policy.

## Asset-class checks

### Equities and ETFs

- Use split/dividend-consistent returns.
- Include delisted names and point-in-time index membership when testing a universe.
- Model borrow availability and fees for shorts.
- Distinguish close-auction information from trades assumed at that close.
- Flag ETF distributions, closures, and underlying-market timezone mismatches.

### FX

- State pair direction: units of quote currency per base currency.
- Convert pip/tick P&L into account currency at the correct timestamp.
- Define the trading-day cutoff and weekend treatment.
- Include rollover/carry and changing interest-rate differentials when material.
- Do not treat decentralized FX as having one universal close or volume series.

### Crypto spot and perpetuals

- Treat venue data, fees, outages, and liquidity as exchange-specific.
- Include maker/taker fees, funding timestamps, funding direction, and settlement currency.
- Define 24/7 daily-bar boundaries explicitly.
- Model liquidation or margin constraints only if the data and rules support them.
- Do not merge symbols across venues without documenting basis and transfer assumptions.

### Futures

- Calculate P&L using contract multiplier and position count.
- Build continuous series without pretending synthetic roll adjustments are executable prices.
- Define roll trigger, roll window, and both legs' costs.
- Avoid holding through first notice or delivery unless explicitly modeled.
- Respect changing contract specifications and expiry calendars.

## P&L contract

For every instrument, write the exact equation from price move to native-currency P&L, then the conversion to account currency. Include fees, spread/slippage, financing/funding, borrow/dividends, and roll effects as separate components.

## Output

Produce:

1. instrument master table;
2. session/calendar policy;
3. executable price and fill convention;
4. P&L and currency-conversion equations;
5. cost components;
6. unresolved convention risks.

If a required multiplier, rate, calendar, or adjustment field is unavailable, stop and flag it instead of substituting a convenient default.
