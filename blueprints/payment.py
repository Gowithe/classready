# ==============================================================================
# FILE: blueprints/payment.py
# Payment blueprint – pricing page, PromptPay QR generation, EasySlip
# verification, payment flow, and user limits API
# ==============================================================================

import os
import re
import json
import base64
import secrets
import urllib.parse
from typing import Optional

import requests as http_requests   # avoid shadowing flask.request
from flask import (
    Blueprint, request, session, jsonify, redirect, url_for,
    render_template, abort, flash, current_app,
)

from models import (
    SubscriptionPlan, UserSubscription, PaymentTransaction,
    UsageLimits, get_db,
)
from blueprints.helpers import login_required, is_premium_user

payment_bp = Blueprint("payment", __name__)


# ---------------------------------------------------------------------------
# Config (from environment)
# ---------------------------------------------------------------------------
PROMPTPAY_ID = os.environ.get("PROMPTPAY_ID", "1234567890123")
PROMPTPAY_NAME = os.environ.get("PROMPTPAY_NAME", "\u0e0a\u0e37\u0e48\u0e2d\u0e1a\u0e31\u0e0d\u0e0a\u0e35")
EASYSLIP_API_KEY = os.environ.get("EASYSLIP_API_KEY", "your_api_key")


# ==============================================================================
# PromptPay QR Generation
# ==============================================================================
def _crc16_ccitt(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
            crc &= 0xFFFF
    return crc


def generate_promptpay_qr_payload(promptpay_id: str, amount: float) -> str:
    promptpay_id = promptpay_id.replace("-", "").replace(" ", "")

    def tlv(tag: str, value: str) -> str:
        return f"{tag}{len(value):02d}{value}"

    if len(promptpay_id) == 10:
        formatted_id = "0066" + promptpay_id[1:]
        id_tag = "01"
    elif len(promptpay_id) == 13:
        formatted_id = promptpay_id
        id_tag = "02"
    else:
        raise ValueError("Invalid PromptPay ID")

    aid = tlv("00", "A000000677010111")
    mobile_or_id = tlv(id_tag, formatted_id)
    merchant_info = tlv("29", aid + mobile_or_id)

    payload = ""
    payload += tlv("00", "01")
    payload += tlv("01", "12")
    payload += merchant_info
    payload += tlv("52", "0000")
    payload += tlv("53", "764")
    payload += tlv("54", f"{amount:.2f}")
    payload += tlv("58", "TH")
    payload += "6304"

    crc = _crc16_ccitt(payload.encode("utf-8"))
    payload = payload[:-4] + f"6304{crc:04X}"
    return payload


def get_promptpay_qr_image_url(promptpay_id: str, amount: float, size: int = 300) -> str:
    payload = generate_promptpay_qr_payload(promptpay_id, amount)
    encoded = urllib.parse.quote(payload)
    return f"https://api.qrserver.com/v1/create-qr-code/?size={size}x{size}&data={encoded}"


# ==============================================================================
# EasySlip Verification
# ==============================================================================
def verify_slip_with_easyslip(image_base64: str, api_key: str) -> dict:
    try:
        response = http_requests.post(
            "https://developer.easyslip.com/api/v1/verify",
            json={"image": image_base64, "checkDuplicate": True},
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        try:
            result = response.json()
        except Exception:
            result = {}

        if response.status_code == 200 and result.get("status") == 200:
            return {
                "success": True,
                "data": result.get("data", {}) or {},
                "error": None,
                "status": result.get("status", 200),
            }

        return {
            "success": False,
            "data": result.get("data"),
            "error": result.get("message", f"HTTP {response.status_code}"),
            "status": result.get("status", response.status_code),
        }
    except http_requests.Timeout:
        return {"success": False, "data": None, "error": "Request timeout", "status": None}
    except Exception as e:
        return {"success": False, "data": None, "error": str(e), "status": None}


# ==============================================================================
# Slip Validation Helpers
# ==============================================================================
def validate_slip_amount(slip_data: dict, expected_amount: float, tolerance: float = 0.0) -> dict:
    try:
        slip_amount = float(slip_data.get("amount", {}).get("amount", 0))
    except Exception:
        slip_amount = 0.0
    is_valid = slip_amount >= (expected_amount - tolerance)
    return {
        "valid": is_valid,
        "slip_amount": slip_amount,
        "expected_amount": expected_amount,
        "difference": slip_amount - expected_amount,
        "error": None if is_valid else f"\u0e08\u0e33\u0e19\u0e27\u0e19\u0e40\u0e07\u0e34\u0e19\u0e44\u0e21\u0e48\u0e15\u0e23\u0e07 (\u0e42\u0e2d\u0e19 {slip_amount:.2f} / \u0e15\u0e49\u0e2d\u0e07\u0e01\u0e32\u0e23 {expected_amount:.2f} \u0e1a\u0e32\u0e17)",
    }


def _normalize_name(s: str) -> str:
    s = (s or "").strip().lower()
    return re.sub(r"[\s\-\._,:\'\"\(\)\[\]\{\}]", "", s)


def _extract_slip_trans_ref(slip_data: dict) -> str:
    if not isinstance(slip_data, dict):
        return ""
    for k in ("transRef", "trans_ref", "transactionRef", "transaction_ref", "reference", "ref"):
        v = slip_data.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    for path in (
        ("data", "transRef"),
        ("data", "transactionRef"),
        ("transaction", "transRef"),
        ("transaction", "transactionRef"),
    ):
        cur = slip_data
        ok = True
        for p in path:
            if isinstance(cur, dict) and p in cur:
                cur = cur[p]
            else:
                ok = False
                break
        if ok and isinstance(cur, str) and cur.strip():
            return cur.strip()
    return ""


def _extract_receiver_info(slip_data: dict) -> tuple:
    if not isinstance(slip_data, dict):
        return ("", "")

    def _get(obj, *path, default=None):
        cur = obj
        for p in path:
            if isinstance(cur, dict) and p in cur:
                cur = cur[p]
            else:
                return default
        return cur

    receiver = None
    if isinstance(slip_data.get("receiver"), dict):
        receiver = slip_data.get("receiver")
    elif isinstance(slip_data.get("data"), dict) and isinstance(slip_data["data"].get("receiver"), dict):
        receiver = slip_data["data"].get("receiver")

    if receiver is None:
        for k in ("to", "creditor"):
            if isinstance(slip_data.get(k), dict):
                receiver = slip_data.get(k)
                break
        if receiver is None and isinstance(slip_data.get("data"), dict):
            for k in ("to", "creditor"):
                if isinstance(slip_data["data"].get(k), dict):
                    receiver = slip_data["data"].get(k)
                    break

    recv_name = ""
    recv_id = ""

    if isinstance(receiver, dict):
        th = _get(receiver, "account", "name", "th")
        en = _get(receiver, "account", "name", "en")
        for v in (th, en):
            if isinstance(v, str) and v.strip():
                recv_name = v.strip()
                break

        proxy_acc = _get(receiver, "account", "proxy", "account")
        bank_acc = _get(receiver, "account", "bank", "account")
        for v in (proxy_acc, bank_acc):
            if isinstance(v, str) and v.strip():
                recv_id = v.strip()
                break

        if not recv_name:
            for nk in ("name", "accountName", "displayName"):
                v = receiver.get(nk)
                if isinstance(v, str) and v.strip():
                    recv_name = v.strip()
                    break
        if not recv_id:
            for ik in ("id", "account", "accountNo", "promptpay", "promptpayId"):
                v = receiver.get(ik)
                if isinstance(v, str) and v.strip():
                    recv_id = v.strip()
                    break

    if not recv_name:
        for nk in ("receiverName", "toName"):
            v = slip_data.get(nk)
            if isinstance(v, str) and v.strip():
                recv_name = v.strip()
                break
        if not recv_name and isinstance(slip_data.get("data"), dict):
            for nk in ("receiverName", "toName"):
                v = slip_data["data"].get(nk)
                if isinstance(v, str) and v.strip():
                    recv_name = v.strip()
                    break

    if not recv_id:
        for ik in ("receiverId", "toId", "promptpay"):
            v = slip_data.get(ik)
            if isinstance(v, str) and v.strip():
                recv_id = v.strip()
                break
        if not recv_id and isinstance(slip_data.get("data"), dict):
            for ik in ("receiverId", "toId", "promptpay"):
                v = slip_data["data"].get(ik)
                if isinstance(v, str) and v.strip():
                    recv_id = v.strip()
                    break

    return (recv_name, recv_id)


def _masked_id_match(expected_promptpay: str, got_masked: str) -> bool:
    exp = re.sub(r"\D", "", expected_promptpay or "")
    got = (got_masked or "").strip()
    if not exp or not got:
        return False
    got_clean = re.sub(r"[^0-9xX\*]", "", got)
    got_clean = got_clean.replace("*", "x").replace("X", "x")
    if "x" not in got_clean:
        return re.sub(r"\D", "", got_clean) == exp
    prefix = re.match(r"^\d+", got_clean)
    suffix = re.search(r"\d+$", got_clean)
    pre = prefix.group(0) if prefix else ""
    suf = suffix.group(0) if suffix else ""
    if pre and not exp.startswith(pre):
        return False
    if suf and not exp.endswith(suf):
        return False
    return True


def validate_slip_receiver(slip_data: dict, expected_name: str, expected_promptpay: str) -> dict:
    recv_name, recv_id = _extract_receiver_info(slip_data)

    aliases = [x.strip() for x in (os.environ.get("PROMPTPAY_NAME_ALIASES", "")).split("|") if x.strip()]
    candidates = [expected_name] + aliases if expected_name else aliases

    rn = _normalize_name(recv_name)
    name_ok = False
    for cand in candidates:
        en = _normalize_name(cand)
        if en and rn and (en in rn or rn in en):
            name_ok = True
            break
    if not candidates:
        name_ok = True

    exp_digits = re.sub(r"\D", "", expected_promptpay or "")
    got_raw = (recv_id or "").strip()
    id_ok = True
    if exp_digits:
        if not got_raw:
            id_ok = False
        else:
            if any(ch in got_raw for ch in ("x", "X", "*")):
                id_ok = _masked_id_match(exp_digits, got_raw)
            else:
                id_ok = re.sub(r"\D", "", got_raw) == exp_digits

    # ✅ FIX: avoid unicode escapes inside f-string {...}
    if not name_ok:
        display_name = recv_name or "ไม่พบชื่อผู้รับ"
        return {"valid": False, "error": f"ชื่อผู้รับไม่ตรง (ในสลิป: {display_name})"}
    if not id_ok:
        display_id = recv_id or "ไม่พบเลขผู้รับ"
        return {"valid": False, "error": f"PromptPay/บัญชีผู้รับไม่ตรง (ในสลิป: {display_id})"}

    return {"valid": True, "error": None}


# ---------------------------------------------------------------------------
# DB schema migration for anti-duplicate columns
# ---------------------------------------------------------------------------
def _ensure_payment_schema() -> None:
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='payment_transactions'")
        if not c.fetchone():
            conn.close()
            return
        c.execute("PRAGMA table_info(payment_transactions)")
        cols = {row[1] for row in c.fetchall()}
        if "slip_trans_ref" not in cols:
            c.execute("ALTER TABLE payment_transactions ADD COLUMN slip_trans_ref TEXT")
        if "receiver_name" not in cols:
            c.execute("ALTER TABLE payment_transactions ADD COLUMN receiver_name TEXT")
        if "receiver_id" not in cols:
            c.execute("ALTER TABLE payment_transactions ADD COLUMN receiver_id TEXT")
        try:
            c.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS uq_payment_slip_trans_ref
                ON payment_transactions(slip_trans_ref)
                WHERE slip_trans_ref IS NOT NULL AND slip_trans_ref <> ''
            """)
        except Exception:
            pass
        conn.commit()
        conn.close()
    except Exception:
        pass


def _slip_trans_ref_used(trans_ref: str, exclude_txn_id: Optional[int] = None) -> bool:
    if not trans_ref:
        return False
    _ensure_payment_schema()
    conn = get_db()
    c = conn.cursor()
    if exclude_txn_id is None:
        c.execute("SELECT id FROM payment_transactions WHERE slip_trans_ref = ? LIMIT 1", (trans_ref,))
    else:
        c.execute("SELECT id FROM payment_transactions WHERE slip_trans_ref = ? AND id <> ? LIMIT 1", (trans_ref, exclude_txn_id))
    row = c.fetchone()
    conn.close()
    return row is not None


# ==============================================================================
# Pricing Page
# ==============================================================================
@payment_bp.route("/pricing")
def pricing():
    plans = SubscriptionPlan.get_all_active()
    user_id = session.get("user_id")
    is_premium = False
    current_sub = None
    stats = {"topic_count": 0, "classroom_count": 0, "ai_generate_count": 0}

    if user_id:
        is_premium = is_premium_user(user_id)
        current_sub = UserSubscription.get_active_subscription(user_id)
        try:
            stats = UsageLimits.get_user_stats(user_id)
        except Exception:
            pass

    return render_template(
        "pricing.html",
        plans=plans,
        is_premium=is_premium,
        current_sub=current_sub,
        stats=stats,
        free_limits={
            "topics": getattr(UsageLimits, "FREE_TOPICS", 5),
            "classrooms": getattr(UsageLimits, "FREE_CLASSROOMS", 2),
            "ai_generate": getattr(UsageLimits, "FREE_AI_GENERATE_PER_MONTH", 3),
        },
    )


@payment_bp.route("/api/user/limits")
@login_required
def api_user_limits():
    user_id = session["user_id"]
    is_prem = is_premium_user(user_id)
    stats = UsageLimits.get_user_stats(user_id)
    return jsonify({
        "ok": True,
        "is_premium": is_prem,
        "stats": stats,
        "limits": {
            "topics": -1 if is_prem else UsageLimits.FREE_TOPICS,
            "classrooms": -1 if is_prem else UsageLimits.FREE_CLASSROOMS,
            "ai_generate": -1 if is_prem else UsageLimits.FREE_AI_GENERATE_PER_MONTH,
        },
        "can_create_topic": UsageLimits.can_create_topic(user_id, is_prem)[0],
        "can_create_classroom": UsageLimits.can_create_classroom(user_id, is_prem)[0],
        "can_ai_generate": UsageLimits.can_ai_generate(user_id, is_prem)[0],
    })


# ==============================================================================
# Payment Flow
# ==============================================================================
@payment_bp.route("/payment/create/<int:plan_id>", methods=["POST"])
@login_required
def payment_create(plan_id):
    user_id = session["user_id"]
    if is_premium_user(user_id):
        return jsonify({"ok": False, "error": "\u0e04\u0e38\u0e13\u0e40\u0e1b\u0e47\u0e19 Premium \u0e2d\u0e22\u0e39\u0e48\u0e41\u0e25\u0e49\u0e27"}), 400
    plan = SubscriptionPlan.get_by_id(plan_id)
    if not plan:
        return jsonify({"ok": False, "error": "\u0e44\u0e21\u0e48\u0e1e\u0e1a\u0e41\u0e1e\u0e47\u0e04\u0e40\u0e01\u0e08"}), 404
    pending = PaymentTransaction.get_pending_by_user(user_id, plan_id)
    if pending:
        return jsonify({"ok": True, "redirect": url_for("payment.payment_page", ref_code=pending["reference_code"])})
    txn = PaymentTransaction.create(user_id=user_id, plan_id=plan_id, amount=plan["price"])
    return jsonify({"ok": True, "redirect": url_for("payment.payment_page", ref_code=txn["reference_code"])})


@payment_bp.route("/payment/<ref_code>")
@login_required
def payment_page(ref_code):
    txn = PaymentTransaction.get_by_reference(ref_code)
    if not txn:
        flash("\u0e44\u0e21\u0e48\u0e1e\u0e1a\u0e23\u0e32\u0e22\u0e01\u0e32\u0e23\u0e0a\u0e33\u0e23\u0e30\u0e40\u0e07\u0e34\u0e19", "error")
        return redirect(url_for("payment.pricing"))
    if txn["user_id"] != session["user_id"]:
        abort(403)
    if txn["status"] == "completed":
        flash("\u0e0a\u0e33\u0e23\u0e30\u0e40\u0e07\u0e34\u0e19\u0e40\u0e23\u0e35\u0e22\u0e1a\u0e23\u0e49\u0e2d\u0e22\u0e41\u0e25\u0e49\u0e27!", "success")
        # ✅ FIX: dashboard is a plain app route -> endpoint is "dashboard"
        return redirect(url_for("dashboard"))
    qr_url = get_promptpay_qr_image_url(PROMPTPAY_ID, txn["amount"])
    return render_template(
        "payment.html",
        txn=txn,
        qr_url=qr_url,
        promptpay_id=PROMPTPAY_ID,
        promptpay_name=PROMPTPAY_NAME,
    )


@payment_bp.route("/payment/<ref_code>/verify", methods=["POST"])
@login_required
def payment_verify(ref_code):
    txn = PaymentTransaction.get_by_reference(ref_code)
    if not txn:
        return jsonify({"ok": False, "error": "\u0e44\u0e21\u0e48\u0e1e\u0e1a\u0e23\u0e32\u0e22\u0e01\u0e32\u0e23"}), 404
    if txn["user_id"] != session["user_id"]:
        return jsonify({"ok": False, "error": "\u0e44\u0e21\u0e48\u0e21\u0e35\u0e2a\u0e34\u0e17\u0e18\u0e34\u0e4c"}), 403
    if txn["status"] == "completed":
        return jsonify({"ok": False, "error": "\u0e0a\u0e33\u0e23\u0e30\u0e40\u0e07\u0e34\u0e19\u0e40\u0e23\u0e35\u0e22\u0e1a\u0e23\u0e49\u0e2d\u0e22\u0e41\u0e25\u0e49\u0e27"}), 400

    if "slip" not in request.files:
        return jsonify({"ok": False, "error": "\u0e01\u0e23\u0e38\u0e13\u0e32\u0e2d\u0e31\u0e1b\u0e42\u0e2b\u0e25\u0e14\u0e2a\u0e25\u0e34\u0e1b"}), 400
    slip_file = request.files["slip"]
    if not slip_file or not slip_file.filename:
        return jsonify({"ok": False, "error": "\u0e01\u0e23\u0e38\u0e13\u0e32\u0e40\u0e25\u0e37\u0e2d\u0e01\u0e44\u0e1f\u0e25\u0e4c"}), 400

    slip_bytes = slip_file.read()
    slip_base64 = base64.b64encode(slip_bytes).decode("utf-8")

    # Save slip file
    slip_filename = f"slip_{ref_code}_{secrets.token_hex(4)}.jpg"
    slip_path = os.path.join(current_app.config["UPLOAD_FOLDER"], slip_filename)
    with open(slip_path, "wb") as f:
        f.write(slip_bytes)

    PaymentTransaction.update_status(txn["id"], "verifying", slip_image=slip_filename)

    # Verify with EasySlip
    easyslip_result = verify_slip_with_easyslip(slip_base64, EASYSLIP_API_KEY)

    if not easyslip_result.get("success"):
        slip_data = easyslip_result.get("data") or {}
        _ensure_payment_schema()
        trans_ref = _extract_slip_trans_ref(slip_data) if isinstance(slip_data, dict) else ""
        try:
            err_payload = {"error": easyslip_result.get("error")}
            if trans_ref:
                err_payload["transRef"] = trans_ref
            PaymentTransaction.update_status(txn["id"], "failed", easyslip_data=json.dumps(err_payload))
            if trans_ref:
                conn = get_db()
                c = conn.cursor()
                c.execute("UPDATE payment_transactions SET slip_trans_ref = COALESCE(?, slip_trans_ref) WHERE id = ?", (trans_ref, txn["id"]))
                conn.commit()
                conn.close()
        except Exception:
            pass

        if (easyslip_result.get("error") or "").strip() == "duplicate_slip":
            return jsonify({"ok": False, "error": "\u0e2a\u0e25\u0e34\u0e1b\u0e19\u0e35\u0e49\u0e16\u0e39\u0e01\u0e43\u0e0a\u0e49\u0e44\u0e1b\u0e41\u0e25\u0e49\u0e27 (duplicate slip)"}), 400
        return jsonify({"ok": False, "error": f"\u0e44\u0e21\u0e48\u0e2a\u0e32\u0e21\u0e32\u0e23\u0e16\u0e15\u0e23\u0e27\u0e08\u0e2a\u0e2d\u0e1a\u0e2a\u0e25\u0e34\u0e1b\u0e44\u0e14\u0e49: {easyslip_result.get('error')}"}), 400

    slip_data = easyslip_result["data"]

    # Anti-duplicate: check transRef
    _ensure_payment_schema()
    trans_ref = _extract_slip_trans_ref(slip_data)
    if trans_ref and _slip_trans_ref_used(trans_ref, exclude_txn_id=txn["id"]):
        PaymentTransaction.update_status(txn["id"], "failed", easyslip_data=json.dumps({"error": "duplicate_slip", "transRef": trans_ref}))
        return jsonify({"ok": False, "error": "\u0e2a\u0e25\u0e34\u0e1b\u0e19\u0e35\u0e49\u0e16\u0e39\u0e01\u0e43\u0e0a\u0e49\u0e41\u0e25\u0e49\u0e27 (\u0e2b\u0e49\u0e32\u0e21\u0e43\u0e0a\u0e49\u0e2a\u0e25\u0e34\u0e1b\u0e0b\u0e49\u0e33)"}), 400

    # Check receiver name + PromptPay ID
    recv_check = validate_slip_receiver(slip_data, PROMPTPAY_NAME, PROMPTPAY_ID)
    if not recv_check["valid"]:
        PaymentTransaction.update_status(txn["id"], "failed", easyslip_data=json.dumps({"error": recv_check["error"], "transRef": trans_ref}))
        return jsonify({"ok": False, "error": recv_check["error"]}), 400

    # Check amount
    validation = validate_slip_amount(slip_data, txn["amount"])
    PaymentTransaction.update_status(
        txn["id"],
        "completed" if validation["valid"] else "failed",
        easyslip_data=json.dumps(slip_data),
    )

    if not validation["valid"]:
        return jsonify({"ok": False, "error": validation["error"]}), 400

    # Success – create subscription
    plan = SubscriptionPlan.get_by_id(txn["plan_id"])
    UserSubscription.create(
        user_id=txn["user_id"],
        plan_id=txn["plan_id"],
        duration_days=plan["duration_days"],
        payment_ref=ref_code,
    )

    return jsonify({
        "ok": True,
        "message": "\U0001f389 \u0e0a\u0e33\u0e23\u0e30\u0e40\u0e07\u0e34\u0e19\u0e2a\u0e33\u0e40\u0e23\u0e47\u0e08! \u0e04\u0e38\u0e13\u0e40\u0e1b\u0e47\u0e19 Premium \u0e41\u0e25\u0e49\u0e27",
        # ✅ FIX: dashboard is a plain app route -> endpoint is "dashboard"
        "redirect": url_for("dashboard"),
    })
