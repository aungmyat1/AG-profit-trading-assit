"""MT5 broker adapter. Boring by design: exposes connect/account/candles/tick/positions/
order_check/order_send and nothing that interprets what the data means -- no TREND/RANGE
classification, no signal logic. See ../PROJECT_STATUS.md 'Authority order'.

Status: scaffolding only, not yet implemented. MT5_MCP_SETUP.md documents an existing
MCP-based conversational path for spot-checks; this package is the separate, scripted
path for anything that becomes a strategy input or executed order (see that file's
'What the MCP does not replace').
"""
