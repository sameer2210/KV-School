"""
Tests 12, 13, 14: Security, authorization, schema migrations, and SQLite startup without Supabase/Gemini.
"""
import pytest
import sqlite3
import tempfile
import os
from decimal import Decimal
from app import create_app, db as _db
from app.config import Config, ProductionConfig, TestingConfig
from app.models import User, Student, Batch, FeeStructure, FeeTransaction, FeeDue


def test_unauthorized_access_to_financial_routes(client, student_user):
    """Test 12: Unauthorized access to collection and financial routes is blocked"""
    # 1. Unauthenticated requests should redirect to login
    res_collect = client.get('/fees/collect')
    assert res_collect.status_code == 302
    assert '/login' in res_collect.headers['Location']

    res_report = client.get('/fees/report')
    assert res_report.status_code == 302
    assert '/login' in res_report.headers['Location']

    # 2. Student role should be forbidden from accessing staff fee collection and reports
    client.post('/login', data={'email': student_user.email, 'password': 'StudentPass123'})

    res_student_collect = client.get('/fees/collect')
    assert res_student_collect.status_code == 403

    res_student_report = client.get('/fees/report')
    assert res_student_report.status_code == 403

    res_student_structures = client.get('/fees/structure')
    assert res_student_structures.status_code == 403


def test_sqlite_test_startup_without_supabase_or_gemini(monkeypatch):
    """Test 14: SQLite-based startup without Supabase or a Gemini key"""
    # Clear DATABASE_URL and GEMINI_API_KEY from environment
    monkeypatch.delenv('DATABASE_URL', raising=False)
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    monkeypatch.setenv('USE_SQLITE', '1')

    # App factory creates cleanly without external service dependencies
    local_app = create_app(TestingConfig)
    assert local_app is not None
    assert local_app.config['TESTING'] is True
    assert 'sqlite' in local_app.config['SQLALCHEMY_DATABASE_URI']


def test_production_secret_key_validation(monkeypatch):
    """Test: Insecure or default SECRET_KEY is rejected in ProductionConfig"""
    monkeypatch.setenv('SECRET_KEY', 'sarva-gyaan-academy-secret-key-2024')
    with pytest.raises(ValueError, match="Production mode requires a strong explicit SECRET_KEY"):
        ProductionConfig.validate_production()

    monkeypatch.setenv('SECRET_KEY', 'short')
    with pytest.raises(ValueError, match="Production mode requires a strong explicit SECRET_KEY"):
        ProductionConfig.validate_production()


def test_database_migration_from_preexisting_schema(tmp_path):
    """Test 13: Database migration from a pre-existing schema without data loss"""
    db_file = tmp_path / "legacy_test.db"
    conn = sqlite3.connect(str(db_file))
    cur = conn.cursor()

    # Create old/pre-existing schema (before quarterly fee updates)
    cur.execute("""
        CREATE TABLE fee_structures (
            id INTEGER PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            amount NUMERIC(10, 2) NOT NULL,
            frequency VARCHAR(20),
            description TEXT,
            is_active BOOLEAN
        );
    """)
    cur.execute("""
        CREATE TABLE fee_dues (
            id INTEGER PRIMARY KEY,
            student_id INTEGER NOT NULL,
            fee_structure_id INTEGER,
            amount NUMERIC(10, 2) NOT NULL,
            due_date DATE NOT NULL,
            month_for VARCHAR(20),
            status VARCHAR(20),
            paid_amount NUMERIC(10, 2)
        );
    """)
    cur.execute("""
        CREATE TABLE fee_transactions (
            id INTEGER PRIMARY KEY,
            receipt_number VARCHAR(20) UNIQUE NOT NULL,
            student_id INTEGER NOT NULL,
            amount NUMERIC(10, 2) NOT NULL,
            payment_date DATE NOT NULL,
            payment_mode VARCHAR(20)
        );
    """)

    # Insert legacy records
    cur.execute("INSERT INTO fee_structures (id, name, amount, frequency, is_active) VALUES (1, 'Tuition', 3000.00, 'MONTHLY', 1);")
    cur.execute("INSERT INTO fee_dues (id, student_id, amount, due_date, status, paid_amount) VALUES (1, 101, 3000.00, '2026-04-10', 'PENDING', 0.00);")
    cur.execute("INSERT INTO fee_transactions (id, receipt_number, student_id, amount, payment_date, payment_mode) VALUES (1, 'REC202604010001', 101, 3000.00, '2026-04-10', 'CASH');")
    conn.commit()
    conn.close()

    # Now create an app targeting this database file
    class LegacyConfig(TestingConfig):
        SQLALCHEMY_DATABASE_URI = f'sqlite:///{db_file}'

    app = create_app(LegacyConfig)

    with app.app_context():
        # Verify that legacy records are completely preserved
        fs = FeeStructure.query.get(1)
        assert fs is not None
        assert fs.name == 'Tuition'
        assert fs.amount == Decimal('3000.00')

        fd = FeeDue.query.get(1)
        assert fd is not None
        assert fd.amount == Decimal('3000.00')
        # Check newly added column is accessible without error!
        assert hasattr(fd, 'academic_session')
        assert hasattr(fd, 'quarter')
        assert hasattr(fd, 'discount_amount')

        tx = FeeTransaction.query.get(1)
        assert tx is not None
        assert tx.receipt_number == 'REC202604010001'
        assert hasattr(tx, 'status')
        assert hasattr(tx, 'reversal_reason')


def test_vercel_environment_instance_path(monkeypatch):
    """Test: Vercel environment uses writable temporary directory without touching read-only deployment path"""
    from app.config import is_running_on_vercel, get_instance_path
    import tempfile

    monkeypatch.setenv('VERCEL', '1')
    assert is_running_on_vercel() is True

    vercel_instance = get_instance_path()
    assert tempfile.gettempdir() in vercel_instance or vercel_instance.startswith('/tmp')

    # Verify app initialization under Vercel configuration
    class VercelConfig(TestingConfig):
        INSTANCE_PATH = vercel_instance

    vercel_app = create_app(VercelConfig)
    assert vercel_app is not None
    assert vercel_app.instance_path == vercel_instance


def test_vercel_database_url_preservation(monkeypatch):
    """Test: PostgreSQL/Supabase database URL is preserved for persistent storage in Vercel mode"""
    from app.config import get_database_url

    monkeypatch.setenv('VERCEL', '1')
    monkeypatch.setenv('DATABASE_URL', 'postgres://postgres:securepass@db.supabase.co:5432/postgres')
    
    url = get_database_url()
    assert url == 'postgresql://postgres:securepass@db.supabase.co:5432/postgres'
