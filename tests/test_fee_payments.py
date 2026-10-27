"""
Tests 4 through 9: Fee payments, partial payments, multiple quarters, allocation integrity,
overpayment prevention, receipt generation, and reversals.
"""
from decimal import Decimal
from datetime import date
from app.models import (
    FeeStructure, FeeDue, FeeTransaction, FeePaymentAllocation,
    create_or_ensure_quarterly_dues, calculate_student_fee_summary
)


def test_full_and_partial_payments(client, db, admin_user, sample_student, sample_fee_structure):
    """Test 4: Full payment and partial payment"""
    # Create Q1-Q4 dues (₹5,000 each)
    create_or_ensure_quarterly_dues(sample_student, '2026-27')
    
    q1_due = FeeDue.query.filter_by(student_id=sample_student.id, quarter='Q1').first()
    assert q1_due.pending_amount == Decimal('5000.00')

    # Login as admin
    client.post('/login', data={'email': admin_user.email, 'password': 'AdminPass123'})

    # 1. Partial payment of ₹2,000 on Q1
    res = client.post('/fees/collect', data={
        'student_id': sample_student.id,
        'amount': '2000.00',
        'payment_mode': 'CASH',
        'academic_session': '2026-27',
        'quarter': 'Q1',
        'fee_due_id': q1_due.id
    }, follow_redirects=True)
    assert res.status_code == 200

    db.session.refresh(q1_due)
    assert q1_due.paid_amount == Decimal('2000.00')
    assert q1_due.pending_amount == Decimal('3000.00')
    assert q1_due.status == FeeDue.STATUS_PARTIAL

    # 2. Complete the remaining balance of ₹3,000 on Q1 (Full payment)
    res2 = client.post('/fees/collect', data={
        'student_id': sample_student.id,
        'amount': '3000.00',
        'payment_mode': 'UPI',
        'transaction_id': 'UPI123456789',
        'academic_session': '2026-27',
        'quarter': 'Q1',
        'fee_due_id': q1_due.id
    }, follow_redirects=True)
    assert res2.status_code == 200

    db.session.refresh(q1_due)
    assert q1_due.paid_amount == Decimal('5000.00')
    assert q1_due.pending_amount == Decimal('0.00')
    assert q1_due.status == FeeDue.STATUS_PAID


def test_two_separate_quarterly_payments_same_student(client, db, admin_user, sample_student, sample_fee_structure):
    """Test 5 & 7: Two separate quarterly payments for same student do not affect unrelated quarters"""
    create_or_ensure_quarterly_dues(sample_student, '2026-27')
    
    q1_due = FeeDue.query.filter_by(student_id=sample_student.id, quarter='Q1').first()
    q2_due = FeeDue.query.filter_by(student_id=sample_student.id, quarter='Q2').first()
    q3_due = FeeDue.query.filter_by(student_id=sample_student.id, quarter='Q3').first()
    q4_due = FeeDue.query.filter_by(student_id=sample_student.id, quarter='Q4').first()

    client.post('/login', data={'email': admin_user.email, 'password': 'AdminPass123'})

    # Pay Q1 in full (₹5,000)
    client.post('/fees/collect', data={
        'student_id': sample_student.id,
        'amount': '5000.00',
        'payment_mode': 'BANK_TRANSFER',
        'academic_session': '2026-27',
        'quarter': 'Q1',
        'fee_due_id': q1_due.id
    }, follow_redirects=True)

    # Pay Q2 in full (₹5,000)
    client.post('/fees/collect', data={
        'student_id': sample_student.id,
        'amount': '5000.00',
        'payment_mode': 'CASH',
        'academic_session': '2026-27',
        'quarter': 'Q2',
        'fee_due_id': q2_due.id
    }, follow_redirects=True)

    db.session.refresh(q1_due)
    db.session.refresh(q2_due)
    db.session.refresh(q3_due)
    db.session.refresh(q4_due)

    # Q1 and Q2 must be PAID
    assert q1_due.status == FeeDue.STATUS_PAID
    assert q1_due.paid_amount == Decimal('5000.00')
    assert q1_due.pending_amount == Decimal('0.00')

    assert q2_due.status == FeeDue.STATUS_PAID
    assert q2_due.paid_amount == Decimal('5000.00')
    assert q2_due.pending_amount == Decimal('0.00')

    # Test 7: Q3 and Q4 must remain completely untouched!
    assert q3_due.status in [FeeDue.STATUS_PENDING, FeeDue.STATUS_OVERDUE]
    assert q3_due.paid_amount == Decimal('0.00')
    assert q3_due.pending_amount == Decimal('5000.00')

    assert q4_due.status == FeeDue.STATUS_PENDING
    assert q4_due.paid_amount == Decimal('0.00')
    assert q4_due.pending_amount == Decimal('5000.00')


