"""
Pytest configuration and shared fixtures for PM SHRI Kendriya Vidyalaya tests.
Runs isolated in-memory SQLite tests without requiring Supabase or GEMINI_API_KEY.
"""
import pytest
from datetime import date, datetime
from decimal import Decimal

from app import create_app, db as _db
from app.config import TestingConfig
from app.models import (
    User, Student, Batch, FeeStructure, FeeTransaction, FeeDue, FeePaymentAllocation,
    calculate_student_fee_summary, create_or_ensure_quarterly_dues
)


@pytest.fixture(scope='session')
def app():
    """Create test application using TestingConfig (in-memory SQLite)"""
    test_app = create_app(TestingConfig)
    return test_app


@pytest.fixture(scope='function')
def db(app):
    """Provide a clean database for each test function"""
    with app.app_context():
        _db.create_all()
        yield _db
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def client(app, db):
    """Test client for HTTP requests"""
    return app.test_client()


@pytest.fixture
def admin_user(db):
    """Admin user fixture"""
    user = User(
        username='TestAdmin',
        email='admin@test.com',
        role='ADMIN',
        is_active=True
    )
    user.set_password('AdminPass123')
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def teacher_user(db):
    """Teacher user fixture"""
    user = User(
        username='TestTeacher',
        email='teacher@test.com',
        role='TEACHER',
        is_active=True
    )
    user.set_password('TeacherPass123')
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def student_user(db):
    """Student user fixture"""
    user = User(
        username='TestStudentUser',
        email='student@test.com',
        role='STUDENT',
        is_active=True
    )
    user.set_password('StudentPass123')
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def sample_batch(db):
    """Sample batch fixture"""
    batch = Batch(
        name='Class 10-A',
        class_name='Class 10',
        capacity=30,
        is_active=True
    )
    db.session.add(batch)
    db.session.commit()
    return batch


@pytest.fixture
def sample_student(db, sample_batch):
    """Sample student fixture"""
    student = Student(
        student_id='SGA20260001',
        first_name='Aarav',
        last_name='Sharma',
        date_of_birth=date(2010, 5, 15),
        gender='MALE',
        email='aarav.sharma@example.com',
        phone='9876543210',
        parent_name='Ramesh Sharma',
        parent_phone='9876543211',
        batch_id=sample_batch.id,
        enrollment_date=date(2026, 4, 1),
        status='ACTIVE'
    )
    db.session.add(student)
    db.session.commit()
    return student


@pytest.fixture
def sample_fee_structure(db, sample_batch):
    """Sample quarterly fee structure fixture"""
    structure = FeeStructure(
        name='Class 10 - Tuition Fee 2026-27',
        batch_id=sample_batch.id,
        academic_session='2026-27',
        fee_component='Tuition Fee',
        amount=Decimal('5000.00'),
        frequency='QUARTERLY',
        is_active=True
    )
    db.session.add(structure)
    db.session.commit()
    return structure
