"""
Fee Management Models
"""
from datetime import datetime, date
from decimal import Decimal
from app import db
from app.utils.helpers import get_current_academic_year, get_quarter_due_date, QUARTERS


class FeeStructure(db.Model):
    """Fee structure definition"""
    __tablename__ = 'fee_structures'
    
    # Frequency constants
    FREQ_MONTHLY = 'MONTHLY'
    FREQ_QUARTERLY = 'QUARTERLY'
    FREQ_YEARLY = 'YEARLY'
    FREQ_ONE_TIME = 'ONE_TIME'
    
    FREQUENCIES = [FREQ_QUARTERLY, FREQ_MONTHLY, FREQ_YEARLY, FREQ_ONE_TIME]
    
    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.Integer, db.ForeignKey('batches.id'), nullable=True)
    academic_session = db.Column(db.String(20), nullable=True, default=get_current_academic_year, index=True)
    fee_component = db.Column(db.String(50), nullable=True, default='Tuition Fee')
    quarter = db.Column(db.String(10), nullable=True)  # Optional specific quarter (e.g., 'Q1') or None for all
    name = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    frequency = db.Column(db.String(20), default=FREQ_QUARTERLY)
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    transactions = db.relationship('FeeTransaction', backref='fee_structure', lazy=True)
    
    @property
    def component_name(self):
        """Get component name fallback"""
        return self.fee_component or self.name or 'Tuition Fee'
    
    def __repr__(self):
        return f'<FeeStructure {self.name} ({self.academic_session}): ₹{self.amount}>'


class FeeTransaction(db.Model):
    """Fee payment transactions"""
    __tablename__ = 'fee_transactions'
    
    # Payment mode constants
    MODE_CASH = 'CASH'
    MODE_CHEQUE = 'CHEQUE'
    MODE_UPI = 'UPI'
    MODE_CARD = 'CARD'
    MODE_BANK_TRANSFER = 'BANK_TRANSFER'
    
    PAYMENT_MODES = [MODE_CASH, MODE_CHEQUE, MODE_UPI, MODE_CARD, MODE_BANK_TRANSFER]
    
    # Transaction status constants
    STATUS_SUCCESS = 'SUCCESS'
    STATUS_REVERSED = 'REVERSED'
    
    id = db.Column(db.Integer, primary_key=True)
    receipt_number = db.Column(db.String(30), unique=True, nullable=False, index=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False, index=True)
    fee_structure_id = db.Column(db.Integer, db.ForeignKey('fee_structures.id'), nullable=True)
    
    # Academic session and quarter context
    academic_session = db.Column(db.String(20), nullable=True, index=True)
    quarter = db.Column(db.String(10), nullable=True)  # e.g., 'Q1', 'Q2', etc.
    fee_component = db.Column(db.String(50), nullable=True)
    
    # Payment details
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    payment_date = db.Column(db.Date, nullable=False, default=date.today)
    payment_mode = db.Column(db.String(20), default=MODE_CASH)
    
    # For specific payment modes
    cheque_number = db.Column(db.String(50))
    cheque_date = db.Column(db.Date)
    bank_name = db.Column(db.String(100))
    transaction_id = db.Column(db.String(100))  # For UPI/Online payments
    
    # Additional info
    description = db.Column(db.String(255))
    month_for = db.Column(db.String(50))  # Optional legacy or quarter display string
    discount = db.Column(db.Numeric(10, 2), default=0)
    fine = db.Column(db.Numeric(10, 2), default=0)
    
    # Transaction Status and Reversal tracking
    status = db.Column(db.String(20), default=STATUS_SUCCESS, index=True)
    reversal_reason = db.Column(db.String(255), nullable=True)
    reversed_at = db.Column(db.DateTime, nullable=True)
    reversed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    # Collected by
    collected_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    collector = db.relationship('User', foreign_keys=[collected_by], backref='fees_collected')
    reverser = db.relationship('User', foreign_keys=[reversed_by], backref='fees_reversed')
    
    @staticmethod
    def generate_receipt_number():
        """Generate unique receipt number"""
        today = datetime.now()
        prefix = f"REC{today.strftime('%Y%m%d')}"
        
        # Get last receipt matching today's prefix
        last_receipt = FeeTransaction.query.filter(
            FeeTransaction.receipt_number.like(f'{prefix}%')
        ).order_by(FeeTransaction.id.desc()).first()
        
        if last_receipt:
            try:
                last_num = int(last_receipt.receipt_number[len(prefix):])
                new_num = last_num + 1
            except Exception:
                new_num = 1
        else:
            new_num = 1
        
        candidate = f"{prefix}{new_num:04d}"
        # Ensure absolute uniqueness in case of race conditions
        while FeeTransaction.query.filter_by(receipt_number=candidate).first():
            new_num += 1
            candidate = f"{prefix}{new_num:04d}"
        return candidate
    
    @property
    def net_amount(self):
        """Calculate net amount using Decimal arithmetic"""
        amt = Decimal(str(self.amount or 0))
        disc = Decimal(str(self.discount or 0))
        fn = Decimal(str(self.fine or 0))
        return amt - disc + fn
    
    @property
    def is_reversed(self):
        """Check if transaction is reversed"""
        return self.status == self.STATUS_REVERSED
    
    def reverse(self, user_id, reason):
        """Reverses this transaction and restores balances on linked dues"""
        if self.status == self.STATUS_REVERSED:
            raise ValueError("This transaction has already been reversed.")
        
        self.status = self.STATUS_REVERSED
        self.reversal_reason = reason
        self.reversed_at = datetime.utcnow()
        self.reversed_by = user_id
        
        # Restore amounts on linked dues
        for alloc in self.allocations:
            due = alloc.due
            if due:
                alloc_amt = Decimal(str(alloc.amount or 0))
                alloc_disc = Decimal(str(alloc.discount_allocated or 0))
                alloc_fine = Decimal(str(alloc.fine_allocated or 0))
                
                due.paid_amount = max(Decimal('0.00'), Decimal(str(due.paid_amount or 0)) - alloc_amt)
                due.discount_amount = max(Decimal('0.00'), Decimal(str(due.discount_amount or 0)) - alloc_disc)
                due.fine_amount = max(Decimal('0.00'), Decimal(str(due.fine_amount or 0)) - alloc_fine)
                due.update_status()
                
        return True
    
    def __repr__(self):
        return f'<FeeTransaction {self.receipt_number}: ₹{self.amount} ({self.status})>'


