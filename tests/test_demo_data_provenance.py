"""Offline reproducibility contract for the committed public demo assets."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from app import product_api


_ROOT = Path(__file__).parent.parent
_PUBLIC_DIR = _ROOT / "sample_data" / "public"
_CSV_PATH = _PUBLIC_DIR / "ibm_telco_customer_churn.csv"
_CONTEXT_PATH = _PUBLIC_DIR / "ibm_telco_customer_churn_context.json"
_DATA_README_PATH = _PUBLIC_DIR / "README.md"
_UPSTREAM_LICENSE_PATH = _PUBLIC_DIR / "LICENSE-IBM-APACHE-2.0.txt"
_THIRD_PARTY_NOTICE_PATH = _ROOT / "THIRD_PARTY_NOTICES.md"
_EXPECTED_CSV_SHA256 = (
    "16320c9c1ec72448db59aa0a26a0b95401046bef5d02fd3aeb906448e3055e91"
)
_EXPECTED_HEADER = (
    "customerID",
    "gender",
    "SeniorCitizen",
    "Partner",
    "Dependents",
    "tenure",
    "PhoneService",
    "MultipleLines",
    "InternetService",
    "OnlineSecurity",
    "OnlineBackup",
    "DeviceProtection",
    "TechSupport",
    "StreamingTV",
    "StreamingMovies",
    "Contract",
    "PaperlessBilling",
    "PaymentMethod",
    "MonthlyCharges",
    "TotalCharges",
    "Churn",
)
_EXPECTED_CONTEXT_FIELDS = {
    "dataset_context",
    "business_question",
    "decision_goal",
    "strategy_profile",
    "user_assumption",
}


def test_committed_demo_data_contract_is_complete_and_offline() -> None:
    """The fresh-clone product assets retain their exact structural contract."""
    assert _CSV_PATH.is_file()
    assert _CONTEXT_PATH.is_file()
    assert _DATA_README_PATH.is_file()
    assert _UPSTREAM_LICENSE_PATH.is_file()
    assert _THIRD_PARTY_NOTICE_PATH.is_file()
    assert hashlib.sha256(_CSV_PATH.read_bytes()).hexdigest() == _EXPECTED_CSV_SHA256

    with _CSV_PATH.open("r", encoding="utf-8-sig", newline="") as csv_file:
        rows = list(csv.reader(csv_file))

    assert tuple(rows[0]) == _EXPECTED_HEADER
    assert len(rows) - 1 == 7043
    assert all(len(row) == 21 for row in rows)
    customer_ids = [row[0] for row in rows[1:]]
    assert all(customer_ids)
    assert len(customer_ids) == len(set(customer_ids))

    context = json.loads(_CONTEXT_PATH.read_text(encoding="utf-8"))
    assert set(context) == _EXPECTED_CONTEXT_FIELDS
    assert all(
        isinstance(context[field], str) and context[field].strip()
        for field in _EXPECTED_CONTEXT_FIELDS
    )

    assert product_api._PUBLIC_CSV.resolve() == _CSV_PATH.resolve()
    assert product_api._PUBLIC_CONTEXT.resolve() == _CONTEXT_PATH.resolve()
    assert product_api._BUSINESS_PROFILE_ID == "ibm_telco_churn_v1"
