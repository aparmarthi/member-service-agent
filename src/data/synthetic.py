"""Synthetic member/order data generator.

Reproduces the *structure* of the PBM order payload (member → patients → orders
→ prescriptions) with entirely fabricated values. No real member data is used or
required. Scenario builders cover the edge cases the agent must handle (multi-patient
family, payment holds, mixed statuses, no-orders, refill-eligible,
escalation-required) so evals exercise them.

Determinism: a seeded ``random.Random`` is threaded through so fixtures are
reproducible without relying on global RNG state. Order dates are relative to
today (``_days_ago``) so lookback windows behave the same whenever this runs.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

from src.config.reason_codes import CATALOG
from src.models.schemas import Member, Order, Patient, Prescription

_FIRST_NAMES = ["Ada", "Rumi", "Kai", "Nova", "Favi", "Iris", "Otto", "Zia", "Milo", "Esme"]
_LAST_NAMES = ["Vega", "Rowe", "Tan", "Okoro", "Reyes", "Haas", "Lindqvist", "Baptiste"]
_DRUGS = [
    "ATORVASTATIN 20MG TAB", "LISINOPRIL 10MG TAB", "PEPCID 20MG TAB",
    "JANUVIA 50MG TAB", "SYNTHROID 50MCG TAB", "BRILINTA 60MG TAB",
    "ACTOS 30MG TAB", "AMOXICILLIN 500MG TAB", "TOPAMAX 50MG TAB",
]
# A representative slice of the catalog covering each priority tier.
_STATUS_POOL = [
    "PAYMENT_METHOD_HOLD", "HIGH_COST_HOLD", "SHIP_CONSENT_HOLD",
    "IN_PROCESS", "CHECKING_INVENTORY",
    "SHIPPED_NO_TRACKING", "DELIVERED_CONFIRMED", "FUTURE_FILL",
    "PA_REQUIRED", "ORDER_CANCELED",
]


def _rng(seed: int) -> random.Random:
    return random.Random(seed)


def _days_ago(days: int) -> str:
    return (date.today() - timedelta(days=days)).isoformat()


def _fake_id(rng: random.Random, width: int = 9) -> str:
    return "".join(str(rng.randint(0, 9)) for _ in range(width))


def _make_rx(
    rng: random.Random,
    status_code: str,
    drug: str | None = None,
    condition_code: str | None = None,
) -> Prescription:
    cond = condition_code if condition_code is not None else rng.choice(["0", "17", "21", "3"])
    return Prescription(
        rx_number=_fake_id(rng, 9),
        drug_name=drug or rng.choice(_DRUGS),
        status_code=status_code,
        condition_code=cond,
        price=round(rng.uniform(5, 320), 2),
    )


def _make_order(rng: random.Random, status_code: str, age_days: int = 3, n_rx: int = 1) -> Order:
    return Order(
        order_number=_fake_id(rng, 10),
        order_date=_days_ago(age_days),
        prescriptions=[_make_rx(rng, status_code) for _ in range(n_rx)],
        tracking_id=_fake_id(rng, 12) if status_code.startswith("SHIPPED") else None,
    )


def _patient(
    rng: random.Random, rel: str, *, status_codes: list[str], ages: list[int] | None = None
) -> Patient:
    ages = ages or [3] * len(status_codes)
    return Patient(
        internal_id=_fake_id(rng),
        first_name=rng.choice(_FIRST_NAMES),
        last_name=rng.choice(_LAST_NAMES),
        dob="1988-01-01",
        relationship=rel,  # type: ignore[arg-type]
        orders=[_make_order(rng, sc, age) for sc, age in zip(status_codes, ages)],
    )


# ---- Named scenarios (one per edge case) ----


def single_patient_mixed_statuses(seed: int = 1) -> Member:
    """One member, multiple orders spanning several priority tiers and ages.

    Ages are chosen so the channels diverge: chat (45 days) sees all five; voice
    (10 days, 30 for future fills) drops the 25-day-old delivery.
    """
    rng = _rng(seed)
    codes = ["PAYMENT_METHOD_HOLD", "IN_PROCESS",
             "SHIPPED_NO_TRACKING", "DELIVERED_CONFIRMED", "FUTURE_FILL"]
    self_patient = _patient(rng, "self", status_codes=codes, ages=[3, 1, 6, 25, 20])
    return Member(member_id=_fake_id(rng, 11), internal_id=self_patient.internal_id,
                  patients=[self_patient])


def family_plan(seed: int = 2) -> Member:
    """Account holder plus spouse and child, each with active orders."""
    rng = _rng(seed)
    holder = _patient(rng, "self", status_codes=["SHIPPED_NO_TRACKING"])
    spouse = _patient(rng, "spouse", status_codes=["HIGH_COST_HOLD"])
    child = _patient(rng, "child", status_codes=["CHECKING_INVENTORY"])
    return Member(member_id=_fake_id(rng, 11), internal_id=holder.internal_id,
                  patients=[holder, spouse, child])


def no_orders(seed: int = 3) -> Member:
    """Member with zero orders in any window (escalation / refill-check path)."""
    rng = _rng(seed)
    p = Patient(internal_id=_fake_id(rng), first_name=rng.choice(_FIRST_NAMES),
                last_name=rng.choice(_LAST_NAMES), dob="1990-01-01", relationship="self")
    return Member(member_id=_fake_id(rng, 11), internal_id=p.internal_id, patients=[p])


def escalation_required(seed: int = 4) -> Member:
    """Member whose only order carries a must-transfer profile hold."""
    rng = _rng(seed)
    p = _patient(rng, "self", status_codes=["PROFILE_HOLD"])
    return Member(member_id=_fake_id(rng, 11), internal_id=p.internal_id, patients=[p])


def payment_hold(seed: int = 5) -> Member:
    """Member with a resolvable payment-method hold (action-path fixture)."""
    rng = _rng(seed)
    p = _patient(rng, "self", status_codes=["PAYMENT_METHOD_HOLD"])
    return Member(member_id=_fake_id(rng, 11), internal_id=p.internal_id, patients=[p])


def refill_mixed_conditions(seed: int = 6) -> Member:
    """Member with prescriptions spanning refill condition codes.

    Covers ready-to-refill (0), renewal (17), controlled substance (5, cannot
    refill), too-early (1), and an unconfigured transfer code (8).
    """
    rng = _rng(seed)
    orders = [
        Order(order_number=_fake_id(rng, 10), order_date=_days_ago(20),
              prescriptions=[_make_rx(rng, "IN_PROCESS",
                                      drug="ATORVASTATIN 20MG TAB", condition_code="0")]),
        Order(order_number=_fake_id(rng, 10), order_date=_days_ago(20),
              prescriptions=[_make_rx(rng, "RENEWAL_NEEDED",
                                      drug="LISINOPRIL 10MG TAB", condition_code="17")]),
        Order(order_number=_fake_id(rng, 10), order_date=_days_ago(20),
              prescriptions=[_make_rx(rng, "IN_PROCESS",
                                      drug="ADDERALL 20MG TAB", condition_code="5")]),
        Order(order_number=_fake_id(rng, 10), order_date=_days_ago(20),
              prescriptions=[_make_rx(rng, "FUTURE_FILL",
                                      drug="PEPCID 20MG TAB", condition_code="1")]),
    ]
    p = Patient(internal_id=_fake_id(rng), first_name=rng.choice(_FIRST_NAMES),
                last_name=rng.choice(_LAST_NAMES), dob="1988-01-01",
                relationship="self", orders=orders)
    return Member(member_id=_fake_id(rng, 11), internal_id=p.internal_id, patients=[p])


def refill_transfer_only(seed: int = 7) -> Member:
    """Member whose only Rx has an unconfigured condition code (forces transfer)."""
    rng = _rng(seed)
    o = Order(order_number=_fake_id(rng, 10), order_date=_days_ago(20),
              prescriptions=[_make_rx(rng, "IN_PROCESS",
                                      drug="TOPAMAX 50MG TAB", condition_code="8")])
    p = Patient(internal_id=_fake_id(rng), first_name=rng.choice(_FIRST_NAMES),
                last_name=rng.choice(_LAST_NAMES), dob="1988-01-01",
                relationship="self", orders=[o])
    return Member(member_id=_fake_id(rng, 11), internal_id=p.internal_id, patients=[p])


def older_orders_only(seed: int = 8) -> Member:
    """Member whose only orders are 2–4 months old (chat's 6-month search path)."""
    rng = _rng(seed)
    p = _patient(rng, "self", status_codes=["DELIVERED_CONFIRMED", "ORDER_CANCELED"],
                 ages=[70, 120])
    return Member(member_id=_fake_id(rng, 11), internal_id=p.internal_id, patients=[p])


def _charged_order(rng: random.Random, status_code: str, drug: str, price: float,
                   charges: list[float], age_days: int = 5) -> Order:
    """An order with explicit plan price and payment captures (refund fixtures)."""
    rx = _make_rx(rng, status_code, drug=drug, condition_code="0")
    rx.price = price
    return Order(order_number=_fake_id(rng, 10), order_date=_days_ago(age_days),
                 prescriptions=[rx], charges=charges)


def refund_small(seed: int = 9) -> Member:
    """Member charged for a cancelled order and charged twice for another ($31.15, auto-approves)."""
    rng = _rng(seed)
    orders = [
        _charged_order(rng, "ORDER_CANCELED", "PEPCID 20MG TAB", 12.40, [12.40]),
        _charged_order(rng, "DELIVERED_CONFIRMED", "LISINOPRIL 10MG TAB", 18.75, [18.75, 18.75]),
    ]
    p = Patient(internal_id=_fake_id(rng), first_name=rng.choice(_FIRST_NAMES),
                last_name=rng.choice(_LAST_NAMES), dob="1988-01-01",
                relationship="self", orders=orders)
    return Member(member_id=_fake_id(rng, 11), internal_id=p.internal_id, patients=[p])


def refund_large(seed: int = 10) -> Member:
    """Member overcharged $87.60 on a copay (above the auto-approve limit, needs a specialist)."""
    rng = _rng(seed)
    orders = [_charged_order(rng, "DELIVERED_CONFIRMED", "JANUVIA 50MG TAB", 45.00, [132.60])]
    p = Patient(internal_id=_fake_id(rng), first_name=rng.choice(_FIRST_NAMES),
                last_name=rng.choice(_LAST_NAMES), dob="1988-01-01",
                relationship="self", orders=orders)
    return Member(member_id=_fake_id(rng, 11), internal_id=p.internal_id, patients=[p])


SCENARIOS = {
    "single_patient_mixed_statuses": single_patient_mixed_statuses,
    "family_plan": family_plan,
    "no_orders": no_orders,
    "escalation_required": escalation_required,
    "payment_hold": payment_hold,
    "refill_mixed_conditions": refill_mixed_conditions,
    "refill_transfer_only": refill_transfer_only,
    "older_orders_only": older_orders_only,
    "refund_small": refund_small,
    "refund_large": refund_large,
}


def build(scenario: str, seed: int | None = None) -> Member:
    """Build a synthetic member for a named scenario.

    Args:
        scenario: One of :data:`SCENARIOS`.
        seed: Optional seed override for reproducibility.

    Returns:
        A fully populated synthetic :class:`Member`.

    Raises:
        KeyError: If the scenario name is unknown.
    """
    fn = SCENARIOS[scenario]
    return fn() if seed is None else fn(seed)