class FeeDue(db.Model):
    """Track pending fee dues"""
    __tablename__ = 'fee_dues'
    
    STATUS_PENDING = 'PENDING'
    STATUS_PAID = 'PAID'
    STATUS_PARTIAL = 'PARTIAL'
    STATUS_OVERDUE = 'OVERDUE'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False, index=True)
    fee_structure_id = db.Column(db.Integer, db.ForeignKey('fee_structures.id'), nullable=True)
    
    # Session, quarter, component
    academic_session = db.Column(db.String(20), nullable=True, index=True)
    quarter = db.Column(db.String(10), nullable=True, index=True)  # 'Q1', 'Q2', 'Q3', 'Q4'
    fee_component = db.Column(db.String(50), nullable=True, default='Tuition Fee')
    
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    due_date = db.Column(db.Date, nullable=False)
    month_for = db.Column(db.String(50))
    status = db.Column(db.String(20), default=STATUS_PENDING, index=True)
    
    # Financial breakdown (Decimal)
    paid_amount = db.Column(db.Numeric(10, 2), default=0)
    discount_amount = db.Column(db.Numeric(10, 2), default=0)
    fine_amount = db.Column(db.Numeric(10, 2), default=0)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships - cascade delete ensures fee dues are removed when student is deleted
    student = db.relationship('Student', backref=db.backref('fee_dues', lazy='dynamic', cascade='all, delete-orphan'))
    fee_structure = db.relationship('FeeStructure', backref='dues')
    
    @property
    def net_due_amount(self):
        """Net assessed due amount including discounts and fines"""
        amt = Decimal(str(self.amount or 0))
        disc = Decimal(str(self.discount_amount or 0))
        fn = Decimal(str(self.fine_amount or 0))
        return max(Decimal('0.00'), amt - disc + fn)
    
    @property
    def pending_amount(self):
        """Get remaining pending amount using Decimal arithmetic"""
        paid = Decimal(str(self.paid_amount or 0))
        return max(Decimal('0.00'), self.net_due_amount - paid)
    
    @property
    def is_overdue(self):
        """Check if fee is overdue"""
        return self.due_date < date.today() and self.status != self.STATUS_PAID
    
    def update_status(self):
        """Update and return the canonical status of this due"""
        net = self.net_due_amount
        paid = Decimal(str(self.paid_amount or 0))
        
        if paid >= net and net > Decimal('0.00'):
            self.status = self.STATUS_PAID
        elif paid > Decimal('0.00'):
            self.status = self.STATUS_PARTIAL
        elif self.due_date < date.today():
            self.status = self.STATUS_OVERDUE
        else:
            self.status = self.STATUS_PENDING
        return self.status
    
    def __repr__(self):
        return f'<FeeDue {self.student_id} - {self.fee_component} {self.quarter} ({self.academic_session}): ₹{self.amount} due {self.due_date}>'


