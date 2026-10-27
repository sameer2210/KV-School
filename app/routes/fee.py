"""
Fee Management Routes
"""
import io
import csv
from datetime import datetime, date
from decimal import Decimal
from flask import (
    Blueprint, render_template, redirect, url_for, flash, request,
    Response, make_response, abort, current_app, jsonify
)
from flask_login import login_required, current_user
from sqlalchemy import func, or_

from app import db
from app.models import (
    Student, Batch, FeeStructure, FeeTransaction, FeeDue, FeePaymentAllocation,
    calculate_student_fee_summary, create_or_ensure_quarterly_dues
)
from app.utils.decorators import staff_required, admin_required
from app.utils.helpers import (
    parse_date, format_currency, format_date, get_months_list, paginate_query,
    get_current_academic_year, get_current_quarter, get_quarter_due_date,
    number_to_words_inr, QUARTERS, QUARTER_DETAILS, FEE_COMPONENTS
)

fee_bp = Blueprint('fee', __name__, url_prefix='/fees')


@fee_bp.route('/')
@login_required
@staff_required
def index():
    """Fee management dashboard"""
    today = date.today()
    current_session = get_current_academic_year()

    # Today's collection (only non-reversed successful transactions)
    today_collection = db.session.query(func.sum(FeeTransaction.amount)).filter(
        FeeTransaction.payment_date == today,
        FeeTransaction.status != FeeTransaction.STATUS_REVERSED
    ).scalar() or Decimal('0.00')

    # This month's collection
    first_day = date(today.year, today.month, 1)
    monthly_collection = db.session.query(func.sum(FeeTransaction.amount)).filter(
        FeeTransaction.payment_date >= first_day,
        FeeTransaction.payment_date <= today,
        FeeTransaction.status != FeeTransaction.STATUS_REVERSED
    ).scalar() or Decimal('0.00')

    # Current session collection
    session_collection = db.session.query(func.sum(FeeTransaction.amount)).filter(
        FeeTransaction.academic_session == current_session,
        FeeTransaction.status != FeeTransaction.STATUS_REVERSED
    ).scalar() or Decimal('0.00')

    # Total pending balance from FeeDue (Single source of truth)
    total_pending = db.session.query(
        func.sum(FeeDue.amount - FeeDue.paid_amount - FeeDue.discount_amount + FeeDue.fine_amount)
    ).filter(
        FeeDue.status != FeeDue.STATUS_PAID
    ).scalar() or Decimal('0.00')
    total_pending = max(Decimal('0.00'), total_pending)

    # Overdue dues count
    overdue_count = FeeDue.query.filter(
        FeeDue.status != FeeDue.STATUS_PAID,
        FeeDue.due_date < today
    ).count()

    # Recent transactions
    recent_transactions = FeeTransaction.query.order_by(
        FeeTransaction.created_at.desc()
    ).limit(10).all()

    # Fee structures
    fee_structures = FeeStructure.query.filter_by(is_active=True).all()

    return render_template('fee/index.html',
        today_collection=today_collection,
        monthly_collection=monthly_collection,
        session_collection=session_collection,
        total_pending=total_pending,
        overdue_count=overdue_count,
        recent_transactions=recent_transactions,
        fee_structures=fee_structures,
        current_session=current_session
    )


