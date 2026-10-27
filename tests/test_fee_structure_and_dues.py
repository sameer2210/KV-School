"""
Tests 2 & 3: Creating fee structures and Q1-Q4 dues with session associations and multiple components.
"""
from datetime import date
from decimal import Decimal
from app.models import FeeStructure, FeeDue, create_or_ensure_quarterly_dues, calculate_student_fee_summary


def test_create_fee_structure_for_academic_session(db, sample_batch):
    """Test 2: Creating a fee structure for an academic session"""
    structure = FeeStructure(
        name='Class 10 - Examination Fee 2026-27',
        batch_id=sample_batch.id,
        academic_session='2026-27',
        fee_component='Examination Fee',
        amount=Decimal('1500.00'),
        frequency='ONE_TIME',
        is_active=True
    )
    db.session.add(structure)
    db.session.commit()

    saved = FeeStructure.query.filter_by(name='Class 10 - Examination Fee 2026-27').first()
    assert saved is not None
    assert saved.academic_session == '2026-27'
    assert saved.fee_component == 'Examination Fee'
    assert saved.amount == Decimal('1500.00')
    assert saved.batch_id == sample_batch.id


def test_create_q1_to_q4_dues_with_session_association(db, sample_student, sample_fee_structure):
    """Test 3: Creating Q1–Q4 dues with correct session association"""
    created_dues = create_or_ensure_quarterly_dues(sample_student, academic_session='2026-27')
    
    assert len(created_dues) == 4
    quarters = [d.quarter for d in created_dues]
    assert set(quarters) == {'Q1', 'Q2', 'Q3', 'Q4'}

    for due in created_dues:
        assert due.academic_session == '2026-27'
        assert due.student_id == sample_student.id
        assert due.amount == Decimal('5000.00')
        assert due.paid_amount == Decimal('0.00')
        assert due.pending_amount == Decimal('5000.00')
        assert due.fee_component == 'Tuition Fee'

    # Check due dates for each quarter
    q1_due = next(d for d in created_dues if d.quarter == 'Q1')
    q2_due = next(d for d in created_dues if d.quarter == 'Q2')
    q3_due = next(d for d in created_dues if d.quarter == 'Q3')
    q4_due = next(d for d in created_dues if d.quarter == 'Q4')

    assert q1_due.due_date == date(2026, 4, 10)
    assert q2_due.due_date == date(2026, 7, 10)
    assert q3_due.due_date == date(2026, 10, 10)
    assert q4_due.due_date == date(2027, 1, 10)

    # Calling it a second time should not create duplicate dues
    dues_second_run = create_or_ensure_quarterly_dues(sample_student, academic_session='2026-27')
    assert len(dues_second_run) == 0

    # Total assessed should be 4 * 5000 = 20,000
    summary = calculate_student_fee_summary(sample_student.id, session='2026-27')
    assert summary['total_assessed'] == Decimal('20000.00')
    assert summary['outstanding_balance'] == Decimal('20000.00')
    assert summary['total_paid'] == Decimal('0.00')


def test_multiple_fee_components_different_amounts(db, sample_batch, sample_student):
    """Test creating multiple components (Tuition, Transport, Admission) with different amounts"""
    struct_tuition = FeeStructure(
        name='Class 10 - Tuition Fee',
        batch_id=sample_batch.id,
        academic_session='2026-27',
        fee_component='Tuition Fee',
        amount=Decimal('4000.00'),
        frequency='QUARTERLY'
    )
    struct_transport = FeeStructure(
        name='Class 10 - Transport Fee',
        batch_id=sample_batch.id,
        academic_session='2026-27',
        fee_component='Transport Fee',
        amount=Decimal('1200.00'),
        frequency='QUARTERLY'
    )
    struct_admission = FeeStructure(
        name='Class 10 - Admission Fee',
        batch_id=sample_batch.id,
        academic_session='2026-27',
        fee_component='Admission Fee',
        amount=Decimal('2500.00'),
        frequency='ONE_TIME'
    )
    db.session.add_all([struct_tuition, struct_transport, struct_admission])
    db.session.commit()

    created_dues = create_or_ensure_quarterly_dues(sample_student, '2026-27')
    # 4 quarters of Tuition + 4 quarters of Transport + 1 One-time Admission = 9 dues
    assert len(created_dues) == 9

    summary = calculate_student_fee_summary(sample_student.id, '2026-27')
    # Expected: (4 * 4000) + (4 * 1200) + 2500 = 16000 + 4800 + 2500 = 23300
    assert summary['total_assessed'] == Decimal('23300.00')
    assert summary['outstanding_balance'] == Decimal('23300.00')
