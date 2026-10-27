"""
Helper Functions
"""
import os
from datetime import datetime
from flask import current_app


def format_currency(amount):
    """Format amount as Indian Rupee"""
    if amount is None:
        return "₹0.00"
    return f"₹{float(amount):,.2f}"


def format_date(date_obj, format_str=None):
    """Format date object to string"""
    if date_obj is None:
        return ""
    if format_str is None:
        format_str = current_app.config.get('DATE_FORMAT', '%d-%m-%Y')
    if isinstance(date_obj, str):
        return date_obj
    return date_obj.strftime(format_str)


def format_datetime(dt_obj, format_str=None):
    """Format datetime object to string"""
    if dt_obj is None:
        return ""
    if format_str is None:
        format_str = current_app.config.get('DATETIME_FORMAT', '%d-%m-%Y %H:%M')
    return dt_obj.strftime(format_str)


def allowed_file(filename):
    """Check if file extension is allowed"""
    if '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in current_app.config.get('ALLOWED_EXTENSIONS', {'png', 'jpg', 'jpeg', 'gif'})


def save_uploaded_file(file, folder='uploads'):
    """Save uploaded file and return path"""
    if file and allowed_file(file.filename):
        from werkzeug.utils import secure_filename
        filename = secure_filename(file.filename)
        
        # Add timestamp to filename to make it unique
        name, ext = os.path.splitext(filename)
        filename = f"{name}_{datetime.now().strftime('%Y%m%d%H%M%S')}{ext}"
        
        upload_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], folder)
        os.makedirs(upload_folder, exist_ok=True)
        
        filepath = os.path.join(upload_folder, filename)
        file.save(filepath)
        
        return os.path.join(folder, filename)
    return None


def parse_date(date_str, format_str='%Y-%m-%d'):
    """Parse date string to date object"""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, format_str).date()
    except ValueError:
        return None


def get_current_academic_year():
    """Get current academic year string (e.g., '2026-27')"""
    today = datetime.now()
    if today.month >= 4:  # April onwards is new academic year
        return f"{today.year}-{str(today.year + 1)[2:]}"
    return f"{today.year - 1}-{str(today.year)[2:]}"


# Canonical academic quarters
QUARTERS = ['Q1', 'Q2', 'Q3', 'Q4']

QUARTER_DETAILS = {
    'Q1': {'name': 'Q1 (Apr - Jun)', 'months': (4, 6), 'due_month': 4, 'due_day': 10},
    'Q2': {'name': 'Q2 (Jul - Sep)', 'months': (7, 9), 'due_month': 7, 'due_day': 10},
    'Q3': {'name': 'Q3 (Oct - Dec)', 'months': (10, 12), 'due_month': 10, 'due_day': 10},
    'Q4': {'name': 'Q4 (Jan - Mar)', 'months': (1, 3), 'due_month': 1, 'due_day': 10},
}

FEE_COMPONENTS = [
    'Tuition Fee',
    'Admission Fee',
    'Examination Fee',
    'Transport Fee',
    'Library Fee',
    'Laboratory Fee',
    'Computer / IT Fee',
    'Other Charges'
]


def get_current_quarter(date_obj=None):
    """Get quarter for a given date (default today)"""
    if date_obj is None:
        date_obj = datetime.now()
    month = date_obj.month
    if 4 <= month <= 6:
        return 'Q1'
    elif 7 <= month <= 9:
        return 'Q2'
    elif 10 <= month <= 12:
        return 'Q3'
    else:
        return 'Q4'


def get_quarter_due_date(session_str, quarter):
    """
    Compute standard due date for a session and quarter.
    session_str: '2026-27'
    quarter: 'Q1' -> 2026-04-10
             'Q2' -> 2026-07-10
             'Q3' -> 2026-10-10
             'Q4' -> 2027-01-10
    """
    from datetime import date
    try:
        start_year = int(session_str.split('-')[0])
    except Exception:
        start_year = datetime.now().year
    
    details = QUARTER_DETAILS.get(quarter, QUARTER_DETAILS['Q1'])
    due_month = details['due_month']
    due_year = start_year if due_month >= 4 else start_year + 1
    return date(due_year, due_month, details['due_day'])


def number_to_words_inr(number):
    """Convert number to Indian Currency words (Rupees and Paise)"""
    try:
        from decimal import Decimal
        num = Decimal(str(number or 0))
    except Exception:
        return ""
    
    if num <= 0:
        return "Zero Rupees Only"
    
    units = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
             "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
             "Seventeen", "Eighteen", "Nineteen"]
    tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]

    def _convert_below_thousand(n):
        res = []
        if n >= 100:
            res.append(units[n // 100] + " Hundred")
            n %= 100
        if n >= 20:
            res.append(tens[n // 10])
            n %= 10
        if n > 0:
            res.append(units[n])
        return " ".join(res).strip()

    rupees = int(num)
    paise = int(round((num - rupees) * 100))

    parts = []
    # Crores (10,000,000)
    if rupees >= 10000000:
        crores = rupees // 10000000
        parts.append(_convert_below_thousand(crores) + " Crore")
        rupees %= 10000000

    # Lakhs (100,000)
    if rupees >= 100000:
        lakhs = rupees // 100000
        parts.append(_convert_below_thousand(lakhs) + " Lakh")
        rupees %= 100000

    # Thousands (1,000)
    if rupees >= 1000:
        thousands = rupees // 1000
        parts.append(_convert_below_thousand(thousands) + " Thousand")
        rupees %= 1000

    # Remaining hundreds, tens, units
    if rupees > 0:
        parts.append(_convert_below_thousand(rupees))

    rupee_words = " ".join(parts).strip()
    result = f"{rupee_words} Rupees" if rupee_words else ""

    if paise > 0:
        paise_words = _convert_below_thousand(paise)
        if result:
            result += f" and {paise_words} Paise"
        else:
            result = f"{paise_words} Paise"

    return (result + " Only").strip()


def get_months_list():
    """Get list of months with their names"""
    return [
        (1, 'January'), (2, 'February'), (3, 'March'),
        (4, 'April'), (5, 'May'), (6, 'June'),
        (7, 'July'), (8, 'August'), (9, 'September'),
        (10, 'October'), (11, 'November'), (12, 'December')
    ]


def paginate_query(query, page, per_page=None):
    """Paginate SQLAlchemy query"""
    if per_page is None:
        per_page = current_app.config.get('ITEMS_PER_PAGE', 20)
    return query.paginate(page=page, per_page=per_page, error_out=False)