@fee_bp.route('/collect', methods=['GET', 'POST'])
@login_required
@staff_required
def collect_fee():
    """Collect fee from student with quarter/due allocation and validation"""
    current_session = get_current_academic_year()
    current_qtr = get_current_quarter()

    if request.method == 'POST':
        try:
            student_id = request.form.get('student_id', type=int)
            amount_str = request.form.get('amount', '0').strip()
            payment_mode = request.form.get('payment_mode', 'CASH').strip()
            academic_session = request.form.get('academic_session', current_session).strip() or current_session
            quarter = request.form.get('quarter', '').strip() or None
            fee_component = request.form.get('fee_component', '').strip() or 'Tuition Fee'
            fee_due_id = request.form.get('fee_due_id', type=int)
            description = request.form.get('description', '').strip()

            # Monetary inputs validation
            try:
                amount = Decimal(amount_str)
            except Exception:
                flash('Please enter a valid monetary amount.', 'danger')
                return redirect(request.url)

            try:
                discount = Decimal(request.form.get('discount', '0') or '0')
            except Exception:
                discount = Decimal('0.00')

            try:
                fine = Decimal(request.form.get('fine', '0') or '0')
            except Exception:
                fine = Decimal('0.00')

            if not student_id:
                flash('Please select a student.', 'warning')
                return redirect(request.url)

            if amount <= Decimal('0.00'):
                flash('Payment amount must be greater than zero.', 'danger')
                return redirect(request.url)

            if discount < Decimal('0.00'):
                flash('Discount amount cannot be negative.', 'danger')
                return redirect(request.url)

            if fine < Decimal('0.00'):
                flash('Fine amount cannot be negative.', 'danger')
                return redirect(request.url)

            student = Student.query.get(student_id)
            if not student:
                flash('Invalid student record selected.', 'danger')
                return redirect(request.url)

            # Determine target due(s) to allocate payment
            target_dues = []

            if fee_due_id:
                specific_due = FeeDue.query.get(fee_due_id)
                if not specific_due or specific_due.student_id != student.id:
                    flash('Selected fee due does not match this student.', 'danger')
                    return redirect(request.url)
                target_dues = [specific_due]
            elif quarter:
                # Target due for specific quarter & component
                specific_due = FeeDue.query.filter_by(
                    student_id=student.id,
                    academic_session=academic_session,
                    quarter=quarter,
                    fee_component=fee_component
                ).first()
                if not specific_due:
                    # Create the due for this quarter
                    specific_due = FeeDue(
                        student_id=student.id,
                        academic_session=academic_session,
                        quarter=quarter,
                        fee_component=fee_component,
                        amount=amount,
                        due_date=get_quarter_due_date(academic_session, quarter),
                        status=FeeDue.STATUS_PENDING,
                        paid_amount=Decimal('0.00'),
                        discount_amount=Decimal('0.00'),
                        fine_amount=Decimal('0.00')
                    )
                    db.session.add(specific_due)
                    db.session.flush()
                target_dues = [specific_due]
            else:
                # Auto-allocation mode: allocate to student's pending dues (oldest due first)
                pending_dues = FeeDue.query.filter(
                    FeeDue.student_id == student.id,
                    FeeDue.status != FeeDue.STATUS_PAID
                ).order_by(FeeDue.due_date.asc(), FeeDue.id.asc()).all()

                if not pending_dues:
                    # Auto-ensure quarterly dues from active fee structures
                    create_or_ensure_quarterly_dues(student, academic_session)
                    pending_dues = FeeDue.query.filter(
                        FeeDue.student_id == student.id,
                        FeeDue.status != FeeDue.STATUS_PAID
                    ).order_by(FeeDue.due_date.asc(), FeeDue.id.asc()).all()

                target_dues = pending_dues

            # Overpayment protection
            if target_dues:
                total_target_pending = sum(d.pending_amount for d in target_dues)
                if total_target_pending > Decimal('0.00') and amount > total_target_pending:
                    flash(
                        f'Payment amount ₹{amount:,.2f} exceeds outstanding due balance of ₹{total_target_pending:,.2f}. '
                        'Accidental overpayment is prevented.',
                        'warning'
                    )
                    return redirect(request.url)
            else:
                # Student has no dues at all; create a due for this payment
                ad_hoc_due = FeeDue(
                    student_id=student.id,
                    academic_session=academic_session,
                    quarter=quarter or current_qtr,
                    fee_component=fee_component,
                    amount=amount,
                    due_date=date.today(),
                    status=FeeDue.STATUS_PENDING,
                    paid_amount=Decimal('0.00'),
                    discount_amount=Decimal('0.00'),
                    fine_amount=Decimal('0.00')
                )
                db.session.add(ad_hoc_due)
                db.session.flush()
                target_dues = [ad_hoc_due]

            # Generate unique receipt number
            receipt_number = FeeTransaction.generate_receipt_number()

            # Determine fee_structure_id if available
            fee_structure_id = request.form.get('fee_structure_id', type=int) or None
            if not fee_structure_id and target_dues and target_dues[0].fee_structure_id:
                fee_structure_id = target_dues[0].fee_structure_id

            # Create transaction
            month_for_str = f"{quarter} ({academic_session})" if quarter else request.form.get('month_for', '').strip()
            payment_date = parse_date(request.form.get('payment_date')) or date.today()

            transaction = FeeTransaction(
                receipt_number=receipt_number,
                student_id=student_id,
                fee_structure_id=fee_structure_id,
                academic_session=academic_session,
                quarter=quarter or (target_dues[0].quarter if target_dues else current_qtr),
                fee_component=fee_component or (target_dues[0].fee_component if target_dues else 'Tuition Fee'),
                amount=amount,
                payment_date=payment_date,
                payment_mode=payment_mode,
                month_for=month_for_str,
                discount=discount,
                fine=fine,
                description=description,
                status=FeeTransaction.STATUS_SUCCESS,
                collected_by=current_user.id
            )

            # For cheque payments
            if payment_mode == 'CHEQUE':
                transaction.cheque_number = request.form.get('cheque_number', '').strip()
                transaction.cheque_date = parse_date(request.form.get('cheque_date'))
                transaction.bank_name = request.form.get('bank_name', '').strip()

            # For online payments
            if payment_mode in ['UPI', 'BANK_TRANSFER', 'CARD']:
                transaction.transaction_id = request.form.get('transaction_id', '').strip()

            db.session.add(transaction)
            db.session.flush()

            # Allocate payment across target dues
            remaining_to_allocate = amount
            remaining_discount = discount
            remaining_fine = fine

            for due in target_dues:
                if (remaining_to_allocate <= Decimal('0.00') and
                    remaining_discount <= Decimal('0.00') and
                    remaining_fine <= Decimal('0.00')):
                    break

                due_pending = due.pending_amount
                if due_pending > Decimal('0.00'):
                    alloc_amt = min(remaining_to_allocate, due_pending)
                else:
                    alloc_amt = remaining_to_allocate

                alloc_disc = min(remaining_discount, Decimal(str(due.amount)) - Decimal(str(due.discount_amount or 0))) if remaining_discount > 0 else Decimal('0.00')
                alloc_fine = remaining_fine

                allocation = FeePaymentAllocation(
                    transaction_id=transaction.id,
                    fee_due_id=due.id,
                    amount=alloc_amt,
                    discount_allocated=alloc_disc,
                    fine_allocated=alloc_fine
                )
                db.session.add(allocation)

                due.paid_amount = Decimal(str(due.paid_amount or 0)) + alloc_amt
                due.discount_amount = Decimal(str(due.discount_amount or 0)) + alloc_disc
                due.fine_amount = Decimal(str(due.fine_amount or 0)) + alloc_fine
                due.update_status()

                remaining_to_allocate -= alloc_amt
                remaining_discount -= alloc_disc
                remaining_fine -= alloc_fine

            db.session.commit()

            flash(f'Payment of ₹{amount:,.2f} received from {student.full_name}. Receipt: {receipt_number}', 'success')
            return redirect(url_for('fee.view_receipt', id=transaction.id))

        except Exception as e:
            db.session.rollback()
            flash(f'Error processing payment: {str(e)}', 'danger')

    # GET request
    fee_structures = FeeStructure.query.filter_by(is_active=True).all()
    batches = Batch.query.filter_by(is_active=True).all()

    # Pre-select student if provided
    student_id = request.args.get('student_id', type=int)
    selected_student = Student.query.get(student_id) if student_id else None
    student_summary = None
    if selected_student:
        # Ensure quarterly dues exist for student
        create_or_ensure_quarterly_dues(selected_student, current_session)
        student_summary = calculate_student_fee_summary(selected_student.id, current_session)

    # Build list of sessions
    current_year = date.today().year
    academic_sessions = [f"{y}-{str(y+1)[2:]}" for y in range(current_year - 1, current_year + 3)]

    return render_template('fee/collect.html',
        fee_structures=fee_structures,
        batches=batches,
        selected_student=selected_student,
        student_summary=student_summary,
        payment_modes=FeeTransaction.PAYMENT_MODES,
        academic_sessions=academic_sessions,
        current_session=current_session,
        current_quarter=current_qtr,
        quarters=QUARTERS,
        quarter_details=QUARTER_DETAILS,
        fee_components=FEE_COMPONENTS
    )