def test_correct_remaining_balance_after_multiple_payments(client, db, admin_user, sample_student, sample_fee_structure):
    """Test 6: Correct remaining balance calculation across multiple payments"""
    create_or_ensure_quarterly_dues(sample_student, '2026-27')
    client.post('/login', data={'email': admin_user.email, 'password': 'AdminPass123'})

    # Initial balance: 4 * 5000 = 20,000
    s0 = calculate_student_fee_summary(sample_student.id, '2026-27')
    assert s0['total_assessed'] == Decimal('20000.00')
    assert s0['total_paid'] == Decimal('0.00')
    assert s0['outstanding_balance'] == Decimal('20000.00')

    # Payment 1: ₹5,000
    client.post('/fees/collect', data={
        'student_id': sample_student.id,
        'amount': '5000.00',
        'payment_mode': 'CASH',
        'academic_session': '2026-27',
        'quarter': 'Q1'
    }, follow_redirects=True)

    s1 = calculate_student_fee_summary(sample_student.id, '2026-27')
    assert s1['total_paid'] == Decimal('5000.00')
    assert s1['outstanding_balance'] == Decimal('15000.00')

    # Payment 2: ₹3,500 (partial on Q2)
    client.post('/fees/collect', data={
        'student_id': sample_student.id,
        'amount': '3500.00',
        'payment_mode': 'UPI',
        'academic_session': '2026-27',
        'quarter': 'Q2'
    }, follow_redirects=True)

    s2 = calculate_student_fee_summary(sample_student.id, '2026-27')
    assert s2['total_paid'] == Decimal('8500.00')
    assert s2['outstanding_balance'] == Decimal('11500.00')


def test_excessive_and_invalid_payment_rejected_safely(client, db, admin_user, sample_student, sample_fee_structure):
    """Test 8: Invalid or excessive payment is rejected safely"""
    create_or_ensure_quarterly_dues(sample_student, '2026-27')
    q1_due = FeeDue.query.filter_by(student_id=sample_student.id, quarter='Q1').first()
    client.post('/login', data={'email': admin_user.email, 'password': 'AdminPass123'})

    # 1. Overpayment: Attempt to pay ₹8,000 against a ₹5,000 due
    res = client.post('/fees/collect', data={
        'student_id': sample_student.id,
        'amount': '8000.00',
        'payment_mode': 'CASH',
        'academic_session': '2026-27',
        'quarter': 'Q1',
        'fee_due_id': q1_due.id
    }, follow_redirects=True)
    assert b'exceeds outstanding' in res.data or b'prevented' in res.data
    # Due should not be modified
    db.session.refresh(q1_due)
    assert q1_due.paid_amount == Decimal('0.00')

    # 2. Negative amount
    res = client.post('/fees/collect', data={
        'student_id': sample_student.id,
        'amount': '-500.00',
        'payment_mode': 'CASH'
    }, follow_redirects=True)
    assert b'greater than zero' in res.data

    # 3. Negative discount
    res = client.post('/fees/collect', data={
        'student_id': sample_student.id,
        'amount': '1000.00',
        'discount': '-200.00',
        'payment_mode': 'CASH'
    }, follow_redirects=True)
    assert b'cannot be negative' in res.data

    # 4. Invalid student ID
    res = client.post('/fees/collect', data={
        'student_id': 999999,
        'amount': '1000.00',
        'payment_mode': 'CASH'
    }, follow_redirects=True)
    assert b'Invalid student' in res.data or res.status_code in [302, 404]


