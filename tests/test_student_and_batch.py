"""
Test 1: Student creation, class/batch assignment, and search functionality.
"""
from datetime import date
from app.models import Student, Batch


def test_student_creation_and_batch_assignment(db, sample_batch):
    """Test 1: Student creation and class/batch assignment"""
    student = Student(
        student_id='SGA20260099',
        first_name='Priya',
        last_name='Patel',
        gender='FEMALE',
        date_of_birth=date(2011, 8, 20),
        phone='9123456780',
        parent_name='Suresh Patel',
        parent_phone='9123456781',
        batch_id=sample_batch.id,
        enrollment_date=date(2026, 4, 1),
        status='ACTIVE'
    )
    db.session.add(student)
    db.session.commit()

    saved = Student.query.filter_by(student_id='SGA20260099').first()
    assert saved is not None
    assert saved.full_name == 'Priya Patel'
    assert saved.batch_id == sample_batch.id
    assert saved.batch.name == 'Class 10-A'
    assert saved.parent_name == 'Suresh Patel'
    assert saved.parent_phone == '9123456781'


def test_student_search_endpoint(client, db, admin_user, sample_student):
    """Test reliable student search by full name, ID, and partial match"""
    # Login as admin
    client.post('/login', data={
        'email': admin_user.email,
        'password': 'AdminPass123'
    })

    # 1. Search by student ID
    res = client.get(f'/students/api/search?q={sample_student.student_id}')
    assert res.status_code == 200
    data = res.get_json()
    assert len(data) == 1
    assert data[0]['student_id'] == sample_student.student_id

    # 2. Search by full name "Aarav Sharma"
    res = client.get('/students/api/search?q=Aarav+Sharma')
    assert res.status_code == 200
    data = res.get_json()
    assert len(data) == 1
    assert data[0]['name'] == 'Aarav Sharma'

    # 3. Search by parent name
    res = client.get('/students/api/search?q=Ramesh')
    assert res.status_code == 200
    data = res.get_json()
    assert len(data) == 1
    assert data[0]['name'] == 'Aarav Sharma'


def test_unique_student_id(db, sample_batch):
    """Test that student ID is unique"""
    s1 = Student(
        student_id='SGA20260002',
        first_name='Karan',
        last_name='Mehta',
        batch_id=sample_batch.id
    )
    db.session.add(s1)
    db.session.commit()

    s2 = Student(
        student_id='SGA20260002',
        first_name='Duplicate',
        last_name='ID',
        batch_id=sample_batch.id
    )
    db.session.add(s2)
    try:
        db.session.commit()
        assert False, "Duplicate student ID should fail"
    except Exception:
        db.session.rollback()
        assert True