def _get_receipt_context(transaction):
    """Build complete data context for receipt views and PDFs"""
    student = transaction.student
    batch = student.batch if student else None

    # Get allocations or linked dues
    allocations = transaction.allocations

    # Calculate previous balance and remaining balance
    session = transaction.academic_session or get_current_academic_year()
    student_summary = calculate_student_fee_summary(student.id, session=session) if student else None

    # Remaining balance for the student
    remaining_balance = student_summary['outstanding_balance'] if student_summary else Decimal('0.00')

    # Previous balance before this transaction
    if transaction.status != FeeTransaction.STATUS_REVERSED:
        previous_balance = remaining_balance + Decimal(str(transaction.amount))
    else:
        previous_balance = remaining_balance

    amount_in_words = number_to_words_inr(transaction.amount)

    return {
        'transaction': transaction,
        'student': student,
        'batch': batch,
        'allocations': allocations,
        'student_summary': student_summary,
        'previous_balance': previous_balance,
        'remaining_balance': remaining_balance,
        'amount_in_words': amount_in_words,
        'school_name': current_app.config.get('SCHOOL_NAME', 'PM SHRI Kendriya Vidyalaya'),
        'school_tagline': current_app.config.get('SCHOOL_TAGLINE', 'Empowering Minds, Inspiring Futures'),
        'school_address': current_app.config.get('SCHOOL_ADDRESS', 'Ordnance Factory Estate, Itarsi'),
        'school_phone': current_app.config.get('SCHOOL_PHONE', '+91 98765 43210'),
        'school_email': current_app.config.get('SCHOOL_EMAIL', 'admin@amrita.com'),
        'school_affiliation': current_app.config.get('SCHOOL_AFFILIATION', 'CBSE / SGA-2024-889')
    }


@fee_bp.route('/receipt/<int:id>')
@login_required
def view_receipt(id):
    """View fee receipt with access control and full component breakdown"""
    transaction = FeeTransaction.query.get_or_404(id)

    # Access control: student can only view their own receipt; staff can view all
    if current_user.is_student():
        if not current_user.student or transaction.student_id != current_user.student.id:
            flash('You do not have permission to view this receipt.', 'danger')
            abort(403)
    elif not (current_user.is_admin() or current_user.is_teacher()):
        flash('You do not have permission to view this receipt.', 'danger')
        abort(403)

    context = _get_receipt_context(transaction)
    return render_template('fee/receipt.html', **context)


@fee_bp.route('/receipt/<int:id>/print')
@login_required
def print_receipt(id):
    """Dedicated printable receipt view"""
    transaction = FeeTransaction.query.get_or_404(id)

    if current_user.is_student():
        if not current_user.student or transaction.student_id != current_user.student.id:
            abort(403)
    elif not (current_user.is_admin() or current_user.is_teacher()):
        abort(403)

    context = _get_receipt_context(transaction)
    return render_template('fee/receipt_print.html', **context)