def test_receipt_number_uniqueness_and_receipt_display(client, db, admin_user, sample_student, sample_fee_structure):
    """Test 9: Unique receipt numbers generated and receipt display works without missing templates"""
    create_or_ensure_quarterly_dues(sample_student, '2026-27')
    client.post('/login', data={'email': admin_user.email, 'password': 'AdminPass123'})

    # Make 3 payments in sequence
    r1 = client.post('/fees/collect', data={
        'student_id': sample_student.id,
        'amount': '1000.00',
        'payment_mode': 'CASH',
        'academic_session': '2026-27',
        'quarter': 'Q1'
    }, follow_redirects=False)
    txn1_id = r1.headers['Location'].split('/')[-1]

    r2 = client.post('/fees/collect', data={
        'student_id': sample_student.id,
        'amount': '1000.00',
        'payment_mode': 'UPI',
        'academic_session': '2026-27',
        'quarter': 'Q1'
    }, follow_redirects=False)
    txn2_id = r2.headers['Location'].split('/')[-1]

    t1 = FeeTransaction.query.get(txn1_id)
    t2 = FeeTransaction.query.get(txn2_id)
    assert t1.receipt_number != t2.receipt_number

    # View receipt page
    res_view = client.get(f'/fees/receipt/{t1.id}')
    assert res_view.status_code == 200
    assert t1.receipt_number.encode() in res_view.data
    assert b'Aarav Sharma' in res_view.data
    assert b'Tuition Fee' in res_view.data

    # Test printable receipt route (verifying NO TemplateNotFound crash!)
    res_print = client.get(f'/fees/receipt/{t1.id}/print')
    assert res_print.status_code == 200
    assert t1.receipt_number.encode() in res_print.data

    # Test PDF route
    res_pdf = client.get(f'/fees/receipt/{t1.id}/pdf')
    assert res_pdf.status_code == 200
    assert res_pdf.content_type == 'application/pdf'


def test_payment_reversal_workflow(client, db, admin_user, sample_student, sample_fee_structure):
    """Test auditable payment reversal restores due balances and updates status"""
    create_or_ensure_quarterly_dues(sample_student, '2026-27')
    q1_due = FeeDue.query.filter_by(student_id=sample_student.id, quarter='Q1').first()
    client.post('/login', data={'email': admin_user.email, 'password': 'AdminPass123'})

    # Collect ₹5,000
    client.post('/fees/collect', data={
        'student_id': sample_student.id,
        'amount': '5000.00',
        'payment_mode': 'CASH',
        'academic_session': '2026-27',
        'quarter': 'Q1',
        'fee_due_id': q1_due.id
    }, follow_redirects=True)

    txn = FeeTransaction.query.filter_by(student_id=sample_student.id).first()
    assert txn.status == FeeTransaction.STATUS_SUCCESS

    db.session.refresh(q1_due)
    assert q1_due.status == FeeDue.STATUS_PAID
    assert q1_due.pending_amount == Decimal('0.00')

    # Reverse transaction with reason
    rev_res = client.post(f'/fees/transactions/{txn.id}/reverse', data={
        'reason': 'Accidental duplicate payment entry'
    }, follow_redirects=True)
    assert rev_res.status_code == 200
    assert b'reversed' in rev_res.data

    db.session.refresh(txn)
    assert txn.status == FeeTransaction.STATUS_REVERSED
    assert txn.reversal_reason == 'Accidental duplicate payment entry'
    assert txn.reversed_by == admin_user.id
    assert txn.reversed_at is not None

    # Verify due balance is restored!
    db.session.refresh(q1_due)
    assert q1_due.status in [FeeDue.STATUS_PENDING, FeeDue.STATUS_OVERDUE]
    assert q1_due.paid_amount == Decimal('0.00')
    assert q1_due.pending_amount == Decimal('5000.00')
