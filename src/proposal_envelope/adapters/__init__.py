"""Adapters mapping existing strategy-specific outputs into the canonical
proposal_envelope.models.CanonicalProposal shape. Each adapter is a pure, one-way,
lossless mapping function -- no detection logic, no execution imports, no behavior
change to the source module it reads from."""