@fee_bp.route('/receipt/<int:id>/pdf')
@login_required
def download_receipt_pdf(id):
    """Download receipt as PDF using reportlab"""
    transaction = FeeTransaction.query.get_or_404(id)

    if current_user.is_student():
        if not current_user.student or transaction.student_id != current_user.student.id:
            abort(403)
    elif not (current_user.is_admin() or current_user.is_teacher()):
        abort(403)

    try:
        from reportlab.lib.pagesizes import letter, A4
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
        styles = getSampleStyleSheet()
        elements = []

        ctx = _get_receipt_context(transaction)

        # Header
        title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], alignment=1, fontSize=18, textColor=colors.HexColor('#1e3a8a'))
        elements.append(Paragraph(ctx['school_name'], title_style))
        sub_style = ParagraphStyle('SubStyle', parent=styles['Normal'], alignment=1, fontSize=10, textColor=colors.HexColor('#4b5563'))
        elements.append(Paragraph(f"{ctx['school_address']} | Tel: {ctx['school_phone']}", sub_style))
        elements.append(Paragraph(f"Affiliation: {ctx['school_affiliation']}", sub_style))
        elements.append(Spacer(1, 15))

        rec_title = ParagraphStyle('RecTitle', parent=styles['Heading2'], alignment=1, fontSize=14, textColor=colors.HexColor('#059669'))
        elements.append(Paragraph("FEE RECEIPT", rec_title))
        elements.append(Spacer(1, 10))

        # Meta table
        student = ctx['student']
        batch_name = ctx['batch'].name if ctx['batch'] else 'N/A'
        meta_data = [
            [f"Receipt No: {transaction.receipt_number}", f"Date: {transaction.payment_date.strftime('%d-%m-%Y')}"],
            [f"Student Name: {student.full_name if student else 'N/A'}", f"Student ID: {student.student_id if student else 'N/A'}"],
            [f"Parent Name: {student.parent_name or 'N/A' if student else 'N/A'}", f"Class / Batch: {batch_name}"],
            [f"Academic Session: {transaction.academic_session or 'N/A'}", f"Quarter: {transaction.quarter or 'N/A'}"],
            [f"Payment Mode: {transaction.payment_mode}", f"Status: {transaction.status}"]
        ]
        meta_table = Table(meta_data, colWidths=[260, 260])
        meta_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(meta_table)
        elements.append(Spacer(1, 15))

        # Component breakdown table
        table_data = [["Fee Component", "Quarter", "Amount (₹)"]]
        if ctx['allocations']:
            for alloc in ctx['allocations']:
                due = alloc.due
                comp = due.fee_component if due else transaction.fee_component or 'Fee Payment'
                qtr = due.quarter if due else transaction.quarter or '-'
                table_data.append([comp, qtr, f"₹{alloc.amount:,.2f}"])
        else:
            table_data.append([transaction.fee_component or 'Fee Payment', transaction.quarter or '-', f"₹{transaction.amount:,.2f}"])

        table_data.append(["Total Amount Paid", "", f"₹{transaction.amount:,.2f}"])
        if transaction.discount and transaction.discount > 0:
            table_data.append(["Discount / Adjustment", "", f"-₹{transaction.discount:,.2f}"])
        if transaction.fine and transaction.fine > 0:
            table_data.append(["Fine / Late Fee", "", f"+₹{transaction.fine:,.2f}"])
        table_data.append(["Remaining Outstanding Balance", "", f"₹{ctx['remaining_balance']:,.2f}"])

        comp_table = Table(table_data, colWidths=[260, 130, 130])
        comp_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f3f4f6')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
            ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(comp_table)
        elements.append(Spacer(1, 12))

        # Amount in words
        words_style = ParagraphStyle('Words', parent=styles['Normal'], fontSize=10, fontName='Helvetica-Oblique')
        elements.append(Paragraph(f"<b>Amount in Words:</b> {ctx['amount_in_words']}", words_style))
        elements.append(Spacer(1, 30))

        # Signature
        sig_data = [["", "_____________________________"], ["", "Authorized Cashier / Principal"]]
        sig_table = Table(sig_data, colWidths=[300, 220])
        sig_table.setStyle(TableStyle([
            ('ALIGN', (1, 0), (1, -1), 'CENTER'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
        ]))
        elements.append(sig_table)

        doc.build(elements)
        buffer.seek(0)

        response = make_response(buffer.getvalue())
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'inline; filename=receipt_{transaction.receipt_number}.pdf'
        return response
    except Exception as e:
        flash(f'Error generating PDF receipt: {str(e)}', 'warning')
        return redirect(url_for('fee.view_receipt', id=id))


@fee_bp.route('/transactions/<int:id>/reverse', methods=['POST'])
@login_required
@staff_required
def reverse_payment(id):
    """Clearly auditable payment reversal workflow"""
    transaction = FeeTransaction.query.get_or_404(id)
    reason = request.form.get('reason', '').strip()

    if not reason:
        flash('A clear reversal reason is required to reverse a payment.', 'warning')
        return redirect(url_for('fee.view_receipt', id=id))

    try:
        transaction.reverse(user_id=current_user.id, reason=reason)
        db.session.commit()
        flash(f'Receipt #{transaction.receipt_number} has been reversed. Linked dues have been updated.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error reversing payment: {str(e)}', 'danger')

    return redirect(url_for('fee.view_receipt', id=id))


@fee_bp.route('/transactions')
@login_required
@staff_required
def list_transactions():
    """List and search fee transactions with full-filtered totals"""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()
    student_id = request.args.get('student_id', type=int)
    receipt_number = request.args.get('receipt_number', '').strip()
    academic_session = request.args.get('academic_session', '').strip()
    quarter = request.args.get('quarter', '').strip()
    start_date = parse_date(request.args.get('start_date'))
    end_date = parse_date(request.args.get('end_date'))
    payment_mode = request.args.get('payment_mode', '').strip()
    status = request.args.get('status', '').strip()

    query = FeeTransaction.query

    if search:
        query = query.join(Student).filter(
            or_(
                Student.first_name.ilike(f'%{search}%'),
                Student.last_name.ilike(f'%{search}%'),
                (Student.first_name + ' ' + Student.last_name).ilike(f'%{search}%'),
                Student.student_id.ilike(f'%{search}%'),
                FeeTransaction.receipt_number.ilike(f'%{search}%')
            )
        )
    if student_id:
        query = query.filter(FeeTransaction.student_id == student_id)
    if receipt_number:
        query = query.filter(FeeTransaction.receipt_number.ilike(f'%{receipt_number}%'))
    if academic_session:
        query = query.filter(FeeTransaction.academic_session == academic_session)
    if quarter:
        query = query.filter(FeeTransaction.quarter == quarter)
    if start_date:
        query = query.filter(FeeTransaction.payment_date >= start_date)
    if end_date:
        query = query.filter(FeeTransaction.payment_date <= end_date)
    if payment_mode:
        query = query.filter(FeeTransaction.payment_mode == payment_mode)
    if status:
        query = query.filter(FeeTransaction.status == status)

    # Calculate totals across the ENTIRE filtered result, not just the page
    # Only sum non-reversed transactions for total collections
    total_amount = query.filter(
        FeeTransaction.status != FeeTransaction.STATUS_REVERSED
    ).with_entities(func.sum(FeeTransaction.amount)).scalar() or Decimal('0.00')

    total_count = query.count()

    query = query.order_by(FeeTransaction.created_at.desc())
    transactions = paginate_query(query, page)

    current_year = date.today().year
    academic_sessions = [f"{y}-{str(y+1)[2:]}" for y in range(current_year - 2, current_year + 3)]

    return render_template('fee/transactions.html',
        transactions=transactions,
        total_amount=total_amount,
        total_count=total_count,
        payment_modes=FeeTransaction.PAYMENT_MODES,
        academic_sessions=academic_sessions,
        quarters=QUARTERS,
        selected_search=search,
        selected_session=academic_session,
        selected_quarter=quarter,
        selected_mode=payment_mode,
        selected_status=status
    )


@fee_bp.route('/transactions/export-csv')
@login_required
@staff_required
def export_transactions_csv():
    """Export filtered fee transactions to CSV"""
    search = request.args.get('search', '').strip()
    academic_session = request.args.get('academic_session', '').strip()
    quarter = request.args.get('quarter', '').strip()
    payment_mode = request.args.get('payment_mode', '').strip()
    start_date = parse_date(request.args.get('start_date'))
    end_date = parse_date(request.args.get('end_date'))
    status = request.args.get('status', '').strip()

    query = FeeTransaction.query
    if search:
        query = query.join(Student).filter(
            or_(
                Student.first_name.ilike(f'%{search}%'),
                Student.last_name.ilike(f'%{search}%'),
                Student.student_id.ilike(f'%{search}%'),
                FeeTransaction.receipt_number.ilike(f'%{search}%')
            )
        )
    if academic_session:
        query = query.filter(FeeTransaction.academic_session == academic_session)
    if quarter:
        query = query.filter(FeeTransaction.quarter == quarter)
    if payment_mode:
        query = query.filter(FeeTransaction.payment_mode == payment_mode)
    if start_date:
        query = query.filter(FeeTransaction.payment_date >= start_date)
    if end_date:
        query = query.filter(FeeTransaction.payment_date <= end_date)
    if status:
        query = query.filter(FeeTransaction.status == status)

    transactions = query.order_by(FeeTransaction.payment_date.desc(), FeeTransaction.id.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'Receipt Number', 'Date', 'Student ID', 'Student Name', 'Batch',
        'Academic Session', 'Quarter', 'Fee Component', 'Amount (INR)',
        'Discount (INR)', 'Fine (INR)', 'Payment Mode', 'Reference / Cheque No',
        'Status', 'Collector'
    ])

    for t in transactions:
        student = t.student
        batch = student.batch.name if (student and student.batch) else '-'
        writer.writerow([
            t.receipt_number,
            t.payment_date.strftime('%Y-%m-%d'),
            student.student_id if student else '',
            student.full_name if student else '',
            batch,
            t.academic_session or '',
            t.quarter or '',
            t.fee_component or '',
            f"{t.amount:.2f}",
            f"{t.discount:.2f}" if t.discount else "0.00",
            f"{t.fine:.2f}" if t.fine else "0.00",
            t.payment_mode,
            t.transaction_id or t.cheque_number or '',
            t.status,
            t.collector.username if t.collector else ''
        ])

    output.seek(0)
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = f'attachment; filename=transactions_{date.today().strftime("%Y%m%d")}.csv'
    return response


