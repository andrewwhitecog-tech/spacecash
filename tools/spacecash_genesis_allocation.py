"""Create and verify SpaceCash genesis allocation files."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from spacecash_core import protocol  # noqa: E402


ALLOCATION_MODE = "spacecash-genesis-allocation-v1"
ALLOCATION_VERSION = 1
TEMPLATE_STATUS = "template_only_not_approved"
APPROVED_STATUS = "approved"
REQUIRED_ALLOCATION_FIELDS = ("address", "amount_units", "label", "basis", "reviewer")
REQUIRED_APPROVAL_FIELDS = ("approved_by", "approved_at", "reviewed_source_hash")


def _hash_body(allocation):
    return {k: v for k, v in allocation.items() if k != "allocation_hash"}


def allocation_hash(allocation):
    return protocol.hash_text(protocol.canonical_json(_hash_body(allocation)))


def genesis_allocation_template():
    allocation = {
        "mode": ALLOCATION_MODE,
        "version": ALLOCATION_VERSION,
        "chain_id": protocol.CHAIN_ID,
        "genesis_plan_id": protocol.GENESIS_PLAN_ID,
        "genesis_plan_hash": protocol.genesis_plan_hash(),
        "monetary_policy_id": protocol.MONETARY_POLICY_ID,
        "monetary_policy_hash": protocol.monetary_policy_hash(),
        "supply_cap_units": protocol.GENESIS_UNITS,
        "supply_cap": protocol.units_to_amount(protocol.GENESIS_UNITS),
        "status": TEMPLATE_STATUS,
        "required_allocation_fields": list(REQUIRED_ALLOCATION_FIELDS),
        "allocations": [],
        "rules": [
            "Historical devnet wallet balances do not automatically migrate.",
            "Candidate private keys are not allowed in a launch allocation.",
            "Every allocation row must have address, amount_units, label, basis, and reviewer.",
            "The approved allocation total must exactly equal the protocol supply cap.",
            "The approval block and manual legal/compliance gate must be complete before launch.",
        ],
        "approval": {
            "approved": False,
            "approved_by": "",
            "approved_at": "",
            "reviewed_source_hash": "",
            "notes": "",
        },
        "manual_gate": {
            "id": "legal_compliance_review_complete",
            "status": "not_complete",
            "reason": "A human-reviewed allocation basis, distribution plan, treasury controls, and legal/compliance approval are required before launch.",
        },
    }
    allocation["allocation_hash"] = allocation_hash(allocation)
    return allocation


def _non_empty_text(value):
    return isinstance(value, str) and bool(value.strip())


def _positive_int(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def validate_allocation(data, require_approved=False):
    errors = []
    warnings = []
    total_units = 0
    duplicate_addresses = []

    if not isinstance(data, dict):
        return {
            "ok": False,
            "allocation_ready": False,
            "errors": ["Allocation document must be a JSON object."],
            "warnings": [],
            "total_units": 0,
            "supply_cap_units": protocol.GENESIS_UNITS,
        }

    expected_fields = {
        "mode": ALLOCATION_MODE,
        "version": ALLOCATION_VERSION,
        "chain_id": protocol.CHAIN_ID,
        "genesis_plan_id": protocol.GENESIS_PLAN_ID,
        "genesis_plan_hash": protocol.genesis_plan_hash(),
        "monetary_policy_id": protocol.MONETARY_POLICY_ID,
        "monetary_policy_hash": protocol.monetary_policy_hash(),
        "supply_cap_units": protocol.GENESIS_UNITS,
    }
    for field, expected in expected_fields.items():
        if data.get(field) != expected:
            errors.append(f"{field} must equal {expected!r}.")

    supplied_hash = data.get("allocation_hash")
    computed_hash = allocation_hash(data)
    if supplied_hash and supplied_hash != computed_hash:
        errors.append("allocation_hash does not match the canonical allocation document.")
    elif not supplied_hash:
        warnings.append("allocation_hash is missing; verifier computed a hash for review.")

    required_fields = data.get("required_allocation_fields")
    if required_fields != list(REQUIRED_ALLOCATION_FIELDS):
        errors.append("required_allocation_fields must match the v1 allocation schema.")

    allocations = data.get("allocations")
    if not isinstance(allocations, list):
        errors.append("allocations must be a list.")
        allocations = []

    seen = set()
    for index, row in enumerate(allocations):
        prefix = f"allocations[{index}]"
        if not isinstance(row, dict):
            errors.append(f"{prefix} must be an object.")
            continue
        missing = [field for field in REQUIRED_ALLOCATION_FIELDS if field not in row]
        if missing:
            errors.append(f"{prefix} missing required fields: {', '.join(missing)}.")
        address = row.get("address")
        if not protocol.valid_address(address):
            errors.append(f"{prefix}.address is not a valid SpaceCash address.")
        elif address in seen:
            duplicate_addresses.append(address)
            errors.append(f"{prefix}.address duplicates an earlier allocation.")
        else:
            seen.add(address)
        amount_units = row.get("amount_units")
        if not _positive_int(amount_units):
            errors.append(f"{prefix}.amount_units must be a positive integer.")
        else:
            total_units += amount_units
        for text_field in ("label", "basis", "reviewer"):
            if not _non_empty_text(row.get(text_field)):
                errors.append(f"{prefix}.{text_field} must be non-empty text.")

    supply_cap_units = data.get("supply_cap_units") if _positive_int(data.get("supply_cap_units")) else protocol.GENESIS_UNITS
    if total_units > supply_cap_units:
        errors.append("allocation total exceeds the supply cap.")
    if total_units != supply_cap_units:
        warnings.append("allocation total does not match the supply cap.")

    approval = data.get("approval") if isinstance(data.get("approval"), dict) else {}
    manual_gate = data.get("manual_gate") if isinstance(data.get("manual_gate"), dict) else {}
    status = data.get("status")
    approved = bool(approval.get("approved")) and status == APPROVED_STATUS
    manual_gate_complete = (
        manual_gate.get("id") == "legal_compliance_review_complete"
        and manual_gate.get("status") == "complete"
    )

    if status not in (TEMPLATE_STATUS, APPROVED_STATUS):
        errors.append(f"status must be {TEMPLATE_STATUS!r} or {APPROVED_STATUS!r}.")

    if require_approved or status == APPROVED_STATUS or approval.get("approved"):
        if status != APPROVED_STATUS:
            errors.append("status must be approved for a launch allocation.")
        if approval.get("approved") is not True:
            errors.append("approval.approved must be true for a launch allocation.")
        for field in REQUIRED_APPROVAL_FIELDS:
            if not _non_empty_text(approval.get(field)):
                errors.append(f"approval.{field} is required for a launch allocation.")
        if not manual_gate_complete:
            errors.append("manual_gate must complete legal_compliance_review_complete for a launch allocation.")
        if total_units != supply_cap_units:
            errors.append("approved launch allocation total must equal the supply cap.")
        if not supplied_hash:
            errors.append("allocation_hash is required for a launch allocation.")

    allocation_ready = bool(
        not errors
        and approved
        and manual_gate_complete
        and total_units == supply_cap_units
        and supplied_hash == computed_hash
    )
    return {
        "ok": not errors,
        "allocation_ready": allocation_ready,
        "status": status,
        "chain_id": data.get("chain_id"),
        "computed_allocation_hash": computed_hash,
        "allocation_hash": supplied_hash,
        "total_units": total_units,
        "total": protocol.units_to_amount(total_units),
        "supply_cap_units": supply_cap_units,
        "supply_cap": protocol.units_to_amount(supply_cap_units),
        "allocation_count": len(allocations),
        "duplicate_addresses": duplicate_addresses,
        "manual_gate_status": manual_gate.get("status"),
        "approval_status": approval.get("approved"),
        "errors": errors,
        "warnings": warnings,
    }


def write_allocation_template(out_path=None):
    allocation = genesis_allocation_template()
    if out_path:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(allocation, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return allocation


def load_allocation(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_parser():
    parser = argparse.ArgumentParser(description="Create or verify a SpaceCash genesis allocation JSON file")
    parser.add_argument("--template-out", type=Path, help="Optional path to write the empty allocation template")
    parser.add_argument("--verify", type=Path, help="Allocation JSON file to verify")
    parser.add_argument("--require-approved", action="store_true", help="Fail unless the allocation is approved and supply-complete")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.verify:
        result = validate_allocation(load_allocation(args.verify), require_approved=args.require_approved)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("ok") and (not args.require_approved or result.get("allocation_ready")) else 2
    allocation = write_allocation_template(args.template_out)
    print(json.dumps(allocation, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
