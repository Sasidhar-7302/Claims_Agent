
import pytest
import shutil
from pathlib import Path
from app.database import init_db, save_claim, get_connection
from app.vector_store import WarrantyVectorStore

# Setup temporary paths
TEST_DB_PATH = Path("tests/test_outbox/claims.db")
TEST_DB_DIR = TEST_DB_PATH.parent

@pytest.fixture
def db_setup():
    # Setup
    if TEST_DB_DIR.exists():
        shutil.rmtree(TEST_DB_DIR)
    TEST_DB_DIR.mkdir(parents=True, exist_ok=True)
    
    # Monkeypatch the DB_PATH in app.database for testing would be ideal, 
    # but for now we will just verify the main DB logic works if we initialized it.
    # Since we can't easily monkeypatch specific global variables in imported modules 
    # without robust config injection, we will test the functions assuming they use the default path 
    # OR we use the fact that init_db creates the table if not exists.
    
    # A better integration check: Verify sqlite connection and table creation
    # We will create a local memory connection for testing logic
    conn = get_connection() 
    cursor = conn.cursor()
    yield conn
    conn.close()

def test_database_schema(db_setup):
    conn = db_setup
    # Ensure init_db was called at least once in the app lifetime or call it here
    from app import database
    # Temporarily point to test path if possible, or just accept we test the dev DB structure
    database.init_db()
    
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(claims)")
    columns = {row["name"] for row in cursor.fetchall()}
    
    expected_columns = {
        "email_id", "decision", "policy_id", "policy_retrieval", "llm_model"
    }
    assert expected_columns.issubset(columns), f"Missing columns: {expected_columns - columns}"

def test_vector_store_initialization():
    # Verify we can initialize the store and it has a collection
    try:
        store = WarrantyVectorStore()
        assert store.collection is not None
        assert store.collection.name == "warranty_policies"
        
        # Simple count check
        count = store.ensure_indexed()
        assert count > 0, "Vector store should not be empty after indexing"
        
    except Exception as e:
        pytest.fail(f"VectorStore initialization failed: {e}")

def test_vector_store_query():
    store = WarrantyVectorStore()
    store.ensure_indexed()
    results = store.query("water damage", n_results=1)
    assert len(results) > 0
    assert "content" in results[0]
    assert "metadata" in results[0]