@fee_bp.route('/pending')
@login_required
@staff_required
def pending_fees():
    """View pending fee dues using canonical session/quarter-aware FeeDue source of truth"""
    batch_id = request.args.get('batch_id', type=int)
    academic_session = request.args.get('academic_session', '').strip() or get_current_academic_year()
    quarter = request.args.get('quarter', '').strip()

    batches = Batch.query.filter_by(is_active=True).all()

    # Query fee dues directly
    due_query = FeeDue.query.join(Student).filter(
        FeeDue.status != FeeDue.STATUS_PAID,
        Student.status == 'ACTIVE'
    )

    if batch_id:
        due_query = due_query.filter(Student.batch_id == batch_id)
    if academic_session:
        due_query = due_query.filter(FeeDue.academic_session == academic_session)
    if quarter:
        due_query = due_query.filter(FeeDue.quarter == quarter)

    dues = due_query.order_by(FeeDue.due_date.asc()).all()

    # Group dues per student to display clean summary list
    student_dues_map = {}
    for d in dues:
        d.update_status()
        s_id = d.student_id
        if s_id not in student_dues_map:
            student_dues_map[s_id] = {
                'student': d.student,
                'expected': Decimal('0.00'),
                'paid': Decimal('0.00'),
                'pending': Decimal('0.00'),
                'overdue_count': 0,
                'quarters': set(),
                'dues': []
            }

        student_dues_map[s_id]['expected'] += d.net_due_amount
        student_dues_map[s_id]['paid'] += Decimal(str(d.paid_amount or 0))
        student_dues_map[s_id]['pending'] += d.pending_amount
        if d.is_overdue:
            student_dues_map[s_id]['overdue_count'] += 1
        if d.quarter:
            student_dues_map[s_id]['quarters'].add(d.quarter)
        student_dues_map[s_id]['dues'].append(d)

    pending_list = list(student_dues_map.values())
    pending_list.sort(key=lambda x: x['pending'], reverse=True)

    total_expected = sum(item['expected'] for item in pending_list)
    total_paid = sum(item['paid'] for item in pending_list)
    total_pending = sum(item['pending'] for item in pending_list)

    current_year = date.today().year
    academic_sessions = [f"{y}-{str(y+1)[2:]}" for y in range(current_year - 2, current_year + 3)]

    return render_template('fee/pending.html',
        batches=batches,
        selected_batch=batch_id,
        selected_session=academic_session,
        selected_quarter=quarter,
        pending_list=pending_list,
        total_expected=total_expected,
        total_paid=total_paid,
        total_pending=total_pending,
        academic_sessions=academic_sessions,
        quarters=QUARTERS
    )


