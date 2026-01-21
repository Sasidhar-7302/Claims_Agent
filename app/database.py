"""
Database module for persistent claim storage.

Uses SQLite for lightweight, file-based persistence.
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

BASE_DIR = Path(__file__).parent.parent
DB_PATH = BASE_DIR / "outbox" / "claims.db"


def get_connection():
    """Get a database connection."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def ensure_columns(cursor, columns: Dict[str, str]) -> None:
    """Ensure required columns exist on the claims table."""
    cursor.execute("PRAGMA table_info(claims)")
    existing = {row["name"] for row in cursor.fetchall()}
    for name, col_type in columns.items():
        if name not in existing:
            cursor.execute(f"ALTER TABLE claims ADD COLUMN {name} {col_type}")


def init_db():
    """Initialize the database tables."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS claims (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email_id TEXT UNIQUE NOT NULL,
            claim_id TEXT,
            decision TEXT,
            timestamp TEXT,
            
            -- Customer Info
            customer_name TEXT,
            customer_email TEXT,
            customer_address TEXT,
            
            -- Product Info
            product_name TEXT,
            product_id TEXT,
            product_serial TEXT,
            purchase_date TEXT,
            
            -- Issue
            issue_description TEXT,
            
            -- Analysis
            recommendation TEXT,
            confidence REAL,
            reasoning TEXT,
            warranty_valid INTEGER,
            warranty_details TEXT,
            exclusions TEXT,
            facts TEXT,
            assumptions TEXT,
            policy_references TEXT,

            -- Policy metadata
            policy_id TEXT,
            policy_version TEXT,
            policy_effective_date TEXT,
            policy_file TEXT,
            policy_retrieval TEXT,

            -- Model metadata
            llm_model TEXT,
            
            -- Outputs
            email_draft TEXT,
            email_path TEXT,
            label_path TEXT,
            packet_path TEXT,
            
            -- Metadata
            reviewer TEXT,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            
            -- Full state JSON for complete data
            full_state TEXT
        )
    """)

    ensure_columns(cursor, {
        "product_id": "TEXT",
        "policy_id": "TEXT",
        "policy_version": "TEXT",
        "policy_effective_date": "TEXT",
        "policy_file": "TEXT",
        "policy_retrieval": "TEXT",
        "llm_model": "TEXT"
    })
    
    conn.commit()
    conn.close()


