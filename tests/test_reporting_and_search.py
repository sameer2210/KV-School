"""
Tests 10 & 11: Search/filter correctness, pagination totals, quarter/session reporting, and exports.
"""
from datetime import date
from decimal import Decimal
from app.models import Student, Batch, FeeTransaction, FeeDue


def test_transactions_search_and_pagination_totals(client, db, admin_user, sample_batch):
    """Test 10: Displayed totals correspond to full filtered result, not just current pagination page"""
    client.post('/login', data={'email': admin_user.email, 'password': 'AdminPass123'})

    # Create 25 students and 25 transactions of ₹1,000 each (Total = ₹25,000)
    for i in range(1, 26):
        student = Student(
            student_id=f'SGA2026{i:04d}',
            first_name=f'Student{i}',
            last_name='Test',
            phone=f'987650{i:04d}',
            batch_id=sample_batch.id
        )
        db.session.add(student)
        db.session.flush()

        txn = FeeTransaction(
            receipt_number=f'REC20261026{i:04d}',
            student_id=student.id,
            amount=Decimal('1000.00'),
            payment_date=date(2026, 10, 26),
            payment_mode='CASH',
            academic_session='2026-27',
            quarter='Q3',
            status=FeeTransaction.STATUS_SUCCESS,
            collected_by=admin_user.id
        )
        db.session.add(txn)

    db.session.commit()

    # Query page 1 (which has 20 items per page)
    res = client.get('/fees/transactions?page=1')
    assert res.status_code == 200
    # Crucial check: Total displayed must be ₹25,000.00, NOT ₹20,000.00!
    assert b'25,000.00' in res.data
    assert b'25 records' in res.data

    # Query page 2 (remaining 5 items)
    res2 = client.get('/fees/transactions?page=2')
    assert res2.status_code == 200
    # Must still show the full filtered total ₹25,000.00!
    assert b'25,000.00' in res2.data

    # Search filter test: search for 'Student15'
    res_search = client.get('/fees/transactions?search=Student15')
    assert res_search.status_code == 200
    assert b'1,000.00' in res_search.data
    assert b'1 records' in res_search.data


def test_quarter_and_session_reporting_and_exports(client, db, admin_user, sample_student):
    """Test 11: Quarter and academic session reporting and export to CSV/Excel"""
    client.post('/login', data={'email': admin_user.email, 'password': 'AdminPass123'})

    # Add Q1 transaction: ₹4,000 in Session 2026-27
    t1 = FeeTransaction(
        receipt_number='REC202604010001',
        student_id=sample_student.id,
        amount=Decimal('4000.00'),
        payment_date=date(2026, 4, 15),
        payment_mode='CASH',
        academic_session='2026-27',
        quarter='Q1',
        fee_component='Tuition Fee',
        status=FeeTransaction.STATUS_SUCCESS,
        collected_by=admin_user.id
    )
    # Add Q2 transaction: ₹6,000 in Session 2026-27
    t2 = FeeTransaction(
        receipt_number='REC202607010001',
        student_id=sample_student.id,
        amount=Decimal('6000.00'),
        payment_date=date(2026, 7, 20),
        payment_mode='UPI',
        academic_session='2026-27',
        quarter='Q2',
        fee_component='Tuition Fee',
        status=FeeTransaction.STATUS_SUCCESS,
        collected_by=admin_user.id
    )
    db.session.add_all([t1, t2])
    db.session.commit()

    # 1. Check report view for session 2026-27
    res = client.get('/fees/report?academic_session=2026-27')
    assert res.status_code == 200
    assert b'Q1' in res.data
    assert b'Q2' in res.data
    assert b'4,000.00' in res.data
    assert b'6,000.00' in res.data

    # 2. Export report to CSV
    csv_res = client.get('/fees/report/export-csv?month=4&year=2026')
    assert csv_res.status_code == 200
    assert csv_res.content_type == 'text/csv'
    assert b'4000.00' in csv_res.data

    # 3. Export report to Excel
    excel_res = client.get('/fees/report/export-excel?month=4&year=2026')
    assert excel_res.status_code == 200
    assert 'spreadsheet' in excel_res.content_type or excel_res.status_code == 302