@fee_bp.route('/pending/export-csv')
@login_required
@staff_required
def export_pending_csv():
    """Export pending fee dues to CSV"""
    batch_id = request.args.get('batch_id', type=int)
    academic_session = request.args.get('academic_session', '').strip()
    quarter = request.args.get('quarter', '').strip()

    query = FeeDue.query.join(Student).filter(
        FeeDue.status != FeeDue.STATUS_PAID,
        Student.status == 'ACTIVE'
    )
    if batch_id:
        query = query.filter(Student.batch_id == batch_id)
    if academic_session:
        query = query.filter(FeeDue.academic_session == academic_session)
    if quarter:
        query = query.filter(FeeDue.quarter == quarter)

    dues = query.order_by(FeeDue.due_date.asc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'Student ID', 'Student Name', 'Batch', 'Academic Session', 'Quarter',
        'Fee Component', 'Due Date', 'Assessed Amount (INR)', 'Discount (INR)',
        'Fine (INR)', 'Net Amount (INR)', 'Paid Amount (INR)', 'Pending Balance (INR)',
        'Status'
    ])

    for d in dues:
        s = d.student
        b = s.batch.name if (s and s.batch) else '-'
        writer.writerow([
            s.student_id if s else '',
            s.full_name if s else '',
            b,
            d.academic_session or '',
            d.quarter or '',
            d.fee_component or '',
            d.due_date.strftime('%Y-%m-%d'),
            f"{d.amount:.2f}",
            f"{d.discount_amount:.2f}",
            f"{d.fine_amount:.2f}",
            f"{d.net_due_amount:.2f}",
            f"{d.paid_amount:.2f}",
            f"{d.pending_amount:.2f}",
            d.status
        ])

    output.seek(0)
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = f'attachment; filename=pending_fees_{date.today().strftime("%Y%m%d")}.csv'
    return response


@fee_bp.route('/defaulters')
@login_required
@staff_required
def defaulters():
    """Fee defaulters list (dues that have passed due date)"""
    today = date.today()

    overdue = FeeDue.query.filter(
        FeeDue.due_date < today,
        FeeDue.status != FeeDue.STATUS_PAID
    ).order_by(FeeDue.due_date.asc()).all()

    for d in overdue:
        d.update_status()

    total_overdue_amount = sum(d.pending_amount for d in overdue)

    return render_template('fee/defaulters.html',
        overdue=overdue,
        total_overdue_amount=total_overdue_amount,
        today=today
    )


# Fee Structure Management (Admin Only)

@fee_bp.route('/structure')
@login_required
@staff_required
def list_structures():
    """List fee structures configured by batch, session, and component"""
    academic_session = request.args.get('academic_session', '').strip()
    batch_id = request.args.get('batch_id', type=int)

    query = FeeStructure.query
    if academic_session:
        query = query.filter(FeeStructure.academic_session == academic_session)
    if batch_id:
        query = query.filter(FeeStructure.batch_id == batch_id)

    structures = query.order_by(FeeStructure.academic_session.desc(), FeeStructure.name.asc()).all()
    batches = Batch.query.filter_by(is_active=True).all()

    current_year = date.today().year
    academic_sessions = [f"{y}-{str(y+1)[2:]}" for y in range(current_year - 1, current_year + 3)]

    return render_template('fee/structures.html',
        structures=structures,
        batches=batches,
        selected_batch=batch_id,
        selected_session=academic_session,
        academic_sessions=academic_sessions
    )