def save_claim(state: Dict[str, Any], decision: str, notes: str = "") -> bool:
    """Save a processed claim to the database."""
    try:
        init_db()
        conn = get_connection()
        cursor = conn.cursor()
        
        extracted = state.get("extracted_fields", {})
        analysis = state.get("analysis", {})
        
        cursor.execute("""
            INSERT OR REPLACE INTO claims (
                email_id, claim_id, decision, timestamp,
                customer_name, customer_email, customer_address,
                product_name, product_id, product_serial, purchase_date,
                issue_description,
                recommendation, confidence, reasoning, warranty_valid, warranty_details,
                exclusions, facts, assumptions, policy_references,
                policy_id, policy_version, policy_effective_date, policy_file, policy_retrieval,
                llm_model,
                email_draft, email_path, label_path, packet_path,
                reviewer, notes, full_state
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            state.get("email_id", ""),
            state.get("claim_id", ""),
            decision,
            datetime.now().isoformat(),
            extracted.get("customer_name", ""),
            extracted.get("customer_email", ""),
            extracted.get("customer_address", ""),
            state.get("product_name", ""),
            state.get("product_id", ""),
            extracted.get("product_serial", ""),
            extracted.get("purchase_date", ""),
            extracted.get("issue_description", ""),
            analysis.get("recommendation", ""),
            analysis.get("confidence", 0),
            analysis.get("reasoning", ""),
            1 if analysis.get("warranty_window_valid") else 0,
            analysis.get("warranty_window_details", ""),
            json.dumps(analysis.get("exclusions_triggered", [])),
            json.dumps(analysis.get("facts", [])),
            json.dumps(analysis.get("assumptions", [])),
            json.dumps(analysis.get("policy_references", [])),
            state.get("policy_id", ""),
            state.get("policy_version", ""),
            state.get("policy_effective_date", ""),
            state.get("policy_file", ""),
            json.dumps(state.get("policy_retrieval", {})),
            state.get("llm_model", ""),
            state.get("customer_email_draft", ""),
            state.get("customer_email_path", ""),
            state.get("return_label_path", ""),
            state.get("review_packet_path", ""),
            "streamlit_user",
            notes,
            json.dumps(state, default=str)
        ))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[DB] Error saving claim: {e}")
        return False


def get_recent_claims(limit: int = 10) -> List[Dict[str, Any]]:
    """Get recent processed claims."""
    try:
        init_db()
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM claims 
            ORDER BY timestamp DESC 
            LIMIT ?
        """, (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        claims = []
        for row in rows:
            claims.append({
                "id": row["id"],
                "email_id": row["email_id"],
                "claim_id": row["claim_id"],
                "decision": row["decision"],
                "timestamp": row["timestamp"],
                "customer_name": row["customer_name"],
                "customer_email": row["customer_email"],
                "product_name": row["product_name"],
                "issue_description": row["issue_description"],
                "recommendation": row["recommendation"],
                "confidence": row["confidence"],
                "reasoning": row["reasoning"],
                "warranty_valid": bool(row["warranty_valid"]),
                "email_draft": row["email_draft"],
                "email_path": row["email_path"],
                "label_path": row["label_path"],
                "packet_path": row["packet_path"],
                "notes": row["notes"]
            })
        
        return claims
    except Exception as e:
        print(f"[DB] Error getting claims: {e}")
        return []


def get_claim_by_email_id(email_id: str) -> Optional[Dict[str, Any]]:
    """Get a specific claim by email ID."""
    try:
        init_db()
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM claims WHERE email_id = ?", (email_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                "id": row["id"],
                "email_id": row["email_id"],
                "claim_id": row["claim_id"],
                "decision": row["decision"],
                "timestamp": row["timestamp"],
                "customer_name": row["customer_name"],
                "customer_email": row["customer_email"],
                "customer_address": row["customer_address"],
                "product_name": row["product_name"],
                "product_id": row["product_id"],
                "product_serial": row["product_serial"],
                "purchase_date": row["purchase_date"],
                "issue_description": row["issue_description"],
                "recommendation": row["recommendation"],
                "confidence": row["confidence"],
                "reasoning": row["reasoning"],
                "warranty_valid": bool(row["warranty_valid"]),
                "warranty_details": row["warranty_details"],
                "exclusions": json.loads(row["exclusions"]) if row["exclusions"] else [],
                "facts": json.loads(row["facts"]) if row["facts"] else [],
                "assumptions": json.loads(row["assumptions"]) if row["assumptions"] else [],
                "policy_references": json.loads(row["policy_references"]) if row["policy_references"] else [],
                "policy_id": row["policy_id"],
                "policy_version": row["policy_version"],
                "policy_effective_date": row["policy_effective_date"],
                "policy_file": row["policy_file"],
                "policy_retrieval": json.loads(row["policy_retrieval"]) if row["policy_retrieval"] else {},
                "llm_model": row["llm_model"],
                "email_draft": row["email_draft"],
                "email_path": row["email_path"],
                "label_path": row["label_path"],
                "packet_path": row["packet_path"],
                "reviewer": row["reviewer"],
                "notes": row["notes"],
                "full_state": json.loads(row["full_state"]) if row["full_state"] else {}
            }
        return None
    except Exception as e:
        print(f"[DB] Error getting claim: {e}")
        return None


def get_all_processed_email_ids() -> List[str]:
    """Get all processed email IDs for inbox filtering."""
    try:
        init_db()
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT email_id FROM claims")
        rows = cursor.fetchall()
        conn.close()
        
        return [row["email_id"] for row in rows]
    except Exception as e:
        print(f"[DB] Error getting email IDs: {e}")
        return []


def get_claim_decisions() -> Dict[str, str]:
    """Get all email_id -> decision mappings."""
    try:
        init_db()
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT email_id, decision FROM claims")
        rows = cursor.fetchall()
        conn.close()
        
        return {row["email_id"]: row["decision"] for row in rows}
    except Exception as e:
        print(f"[DB] Error getting decisions: {e}")
        return {}


def clear_all_claims():
    """Clear all claims from database (for reset)."""
    try:
        init_db()
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM claims")
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[DB] Error clearing claims: {e}")
        return False


def get_stats() -> Dict[str, int]:
    """Get claim statistics."""
    try:
        init_db()
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) as total FROM claims")
        total = cursor.fetchone()["total"]
        
        cursor.execute("SELECT COUNT(*) as approved FROM claims WHERE decision = 'APPROVE'")
        approved = cursor.fetchone()["approved"]
        
        cursor.execute("SELECT COUNT(*) as rejected FROM claims WHERE decision = 'REJECT'")
        rejected = cursor.fetchone()["rejected"]
        
        cursor.execute("SELECT COUNT(*) as need_info FROM claims WHERE decision = 'NEED_INFO'")
        need_info = cursor.fetchone()["need_info"]
        
        conn.close()
        
        return {
            "total": total,
            "approved": approved,
            "rejected": rejected,
            "need_info": need_info
        }
    except Exception as e:
        print(f"[DB] Error getting stats: {e}")
        return {"total": 0, "approved": 0, "rejected": 0, "need_info": 0}
