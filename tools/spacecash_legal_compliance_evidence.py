"""Create and verify SpaceCash legal/compliance review evidence.

This verifier checks that legal/compliance review evidence is complete and
structured. It does not provide legal advice or replace counsel review.
"""

import argparse
import hashlib
import json
import re
import secrets
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = Path(__file__).resolve().parent
for candidate in (ROOT, TOOLS_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from spacecash_core import protocol  # noqa: E402
from spacecash_genesis_allocation import genesis_allocation_template  # noqa: E402


EVIDENCE_MODE = "spacecash-legal-compliance-evidence-v1"
EVIDENCE_VERSION = 1
HASH_RE = re.compile(r"^[0-9A-Fa-f]{64}$")
STATUS_VALUES = ("not_started", "in_review", "blocked", "approved", "rejected")
AREA_STATUSES = ("not_reviewed", "approved", "approved_with_conditions", "blocked", "not_applicable")
FINAL_DECISIONS = ("not_reviewed", "approved", "approved_with_conditions", "no_launch")
READY_AREA_STATUSES = ("approved", "approved_with_conditions", "not_applicable")

REQUIRED_REVIEW_AREAS = (
    {"id": "token_payment_classification", "title": "Token And Payment Classification"},
    {"id": "supply_distribution_treasury", "title": "Supply, Distribution, Treasury, Fee, And Burn Policy"},
    {"id": "genesis_allocation_basis", "title": "Genesis Allocation Basis And Migration Boundary"},
    {"id": "consumer_protection_refunds", "title": "Consumer Protection And Refund Terms"},
    {"id": "tax_reporting", "title": "Tax Treatment And Reporting Responsibilities"},
    {"id": "restricted_product_controls", "title": "Restricted Product Controls"},
    {"id": "customer_support", "title": "Customer Support Workflow"},
    {"id": "privacy_data_retention", "title": "Data Retention And Privacy Policy"},
    {"id": "marketing_risk_disclosures", "title": "Marketing And Risk Disclosures"},
    {"id": "jurisdiction_availability", "title": "Jurisdictional Availability"},
    {"id": "terms_of_service", "title": "Terms Of Service And Launch Communications"},
)

REQUIRED_DOCUMENT_FIELDS = (
    "approved_use_case",
    "prohibited_use_cases",
    "required_disclosures",
    "required_operational_controls",
    "terms_path",
    "privacy_policy_path",
    "refund_policy_path",
    "restricted_product_policy_path",
    "tax_position_path",
)

REQUIRED_DISTRIBUTION_FIELDS = (
    "genesis_allocation_hash",
    "allocation_verifier_output_path",
    "allocation_verifier_output_sha256",
    "treasury_controls_path",
    "treasury_controls_sha256",
)

LEGAL_DOCUMENT_WORKPAPERS = {
    "approved_use_case": ("legal/documents/approved_use_case.md", "Approved Use Case"),
    "prohibited_use_cases": ("legal/documents/prohibited_use_cases.md", "Prohibited Use Cases"),
    "required_disclosures": ("legal/documents/required_disclosures.md", "Required Disclosures"),
    "required_operational_controls": ("legal/documents/required_operational_controls.md", "Required Operational Controls"),
    "terms_path": ("legal/documents/terms.md", "Terms Of Service"),
    "privacy_policy_path": ("legal/documents/privacy_policy.md", "Privacy Policy"),
    "refund_policy_path": ("legal/documents/refund_policy.md", "Refund Policy"),
    "restricted_product_policy_path": ("legal/documents/restricted_product_policy.md", "Restricted Product Policy"),
    "tax_position_path": ("legal/documents/tax_position.md", "Tax Position"),
}

DOCUMENT_HASH_FIELDS = {
    "terms_path": "terms_sha256",
    "privacy_policy_path": "privacy_policy_sha256",
    "refund_policy_path": "refund_policy_sha256",
    "restricted_product_policy_path": "restricted_product_policy_sha256",
    "tax_position_path": "tax_position_sha256",
}

DISTRIBUTION_WORKPAPERS = {
    "allocation_verifier_output_path": ("legal/distribution/allocation_verifier_output_placeholder.json", "Allocation Verifier Output"),
    "treasury_controls_path": ("legal/distribution/treasury_controls.md", "Treasury Controls"),
    "fee_policy_path": ("legal/distribution/fee_policy.md", "Fee Policy"),
}

DISTRIBUTION_HASH_FIELDS = {
    "allocation_verifier_output_path": "allocation_verifier_output_sha256",
    "treasury_controls_path": "treasury_controls_sha256",
    "fee_policy_path": "fee_policy_sha256",
}

AREA_QUESTIONS = {
    "token_payment_classification": [
        "Does the intended use remain a product-payment utility rather than an investment product?",
        "What claims must be avoided in launch, wallet, and marketplace copy?",
    ],
    "supply_distribution_treasury": [
        "Does the supply, fee, burn, and treasury policy match the reviewed monetary policy hash?",
        "What approvals and controls are required before treasury movement?",
    ],
    "genesis_allocation_basis": [
        "Does the launch allocation have a written basis, verifier output, and approved allocation hash?",
        "Does the reviewer confirm devnet balances and generated candidate keys are not migrated by default?",
    ],
    "consumer_protection_refunds": [
        "What refund rights and product-delivery obligations apply to SpaceCash payments?",
        "How should failed, reversed, or disputed product orders be handled?",
    ],
    "tax_reporting": [
        "What tax records must be retained for payments, refunds, treasury actions, and promotional credits?",
        "Who is responsible for customer, operator, and treasury reporting?",
    ],
    "restricted_product_controls": [
        "Which products, users, or locations must be blocked before any public use?",
        "What operational checks enforce restricted-product rules?",
    ],
    "customer_support": [
        "What support workflow is required for payment disputes, wallet loss, and order status errors?",
        "What response-time and escalation records should be retained?",
    ],
    "privacy_data_retention": [
        "What personal data is collected by wallet, order, support, and node operations?",
        "What retention, deletion, and access-control rules apply?",
    ],
    "marketing_risk_disclosures": [
        "Do all public materials avoid investment, legal tender, and exchange-listing claims?",
        "What risk disclosures are required near wallet, checkout, and launch communications?",
    ],
    "jurisdiction_availability": [
        "Which jurisdictions are approved, blocked, or pending review?",
        "What operational controls enforce jurisdiction limits?",
    ],
    "terms_of_service": [
        "Do terms, privacy, refund, restricted-product, and tax materials match the reviewed launch scope?",
        "What final communications must be approved before launch?",
    ],
}


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def default_workbench_dir():
    stamp = protocol.utc_now().replace(":", "").replace("-", "").replace("Z", "Z")
    return ROOT / "_tmp" / f"spacecash_legal_compliance_workbench_{stamp}_{secrets.token_hex(4)}"


def safe_reset_dir(path):
    path = Path(path).resolve()
    tmp_root = (ROOT / "_tmp").resolve()
    if path == tmp_root or tmp_root not in path.parents:
        raise ValueError("Refusing to overwrite a legal/compliance workbench outside the project _tmp directory.")
    if path.exists():
        shutil.rmtree(path)


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _hash_relative(out_dir, rel):
    return file_hash(Path(out_dir) / rel)


def _non_empty(value):
    return isinstance(value, str) and bool(value.strip())


def _hash_or_empty(value):
    text = str(value or "").strip()
    return not text or HASH_RE.fullmatch(text) is not None


def _artifact(rel):
    path = ROOT / rel
    return {
        "path": rel,
        "exists": path.exists(),
        "sha256": file_hash(path) if path.exists() else "",
    }


def _default_artifacts():
    return [
        _artifact("docs/spacecash/LEGAL_COMPLIANCE_GATE.md"),
        _artifact("docs/spacecash/MONETARY_POLICY.md"),
        _artifact("docs/spacecash/GENESIS_PLAN.md"),
        _artifact("docs/spacecash/GENESIS_ALLOCATION.md"),
        _artifact("docs/spacecash/MAINNET_GATE.md"),
    ]


def _empty_area(definition):
    return {
        "id": definition["id"],
        "title": definition["title"],
        "status": "not_reviewed",
        "reviewer": "",
        "evidence": "",
        "decision": "not_reviewed",
        "notes": "",
    }


def legal_compliance_evidence_template():
    return {
        "mode": EVIDENCE_MODE,
        "version": EVIDENCE_VERSION,
        "chain_id": protocol.CHAIN_ID,
        "status": "not_started",
        "reviewed_source_hash": "",
        "release_bundle_sha256": "",
        "protocol_hashes": {
            "monetary_policy_hash": protocol.monetary_policy_hash(),
            "genesis_plan_hash": protocol.genesis_plan_hash(),
            "genesis_allocation_hash": genesis_allocation_template().get("allocation_hash"),
            "wallet_policy_hash": protocol.wallet_policy_hash(),
        },
        "artifacts": _default_artifacts(),
        "reviewer": {
            "name": "",
            "firm": "",
            "contact": "",
            "role": "",
            "engagement_letter_path": "",
            "engagement_letter_sha256": "",
        },
        "scope": {
            "intended_use_cases": [],
            "prohibited_use_cases": [],
            "allowed_jurisdictions": [],
            "blocked_jurisdictions": [],
            "product_payment_reviewed": False,
            "public_distribution_reviewed": False,
            "treasury_controls_reviewed": False,
        },
        "review_areas": [_empty_area(definition) for definition in REQUIRED_REVIEW_AREAS],
        "documents": {
            "approved_use_case": "",
            "prohibited_use_cases": "",
            "required_disclosures": "",
            "required_operational_controls": "",
            "terms_path": "",
            "terms_sha256": "",
            "privacy_policy_path": "",
            "privacy_policy_sha256": "",
            "refund_policy_path": "",
            "refund_policy_sha256": "",
            "restricted_product_policy_path": "",
            "restricted_product_policy_sha256": "",
            "tax_position_path": "",
            "tax_position_sha256": "",
        },
        "distribution": {
            "genesis_allocation_hash": "",
            "allocation_verifier_output_path": "",
            "allocation_verifier_output_sha256": "",
            "treasury_controls_path": "",
            "treasury_controls_sha256": "",
            "fee_policy_path": "",
            "fee_policy_sha256": "",
        },
        "final_decision": {
            "decision": "not_reviewed",
            "decided_at": "",
            "reviewer_statement": "",
            "conditions": [],
            "no_investment_claims_confirmed": False,
            "no_legal_tender_claims_confirmed": False,
            "no_exchange_listing_claims_confirmed": False,
            "real_money_use_authorized": False,
        },
        "manual_gate": {
            "id": "legal_compliance_review_complete",
            "status": "not_complete",
            "reason": "Legal/compliance review, distribution basis, disclosures, operating controls, and final decision are required before real-money or mainnet use.",
        },
    }


def _validate_artifacts(artifacts, errors, warnings):
    if not isinstance(artifacts, list):
        errors.append("artifacts must be a list.")
        return []
    verified = []
    for index, artifact in enumerate(artifacts):
        prefix = f"artifacts[{index}]"
        if not isinstance(artifact, dict):
            errors.append(f"{prefix} must be an object.")
            continue
        rel = artifact.get("path")
        if not _non_empty(rel):
            errors.append(f"{prefix}.path is required.")
            continue
        path = ROOT / rel
        exists = path.exists()
        claimed = str(artifact.get("sha256") or "").strip().upper()
        if artifact.get("exists") is True and not exists:
            errors.append(f"{prefix}.exists is true but the file is missing.")
        if exists and claimed:
            actual = file_hash(path)
            if actual != claimed:
                errors.append(f"{prefix}.sha256 does not match {rel}.")
            else:
                verified.append(rel)
        elif not exists:
            warnings.append(f"{rel} is not present yet.")
    return verified


def _validate_reviewer(reviewer, errors, blockers, require_complete):
    if not isinstance(reviewer, dict):
        errors.append("reviewer must be an object.")
        reviewer = {}
    required = ("name", "firm", "contact", "role", "engagement_letter_path")
    missing = [field for field in required if not _non_empty(reviewer.get(field))]
    if missing:
        blockers.append("reviewer_missing")
        if require_complete:
            errors.append(f"reviewer missing required fields: {', '.join(missing)}.")
    engagement_hash = str(reviewer.get("engagement_letter_sha256") or "").strip()
    if not engagement_hash:
        blockers.append("engagement_letter_missing")
        if require_complete:
            errors.append("reviewer.engagement_letter_sha256 is required.")
    elif not HASH_RE.fullmatch(engagement_hash):
        errors.append("reviewer.engagement_letter_sha256 must be a 64-character SHA-256 hash.")


def _validate_scope(scope, errors, blockers, require_complete):
    if not isinstance(scope, dict):
        errors.append("scope must be an object.")
        scope = {}
    for field in ("intended_use_cases", "prohibited_use_cases", "allowed_jurisdictions", "blocked_jurisdictions"):
        value = scope.get(field)
        if not isinstance(value, list):
            errors.append(f"scope.{field} must be a list.")
            value = []
        if require_complete and not value and field != "blocked_jurisdictions":
            errors.append(f"scope.{field} is required.")
            blockers.append(f"{field}_missing")
    for field in ("product_payment_reviewed", "public_distribution_reviewed", "treasury_controls_reviewed"):
        if scope.get(field) is not True:
            blockers.append(f"{field}_not_confirmed")
            if require_complete:
                errors.append(f"scope.{field} must be true.")


def _validate_review_areas(review_areas, errors, blockers, require_complete):
    if not isinstance(review_areas, list):
        errors.append("review_areas must be a list.")
        review_areas = []
    required = {area["id"]: area for area in REQUIRED_REVIEW_AREAS}
    by_id = {}
    ready = []
    for index, area in enumerate(review_areas):
        prefix = f"review_areas[{index}]"
        if not isinstance(area, dict):
            errors.append(f"{prefix} must be an object.")
            continue
        area_id = area.get("id")
        if area_id not in required:
            errors.append(f"{prefix}.id is not a required legal/compliance review area.")
            continue
        if area_id in by_id:
            errors.append(f"{prefix}.id duplicates an earlier review area.")
            continue
        by_id[area_id] = area
        if area.get("title") != required[area_id]["title"]:
            errors.append(f"{area_id}.title does not match the v1 legal/compliance schema.")
        if area.get("status") not in AREA_STATUSES:
            errors.append(f"{area_id}.status must be one of {', '.join(AREA_STATUSES)}.")
        if area.get("status") == "blocked":
            blockers.append(f"{area_id}_blocked")
        if area.get("status") in READY_AREA_STATUSES:
            ready.append(area_id)
        if require_complete or area.get("status") in READY_AREA_STATUSES + ("blocked",):
            if not _non_empty(area.get("reviewer")):
                errors.append(f"{area_id}.reviewer is required.")
            if not _non_empty(area.get("evidence")):
                errors.append(f"{area_id}.evidence is required.")
            if area.get("decision") not in FINAL_DECISIONS:
                errors.append(f"{area_id}.decision must be one of {', '.join(FINAL_DECISIONS)}.")
    for area_id in required:
        if area_id not in by_id:
            errors.append(f"Missing legal/compliance review area {area_id}.")
            blockers.append(f"{area_id}_missing")
        elif by_id[area_id].get("status") not in READY_AREA_STATUSES:
            blockers.append(f"{area_id}_not_approved")
    if len(ready) < len(required):
        blockers.append("review_areas_not_approved")
    return ready


def _validate_documents(documents, errors, blockers, require_complete):
    if not isinstance(documents, dict):
        errors.append("documents must be an object.")
        documents = {}
    for field in REQUIRED_DOCUMENT_FIELDS:
        if not _non_empty(documents.get(field)):
            blockers.append(f"{field}_missing")
            if require_complete:
                errors.append(f"documents.{field} is required.")
    for field, value in documents.items():
        if field.endswith("_sha256") and value and not HASH_RE.fullmatch(str(value).strip()):
            errors.append(f"documents.{field} must be a 64-character SHA-256 hash.")
    if require_complete:
        for path_field in ("terms", "privacy_policy", "refund_policy", "restricted_product_policy", "tax_position"):
            if _non_empty(documents.get(f"{path_field}_path")) and not _non_empty(documents.get(f"{path_field}_sha256")):
                errors.append(f"documents.{path_field}_sha256 is required when {path_field}_path is set.")


def _validate_distribution(distribution, errors, blockers, require_complete):
    if not isinstance(distribution, dict):
        errors.append("distribution must be an object.")
        distribution = {}
    for field in REQUIRED_DISTRIBUTION_FIELDS:
        if not _non_empty(distribution.get(field)):
            blockers.append(f"{field}_missing")
            if require_complete:
                errors.append(f"distribution.{field} is required.")
    for field, value in distribution.items():
        if field.endswith("_hash") or field.endswith("_sha256"):
            if value and not HASH_RE.fullmatch(str(value).strip()):
                errors.append(f"distribution.{field} must be a 64-character SHA-256 hash.")
    expected_template_hash = genesis_allocation_template().get("allocation_hash")
    allocation_hash = str(distribution.get("genesis_allocation_hash") or "").strip()
    if allocation_hash and allocation_hash == expected_template_hash:
        blockers.append("launch_allocation_not_approved")
        if require_complete:
            errors.append("distribution.genesis_allocation_hash must reference an approved launch allocation, not the empty template hash.")


def _validate_final_decision(final_decision, errors, blockers, require_complete):
    if not isinstance(final_decision, dict):
        errors.append("final_decision must be an object.")
        final_decision = {}
    decision = final_decision.get("decision")
    if decision not in FINAL_DECISIONS:
        errors.append(f"final_decision.decision must be one of {', '.join(FINAL_DECISIONS)}.")
    if decision not in ("approved", "approved_with_conditions"):
        blockers.append("final_decision_not_approved")
        if require_complete:
            errors.append("final_decision.decision must be approved or approved_with_conditions.")
    for field in ("decided_at", "reviewer_statement"):
        if not _non_empty(final_decision.get(field)):
            blockers.append(f"final_decision_{field}_missing")
            if require_complete:
                errors.append(f"final_decision.{field} is required.")
    conditions = final_decision.get("conditions")
    if not isinstance(conditions, list):
        errors.append("final_decision.conditions must be a list.")
    for field in ("no_investment_claims_confirmed", "no_legal_tender_claims_confirmed", "no_exchange_listing_claims_confirmed", "real_money_use_authorized"):
        if final_decision.get(field) is not True:
            blockers.append(f"{field}_not_confirmed")
            if require_complete:
                errors.append(f"final_decision.{field} must be true.")


def validate_legal_compliance_evidence(data, require_complete=False):
    errors = []
    warnings = []
    blockers = []

    if not isinstance(data, dict):
        return {
            "ok": False,
            "legal_compliance_ready": False,
            "errors": ["Legal/compliance evidence must be a JSON object."],
            "warnings": [],
            "blockers": ["schema"],
        }

    if data.get("mode") != EVIDENCE_MODE:
        errors.append(f"mode must equal {EVIDENCE_MODE!r}.")
    if data.get("version") != EVIDENCE_VERSION:
        errors.append(f"version must equal {EVIDENCE_VERSION}.")
    if data.get("chain_id") != protocol.CHAIN_ID:
        errors.append(f"chain_id must equal {protocol.CHAIN_ID!r}.")
    if data.get("status") not in STATUS_VALUES:
        errors.append(f"status must be one of {', '.join(STATUS_VALUES)}.")

    expected_hashes = legal_compliance_evidence_template()["protocol_hashes"]
    hashes = data.get("protocol_hashes") if isinstance(data.get("protocol_hashes"), dict) else {}
    for field, expected in expected_hashes.items():
        if hashes.get(field) != expected:
            errors.append(f"protocol_hashes.{field} must equal {expected}.")

    for field in ("reviewed_source_hash", "release_bundle_sha256"):
        value = str(data.get(field) or "").strip()
        if not value:
            blockers.append(f"{field}_missing")
            if require_complete:
                errors.append(f"{field} is required.")
        elif not _hash_or_empty(value):
            errors.append(f"{field} must be a 64-character SHA-256 hash.")

    verified_artifacts = _validate_artifacts(data.get("artifacts") or [], errors, warnings)
    _validate_reviewer(data.get("reviewer"), errors, blockers, require_complete)
    _validate_scope(data.get("scope"), errors, blockers, require_complete)
    approved_areas = _validate_review_areas(data.get("review_areas") or [], errors, blockers, require_complete)
    _validate_documents(data.get("documents"), errors, blockers, require_complete)
    _validate_distribution(data.get("distribution"), errors, blockers, require_complete)
    _validate_final_decision(data.get("final_decision"), errors, blockers, require_complete)

    manual_gate = data.get("manual_gate") if isinstance(data.get("manual_gate"), dict) else {}
    manual_gate_complete = (
        manual_gate.get("id") == "legal_compliance_review_complete"
        and manual_gate.get("status") == "complete"
    )
    if not manual_gate_complete:
        blockers.append("manual_gate_not_complete")
        if require_complete:
            errors.append("manual_gate legal_compliance_review_complete must be complete.")

    if require_complete or data.get("status") == "approved":
        if data.get("status") != "approved":
            errors.append("status must be approved for legal/compliance completion.")

    blockers = sorted(set(blockers))
    legal_compliance_ready = bool(
        not errors
        and not blockers
        and data.get("status") == "approved"
        and manual_gate_complete
    )
    if require_complete and not legal_compliance_ready:
        errors.append("Legal/compliance evidence is not complete.")

    return {
        "ok": not errors,
        "legal_compliance_ready": legal_compliance_ready,
        "mode": EVIDENCE_MODE,
        "chain_id": data.get("chain_id"),
        "status": data.get("status"),
        "approved_area_count": len(approved_areas),
        "required_area_count": len(REQUIRED_REVIEW_AREAS),
        "verified_artifacts": verified_artifacts,
        "blockers": blockers,
        "manual_gate_status": manual_gate.get("status"),
        "errors": errors,
        "warnings": warnings,
    }


def write_legal_review_workpapers(out_dir):
    review_area_paths = []
    for definition in REQUIRED_REVIEW_AREAS:
        area_id = definition["id"]
        path = Path("legal") / "review_areas" / f"{area_id}.md"
        questions = "\n".join(f"- [ ] {question}" for question in AREA_QUESTIONS.get(area_id, []))
        write_text(out_dir / path, "\n".join([
            f"# SpaceCash Legal/Compliance Review Area: {definition['title']}",
            "",
            f"- Area ID: `{area_id}`",
            "- Status: `not_reviewed`",
            "- Reviewer:",
            "- Reviewed at:",
            "- Decision: `not_reviewed`",
            "",
            "## Review Questions",
            "",
            questions,
            "",
            "## Evidence Reviewed",
            "",
            "- Source hash:",
            "- Release bundle SHA256:",
            "- Policies or artifacts reviewed:",
            "",
            "## Decision Notes",
            "",
            "- Conditions:",
            "- Required disclosure changes:",
            "- Required operational-control changes:",
            "",
        ]))
        review_area_paths.append(path.as_posix())

    document_paths = {}
    for field, (rel, title) in LEGAL_DOCUMENT_WORKPAPERS.items():
        write_text(out_dir / rel, "\n".join([
            f"# SpaceCash {title}",
            "",
            "Draft input for legal/compliance review. This is not approval.",
            "",
            "## Scope",
            "",
            "- Draft statement:",
            "- Reviewer edits required:",
            "",
            "## Approved Text",
            "",
            "",
            "## Operational Notes",
            "",
            "- Owner:",
            "- Evidence path:",
            "- Update hash after final edits:",
            "",
        ]))
        document_paths[field] = rel

    allocation_placeholder_path = DISTRIBUTION_WORKPAPERS["allocation_verifier_output_path"][0]
    write_json(out_dir / allocation_placeholder_path, {
        "mode": "spacecash-allocation-verifier-output-placeholder-v1",
        "status": "placeholder_not_launch_allocation",
        "allocation_hash": genesis_allocation_template().get("allocation_hash"),
        "allocation_ready": False,
        "note": "Replace with approved launch allocation verifier output before legal/compliance completion.",
    })
    write_text(out_dir / DISTRIBUTION_WORKPAPERS["treasury_controls_path"][0], "\n".join([
        "# SpaceCash Treasury Controls",
        "",
        "Draft input for legal/compliance review. This is not approval.",
        "",
        "## Required Controls",
        "",
        "- Treasury owner:",
        "- Approval threshold:",
        "- Movement limits:",
        "- Audit log location:",
        "- Incident procedure:",
        "",
    ]))
    write_text(out_dir / DISTRIBUTION_WORKPAPERS["fee_policy_path"][0], "\n".join([
        "# SpaceCash Fee Policy",
        "",
        "Draft input for legal/compliance review. This is not approval.",
        "",
        "## Fee Rules",
        "",
        "- Fee schedule:",
        "- Burn or treasury treatment:",
        "- Customer disclosure text:",
        "- Change approval process:",
        "",
    ]))

    engagement_letter_path = Path("legal") / "reviewer" / "engagement_letter_template.md"
    write_text(out_dir / engagement_letter_path, "\n".join([
        "# SpaceCash Legal/Compliance Engagement Letter Template",
        "",
        "- Reviewer name:",
        "- Firm:",
        "- Contact:",
        "- Role:",
        "- Reviewed source hash:",
        "- Release bundle SHA256:",
        "- Signed at:",
        "",
        "## Scope Acceptance",
        "",
        "The reviewer accepts the legal/compliance scope in",
        "`docs/spacecash/LEGAL_COMPLIANCE_GATE.md` and the workpapers in this package.",
        "",
        "## Signature",
        "",
        "",
    ]))

    final_decision_path = Path("legal") / "final_decision_template.md"
    write_text(out_dir / final_decision_path, "\n".join([
        "# SpaceCash Legal/Compliance Final Decision Template",
        "",
        "- Decision: `not_reviewed`",
        "- Decided at:",
        "- Reviewer:",
        "- Reviewed source hash:",
        "- Release bundle SHA256:",
        "",
        "## Required Confirmations",
        "",
        "- [ ] No investment claims confirmed.",
        "- [ ] No legal tender claims confirmed.",
        "- [ ] No exchange-listing claims confirmed.",
        "- [ ] Real-money use authorized by reviewer.",
        "",
        "## Conditions",
        "",
        "- None recorded yet.",
        "",
        "## Required Gate Note",
        "",
        "Do not mark `legal_compliance_review_complete` complete until the final",
        "legal/compliance evidence JSON passes `--require-complete` and the manual gate",
        "is explicitly approved.",
        "",
    ]))

    return {
        "review_area_workpapers": review_area_paths,
        "document_workpapers": document_paths,
        "distribution_workpapers": {field: rel for field, (rel, _title) in DISTRIBUTION_WORKPAPERS.items()},
        "engagement_letter_template": engagement_letter_path.as_posix(),
        "final_decision_template": final_decision_path.as_posix(),
    }


def write_legal_compliance_evidence_workbench(out_dir, workpapers, reviewed_source_hash="", release_bundle_sha256=""):
    payload = legal_compliance_evidence_template()
    payload["status"] = "not_started"
    payload["reviewed_source_hash"] = reviewed_source_hash or ""
    payload["release_bundle_sha256"] = release_bundle_sha256 or ""
    payload["reviewer"]["engagement_letter_path"] = workpapers["engagement_letter_template"]
    payload["reviewer"]["engagement_letter_sha256"] = _hash_relative(out_dir, workpapers["engagement_letter_template"])
    payload["scope"]["intended_use_cases"] = [
        "Draft for reviewer confirmation: closed-loop SpaceCash product payments after approval.",
    ]
    payload["scope"]["prohibited_use_cases"] = [
        "investment marketing",
        "legal tender claims",
        "exchange listing claims",
        "restricted-product transactions without approved controls",
    ]

    area_paths = {Path(path).stem: path for path in workpapers.get("review_area_workpapers", [])}
    for area in payload["review_areas"]:
        area["evidence"] = area_paths.get(area["id"], "")

    for field, rel in workpapers.get("document_workpapers", {}).items():
        payload["documents"][field] = rel
        hash_field = DOCUMENT_HASH_FIELDS.get(field)
        if hash_field:
            payload["documents"][hash_field] = _hash_relative(out_dir, rel)

    payload["distribution"]["genesis_allocation_hash"] = genesis_allocation_template().get("allocation_hash")
    for field, rel in workpapers.get("distribution_workpapers", {}).items():
        payload["distribution"][field] = rel
        hash_field = DISTRIBUTION_HASH_FIELDS.get(field)
        if hash_field:
            payload["distribution"][hash_field] = _hash_relative(out_dir, rel)

    payload["final_decision"]["reviewer_statement"] = f"Use {workpapers['final_decision_template']} for final reviewer decision."
    write_json(out_dir / "legal_compliance_evidence_workbench.json", payload)
    return payload


def write_workbench_readme(out_dir, summary):
    write_text(out_dir / "README.md", "\n".join([
        "# SpaceCash Legal/Compliance Workbench",
        "",
        "This package prepares legal/compliance review evidence. It is not legal advice or approval.",
        "",
        f"- Chain: `{summary['chain_id']}`",
        f"- Source hash: `{summary['reviewed_source_hash'] or 'not set'}`",
        f"- Release bundle SHA256: `{summary['release_bundle_sha256'] or 'not set'}`",
        f"- Legal/compliance ready: `{summary['legal_compliance_ready']}`",
        f"- Review areas: `{summary['review_area_count']}`",
        f"- Manual gate: `{summary['manual_gate']['status']}`",
        "",
        "Reviewer order:",
        "",
        "1. Verify `SHA256SUMS.txt`.",
        "2. Review `legal_compliance_evidence_workbench.json` and `legal_compliance_evidence_workbench_check.json`.",
        "3. Fill `legal/reviewer/engagement_letter_template.md` with the actual reviewer details.",
        "4. Complete every `legal/review_areas/*.md` workpaper.",
        "5. Finalize the documents under `legal/documents/` and update their hashes in the evidence JSON.",
        "6. Replace the allocation placeholder with approved launch allocation verifier output.",
        "7. Fill `legal/final_decision_template.md` and then complete the final evidence JSON.",
        "8. Do not mark `legal_compliance_review_complete` complete until `--require-complete` passes.",
        "",
    ]))


def write_checksums(out_dir):
    artifact_paths = sorted(
        path for path in out_dir.rglob("*")
        if path.is_file() and path.name != "SHA256SUMS.txt"
    )
    lines = []
    files = []
    for path in artifact_paths:
        digest = file_hash(path)
        rel = path.relative_to(out_dir).as_posix()
        lines.append(f"{digest}  {rel}")
        files.append({"path": rel, "bytes": path.stat().st_size, "sha256": digest})
    sums = out_dir / "SHA256SUMS.txt"
    sums.write_text("\n".join(lines) + "\n", encoding="utf-8")
    files.append({"path": "SHA256SUMS.txt", "bytes": sums.stat().st_size, "sha256": file_hash(sums)})
    return files


def build_legal_compliance_workbench(out_dir=None, reviewed_source_hash="", release_bundle_sha256="", force=False):
    out_dir = Path(out_dir or default_workbench_dir())
    if out_dir.exists():
        if not force:
            raise ValueError(f"Legal/compliance workbench already exists: {out_dir}")
        safe_reset_dir(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    workpapers = write_legal_review_workpapers(out_dir)
    evidence = write_legal_compliance_evidence_workbench(
        out_dir,
        workpapers,
        reviewed_source_hash=reviewed_source_hash,
        release_bundle_sha256=release_bundle_sha256,
    )
    check = validate_legal_compliance_evidence(evidence)
    write_json(out_dir / "legal_compliance_evidence_workbench_check.json", check)

    summary = {
        "ok": bool(check.get("ok") and not check.get("legal_compliance_ready")),
        "mode": "spacecash-legal-compliance-workbench-v1",
        "generated_at": protocol.utc_now(),
        "chain_id": protocol.CHAIN_ID,
        "out_dir": str(out_dir.resolve()),
        "reviewed_source_hash": evidence.get("reviewed_source_hash"),
        "release_bundle_sha256": evidence.get("release_bundle_sha256"),
        "legal_compliance_ready": check.get("legal_compliance_ready"),
        "approved_area_count": check.get("approved_area_count"),
        "required_area_count": check.get("required_area_count"),
        "review_area_count": len(workpapers.get("review_area_workpapers") or []),
        "blockers": check.get("blockers") or [],
        "review_workpapers": workpapers,
        "required_outputs": [
            "signed reviewer engagement",
            "approved use case",
            "prohibited use cases",
            "required disclosures",
            "terms of service",
            "privacy policy",
            "refund policy",
            "restricted product policy",
            "tax position",
            "approved launch allocation verifier output",
            "treasury controls",
            "final legal/compliance decision",
        ],
        "manual_gate": {
            "id": "legal_compliance_review_complete",
            "status": "not_complete",
            "reason": "Legal/compliance review and final launch authorization are still required.",
        },
    }
    write_json(out_dir / "legal_compliance_workbench_summary.json", summary)
    write_workbench_readme(out_dir, summary)
    files = write_checksums(out_dir)
    result = dict(summary)
    result["files"] = files
    return result


def write_legal_compliance_evidence_template(out_path=None):
    payload = legal_compliance_evidence_template()
    if out_path:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def load_legal_compliance_evidence(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_parser():
    parser = argparse.ArgumentParser(description="Create or verify SpaceCash legal/compliance review evidence")
    parser.add_argument("--template-out", type=Path, help="Optional path to write the legal/compliance evidence template")
    parser.add_argument("--verify", type=Path, help="Legal/compliance evidence JSON file to verify")
    parser.add_argument("--require-complete", action="store_true", help="Fail unless the legal/compliance gate is complete")
    parser.add_argument("--workbench-out-dir", type=Path, help="Write a legal/compliance review workbench packet")
    parser.add_argument("--reviewed-source-hash", default="", help="Optional reviewed source hash to seed into the workbench")
    parser.add_argument("--release-bundle-sha256", default="", help="Optional release bundle SHA-256 to seed into the workbench")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing workbench directory under _tmp")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.verify:
        result = validate_legal_compliance_evidence(
            load_legal_compliance_evidence(args.verify),
            require_complete=args.require_complete,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("ok") and (not args.require_complete or result.get("legal_compliance_ready")) else 2
    if args.workbench_out_dir:
        try:
            result = build_legal_compliance_workbench(
                out_dir=args.workbench_out_dir,
                reviewed_source_hash=args.reviewed_source_hash,
                release_bundle_sha256=args.release_bundle_sha256,
                force=args.force,
            )
        except ValueError as exc:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("ok") else 2
    payload = write_legal_compliance_evidence_template(args.template_out)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