@fee_bp.route('/structure/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_structure():
    """Add fee structure (admin only)"""
    current_session = get_current_academic_year()

    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            batch_id = request.form.get('batch_id', type=int) or None
            academic_session = request.form.get('academic_session', current_session).strip() or current_session
            fee_component = request.form.get('fee_component', 'Tuition Fee').strip() or 'Tuition Fee'
            quarter = request.form.get('quarter', '').strip() or None
            amount = Decimal(request.form.get('amount', '0'))
            frequency = request.form.get('frequency', FeeStructure.FREQ_QUARTERLY).strip()
            description = request.form.get('description', '').strip()

            if not name:
                name = f"{fee_component} ({academic_session})"

            if amount <= Decimal('0.00'):
                flash('Fee amount must be greater than zero.', 'danger')
                return redirect(request.url)

            structure = FeeStructure(
                name=name,
                batch_id=batch_id,
                academic_session=academic_session,
                fee_component=fee_component,
                quarter=quarter,
                amount=amount,
                frequency=frequency,
                description=description,
                is_active=True
            )
            db.session.add(structure)
            db.session.commit()

            flash(f'Fee structure "{structure.name}" created successfully!', 'success')
            return redirect(url_for('fee.list_structures'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error creating fee structure: {str(e)}', 'danger')

    batches = Batch.query.filter_by(is_active=True).all()
    current_year = date.today().year
    academic_sessions = [f"{y}-{str(y+1)[2:]}" for y in range(current_year - 1, current_year + 3)]

    return render_template('fee/add_structure.html',
        batches=batches,
        frequencies=FeeStructure.FREQUENCIES,
        academic_sessions=academic_sessions,
        current_session=current_session,
        fee_components=FEE_COMPONENTS,
        quarters=QUARTERS
    )


@fee_bp.route('/structure/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_structure(id):
    """Edit fee structure (admin only)"""
    structure = FeeStructure.query.get_or_404(id)

    if request.method == 'POST':
        try:
            structure.name = request.form.get('name', '').strip()
            structure.batch_id = request.form.get('batch_id', type=int) or None
            structure.academic_session = request.form.get('academic_session', structure.academic_session).strip()
            structure.fee_component = request.form.get('fee_component', structure.fee_component).strip()
            structure.quarter = request.form.get('quarter', '').strip() or None
            structure.amount = Decimal(request.form.get('amount', '0'))
            structure.frequency = request.form.get('frequency', FeeStructure.FREQ_QUARTERLY)
            structure.description = request.form.get('description', '').strip()
            structure.is_active = 'is_active' in request.form

            db.session.commit()
            flash('Fee structure updated successfully!', 'success')
            return redirect(url_for('fee.list_structures'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error updating fee structure: {str(e)}', 'danger')

    batches = Batch.query.filter_by(is_active=True).all()
    current_year = date.today().year
    academic_sessions = [f"{y}-{str(y+1)[2:]}" for y in range(current_year - 1, current_year + 3)]

    return render_template('fee/edit_structure.html',
        structure=structure,
        batches=batches,
        frequencies=FeeStructure.FREQUENCIES,
        academic_sessions=academic_sessions,
        fee_components=FEE_COMPONENTS,
        quarters=QUARTERS
    )


@fee_bp.route('/structure/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_structure(id):
    """Delete fee structure safely (admin only)"""
    structure = FeeStructure.query.get_or_404(id)
    structure_name = structure.name

    try:
        transaction_count = FeeTransaction.query.filter_by(fee_structure_id=id).count()
        if transaction_count > 0:
            flash(
                f'Cannot delete "{structure_name}" - it has {transaction_count} associated historical transaction(s). '
                'Deactivate it instead to preserve audit history.',
                'warning'
            )
            return redirect(url_for('fee.list_structures'))

        db.session.delete(structure)
        db.session.commit()
        flash(f'Fee structure "{structure_name}" deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting fee structure: {str(e)}', 'danger')

    return redirect(url_for('fee.list_structures'))


@fee_bp.route('/dues/generate', methods=['POST'])
@login_required
@admin_required
def generate_batch_dues():
    """Admin tool to generate Q1–Q4 dues for all students in a batch for an academic session"""
    batch_id = request.form.get('batch_id', type=int)
    academic_session = request.form.get('academic_session', '').strip() or get_current_academic_year()

    if not batch_id:
        flash('Please select a batch to generate dues.', 'warning')
        return redirect(url_for('fee.list_structures'))

    batch = Batch.query.get_or_404(batch_id)
    students = Student.query.filter_by(batch_id=batch.id, status='ACTIVE').all()

    total_created = 0
    for s in students:
        created = create_or_ensure_quarterly_dues(s, academic_session)
        total_created += len(created)

    flash(f'Generated {total_created} quarterly due(s) across {len(students)} student(s) in {batch.name} for session {academic_session}.', 'success')
    return redirect(url_for('fee.pending_fees', batch_id=batch.id, academic_session=academic_session))


# Reports & Ledger

@fee_bp.route('/report')
@login_required
@staff_required
def fee_report():
    """Fee collection report by day, month, quarter, session, component, and mode"""
    month = request.args.get('month', date.today().month, type=int)
    year = request.args.get('year', date.today().year, type=int)
    academic_session = request.args.get('academic_session', '').strip()
    quarter = request.args.get('quarter', '').strip()

    # Base query for successful collections
    query = FeeTransaction.query.filter(
        FeeTransaction.status != FeeTransaction.STATUS_REVERSED
    )

    if academic_session:
        query = query.filter(FeeTransaction.academic_session == academic_session)
    if quarter:
        query = query.filter(FeeTransaction.quarter == quarter)

    # Date range for monthly breakdown
    first_day = date(year, month, 1)
    if month == 12:
        last_day = date(year + 1, 1, 1)
    else:
        last_day = date(year, month + 1, 1)

    # Month collection
    month_query = query.filter(
        FeeTransaction.payment_date >= first_day,
        FeeTransaction.payment_date < last_day
    )
    total = month_query.with_entities(func.sum(FeeTransaction.amount)).scalar() or Decimal('0.00')

    # Payment mode-wise breakdown for the month
    mode_breakdown = month_query.with_entities(
        FeeTransaction.payment_mode,
        func.sum(FeeTransaction.amount).label('total'),
        func.count(FeeTransaction.id).label('count')
    ).group_by(FeeTransaction.payment_mode).all()

    # Daily collection for the month
    daily_collection = month_query.with_entities(
        FeeTransaction.payment_date,
        func.sum(FeeTransaction.amount).label('total')
    ).group_by(FeeTransaction.payment_date).order_by(FeeTransaction.payment_date).all()

    # Quarter-wise breakdown for session
    session_for_qtr = academic_session or get_current_academic_year()
    quarter_breakdown = db.session.query(
        FeeTransaction.quarter,
        func.sum(FeeTransaction.amount).label('total'),
        func.count(FeeTransaction.id).label('count')
    ).filter(
        FeeTransaction.academic_session == session_for_qtr,
        FeeTransaction.status != FeeTransaction.STATUS_REVERSED
    ).group_by(FeeTransaction.quarter).all()

    # Component breakdown for session
    component_breakdown = db.session.query(
        FeeTransaction.fee_component,
        func.sum(FeeTransaction.amount).label('total'),
        func.count(FeeTransaction.id).label('count')
    ).filter(
        FeeTransaction.academic_session == session_for_qtr,
        FeeTransaction.status != FeeTransaction.STATUS_REVERSED
    ).group_by(FeeTransaction.fee_component).all()

    current_year = date.today().year
    academic_sessions = [f"{y}-{str(y+1)[2:]}" for y in range(current_year - 2, current_year + 3)]

    return render_template('fee/report.html',
        month=month,
        year=year,
        months=get_months_list(),
        total=total,
        mode_breakdown=mode_breakdown,
        daily_collection=daily_collection,
        quarter_breakdown=quarter_breakdown,
        component_breakdown=component_breakdown,
        academic_sessions=academic_sessions,
        selected_session=academic_session,
        selected_quarter=quarter,
        current_session=session_for_qtr
    )


@fee_bp.route('/report/export-csv')
@login_required
@staff_required
def export_report_csv():
    """Export collection report breakdown to CSV"""
    month = request.args.get('month', date.today().month, type=int)
    year = request.args.get('year', date.today().year, type=int)

    first_day = date(year, month, 1)
    last_day = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)

    daily = db.session.query(
        FeeTransaction.payment_date,
        func.sum(FeeTransaction.amount).label('total'),
        func.count(FeeTransaction.id).label('count')
    ).filter(
        FeeTransaction.payment_date >= first_day,
        FeeTransaction.payment_date < last_day,
        FeeTransaction.status != FeeTransaction.STATUS_REVERSED
    ).group_by(FeeTransaction.payment_date).order_by(FeeTransaction.payment_date).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([f'Daily Collection Report - {month}/{year}'])
    writer.writerow(['Date', 'Transactions Count', 'Total Collection (INR)'])

    grand_total = Decimal('0.00')
    grand_count = 0
    for day, amt, cnt in daily:
        writer.writerow([day.strftime('%Y-%m-%d'), cnt, f"{amt:.2f}"])
        grand_total += amt
        grand_count += cnt

    writer.writerow([])
    writer.writerow(['Grand Total', grand_count, f"{grand_total:.2f}"])

    output.seek(0)
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = f'attachment; filename=collection_report_{year}_{month}.csv'
    return response


@fee_bp.route('/report/export-excel')
@login_required
@staff_required
def export_report_excel():
    """Export collection report to Excel using openpyxl"""
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

        month = request.args.get('month', date.today().month, type=int)
        year = request.args.get('year', date.today().year, type=int)

        first_day = date(year, month, 1)
        last_day = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)

        daily = db.session.query(
            FeeTransaction.payment_date,
            func.sum(FeeTransaction.amount).label('total'),
            func.count(FeeTransaction.id).label('count')
        ).filter(
            FeeTransaction.payment_date >= first_day,
            FeeTransaction.payment_date < last_day,
            FeeTransaction.status != FeeTransaction.STATUS_REVERSED
        ).group_by(FeeTransaction.payment_date).order_by(FeeTransaction.payment_date).all()

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = f"Report {month}-{year}"

        # Title
        ws.merge_cells('A1:C1')
        ws['A1'] = f"PM SHRI Kendriya Vidyalaya - Monthly Collection Report ({month}/{year})"
        ws['A1'].font = Font(size=14, bold=True, color="1E3A8A")
        ws['A1'].alignment = Alignment(horizontal='center')

        # Headers
        headers = ['Date', 'Transactions Count', 'Total Collection (₹)']
        ws.append([])
        ws.append(headers)

        header_fill = PatternFill(start_color="10B981", end_color="10B981", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True)
        for col_num in range(1, 4):
            cell = ws.cell(row=3, column=col_num)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center' if col_num < 3 else 'right')

        grand_total = Decimal('0.00')
        grand_count = 0
        row_idx = 4
        for day, amt, cnt in daily:
            ws.append([day.strftime('%d-%m-%Y'), cnt, float(amt)])
            ws.cell(row=row_idx, column=3).number_format = '#,##0.00'
            grand_total += amt
            grand_count += cnt
            row_idx += 1

        # Summary Row
        ws.append(['Grand Total', grand_count, float(grand_total)])
        ws.cell(row=row_idx, column=1).font = Font(bold=True)
        ws.cell(row=row_idx, column=2).font = Font(bold=True)
        cell_total = ws.cell(row=row_idx, column=3)
        cell_total.font = Font(bold=True)
        cell_total.number_format = '#,##0.00'

        # Auto-adjust column width
        ws.column_dimensions['A'].width = 18
        ws.column_dimensions['B'].width = 22
        ws.column_dimensions['C'].width = 25

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        response = make_response(output.getvalue())
        response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        response.headers['Content-Disposition'] = f'attachment; filename=collection_report_{year}_{month}.xlsx'
        return response
    except Exception as e:
        flash(f'Error generating Excel report: {str(e)}. Using CSV fallback.', 'warning')
        return redirect(url_for('fee.export_report_csv', month=month, year=year))


@fee_bp.route('/student-details/<int:student_id>')
@login_required
@staff_required
def get_student_fee_details(student_id):
    """Get fee details for a specific student via AJAX using unified source of truth"""
    student = Student.query.get_or_404(student_id)
    session = request.args.get('session', get_current_academic_year())

    # Ensure quarterly dues exist
    create_or_ensure_quarterly_dues(student, session)

    # Calculate unified summary
    summary = calculate_student_fee_summary(student.id, session=session)

    dues_data = []
    for d in summary['dues']:
        dues_data.append({
            'id': d.id,
            'academic_session': d.academic_session,
            'quarter': d.quarter or 'N/A',
            'fee_component': d.fee_component or 'Tuition Fee',
            'amount': float(d.amount),
            'discount': float(d.discount_amount or 0),
            'fine': float(d.fine_amount or 0),
            'net_due': float(d.net_due_amount),
            'paid': float(d.paid_amount or 0),
            'pending': float(d.pending_amount),
            'status': d.status,
            'due_date': d.due_date.strftime('%d-%m-%Y'),
            'is_overdue': d.is_overdue
        })

    response = {
        'status': 'success',
        'student': {
            'id': student.id,
            'student_id': student.student_id,
            'name': student.full_name,
            'batch_id': student.batch_id,
            'batch_name': student.batch.name if student.batch else 'No Batch',
            'parent_name': student.parent_name or '',
            'parent_phone': student.parent_phone or ''
        },
        'summary': {
            'total_assessed': float(summary['total_assessed']),
            'total_discount': float(summary['total_discount']),
            'total_fine': float(summary['total_fine']),
            'total_net_due': float(summary['total_net_due']),
            'total_paid': float(summary['total_paid']),
            'outstanding_balance': float(summary['outstanding_balance']),
            'has_pending': summary['has_pending']
        },
        'dues': dues_data
    }

    return Response(
        response=json.dumps(response),
        status=200,
        mimetype='application/json'
    )