class FeePaymentAllocation(db.Model):
    """Allocates a payment transaction to a specific fee due"""
    __tablename__ = 'fee_payment_allocations'
    
    id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(db.Integer, db.ForeignKey('fee_transactions.id', ondelete='CASCADE'), nullable=False, index=True)
    fee_due_id = db.Column(db.Integer, db.ForeignKey('fee_dues.id', ondelete='CASCADE'), nullable=False, index=True)
    
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    discount_allocated = db.Column(db.Numeric(10, 2), default=0)
    fine_allocated = db.Column(db.Numeric(10, 2), default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    transaction = db.relationship('FeeTransaction', backref=db.backref('allocations', cascade='all, delete-orphan', lazy=True))
    due = db.relationship('FeeDue', backref=db.backref('allocations', cascade='all, delete-orphan', lazy=True))
    
    def __repr__(self):
        return f'<FeePaymentAllocation Txn:{self.transaction_id} -> Due:{self.fee_due_id}: ₹{self.amount}>'


# Service functions for unified single-source-of-truth calculations
def calculate_student_fee_summary(student_id, session=None):
    """
    Unified Single Source of Truth for Student Fee Ledger and Outstanding Balance.
    Calculates:
    - total_assessed
    - total_discount
    - total_fine
    - total_net_due
    - total_paid
    - outstanding_balance
    - dues list with individual statuses and pending balances
    """
    query = FeeDue.query.filter_by(student_id=student_id)
    if session:
        query = query.filter_by(academic_session=session)
        
    dues = query.order_by(FeeDue.due_date.asc(), FeeDue.id.asc()).all()
    
    total_assessed = Decimal('0.00')
    total_discount = Decimal('0.00')
    total_fine = Decimal('0.00')
    total_paid = Decimal('0.00')
    total_net_due = Decimal('0.00')
    outstanding_balance = Decimal('0.00')
    
    for due in dues:
        due.update_status()
        amt = Decimal(str(due.amount or 0))
        disc = Decimal(str(due.discount_amount or 0))
        fn = Decimal(str(due.fine_amount or 0))
        paid = Decimal(str(due.paid_amount or 0))
        net = due.net_due_amount
        pending = due.pending_amount
        
        total_assessed += amt
        total_discount += disc
        total_fine += fn
        total_paid += paid
        total_net_due += net
        outstanding_balance += pending
        
    return {
        'total_assessed': total_assessed,
        'total_discount': total_discount,
        'total_fine': total_fine,
        'total_net_due': total_net_due,
        'total_paid': total_paid,
        'outstanding_balance': outstanding_balance,
        'dues': dues,
        'has_pending': outstanding_balance > Decimal('0.00')
    }


def create_or_ensure_quarterly_dues(student, academic_session=None):
    """
    Ensure Q1–Q4 (and one-time/annual) dues exist for a student's batch
    for the specified academic session without duplicate creation.
    """
    if not student.batch_id:
        return []
        
    session = academic_session or get_current_academic_year()
    structures = FeeStructure.query.filter(
        FeeStructure.is_active.is_(True),
        (FeeStructure.batch_id == student.batch_id) | (FeeStructure.batch_id.is_(None)),
        (FeeStructure.academic_session == session) | (FeeStructure.academic_session.is_(None))
    ).all()
    
    created_dues = []
    
    for structure in structures:
        comp = structure.fee_component or structure.name or 'Tuition Fee'
        freq = (structure.frequency or FeeStructure.FREQ_QUARTERLY).upper()
        amt = Decimal(str(structure.amount))
        
        if freq == FeeStructure.FREQ_QUARTERLY:
            for q in QUARTERS:
                existing = FeeDue.query.filter_by(
                    student_id=student.id,
                    academic_session=session,
                    quarter=q,
                    fee_component=comp
                ).first()
                if not existing:
                    due = FeeDue(
                        student_id=student.id,
                        fee_structure_id=structure.id,
                        academic_session=session,
                        quarter=q,
                        fee_component=comp,
                        amount=amt,
                        due_date=get_quarter_due_date(session, q),
                        status=FeeDue.STATUS_PENDING,
                        paid_amount=Decimal('0.00'),
                        discount_amount=Decimal('0.00'),
                        fine_amount=Decimal('0.00')
                    )
                    due.update_status()
                    db.session.add(due)
                    created_dues.append(due)
        elif freq in [FeeStructure.FREQ_ONE_TIME, FeeStructure.FREQ_YEARLY]:
            existing = FeeDue.query.filter_by(
                student_id=student.id,
                academic_session=session,
                quarter='Q1',
                fee_component=comp
            ).first()
            if not existing:
                due = FeeDue(
                    student_id=student.id,
                    fee_structure_id=structure.id,
                    academic_session=session,
                    quarter='Q1',
                    fee_component=comp,
                    amount=amt,
                    due_date=get_quarter_due_date(session, 'Q1'),
                    status=FeeDue.STATUS_PENDING,
                    paid_amount=Decimal('0.00'),
                    discount_amount=Decimal('0.00'),
                    fine_amount=Decimal('0.00')
                )
                due.update_status()
                db.session.add(due)
                created_dues.append(due)
                
    if created_dues:
        db.session.commit()
    return created_dues
