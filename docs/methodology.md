# PAYSCAPE-X Outcome Methodology

**Status: methodology only. The Outcome Engine is not implemented in Part 1
(Rule 2).**

## Outcome states

Every transaction is classified into one of four states:

| State         | Meaning |
|---------------|---------|
| `FULFILLED`   | The intended business outcome was achieved and verified with evidence. |
| `AT_RISK`     | Payment succeeded but the outcome is not yet confirmed (delay, stock shortfall, carrier exception). |
| `FAILED`      | The outcome definitively did not happen despite payment success (lost shipment, no provisioning, refund). |
| `UNVERIFIABLE`| There is not enough structured event evidence to decide (missing events). |

> `UNVERIFIABLE` is a first-class answer. Guessing is forbidden.

## Method (planned)

1. **Reconstruct** the journey from `TransactionEvent` rows in time order.
2. **Verify intent** — what did this order promise (deliver goods, activate
   service, renew subscription)?
3. **Check consistency** — do the events contradict each other (paid +
   out-of-stock, shipped + never delivered)?
4. **Apply rules** — SLA windows, provider semantics, inventory allocation
   behaviour.
5. **Classify** using only confirmed evidence.
6. **Record** the evidence trail for every classification so an operator can
   audit it.

## Metrics (planned)

- **Payment Success** — attempts that succeeded.
- **Business Outcome Success** — successful payments whose intended outcome
  was fulfilled.
- **At Risk** — successful payments whose outcome is unconfirmed.
- **Failed Outcomes** — successful payments that definitively failed.

The gap between Payment Success and Business Outcome Success is the metric
PAYSCAPE-X exists to surface.
