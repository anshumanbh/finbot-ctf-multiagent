from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from src.models.user import db

class Vendor(db.Model):
    __tablename__ = 'vendors'
    
    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(200), nullable=False)
    contact_person = db.Column(db.String(100), nullable=False)
    contact_email = db.Column(db.String(120), nullable=False, unique=True)
    phone_number = db.Column(db.String(20), nullable=False)
    business_type = db.Column(db.String(50), nullable=False)
    vendor_category = db.Column(db.Text, nullable=False)  # JSON string of categories
    tax_id = db.Column(db.String(50), nullable=False)
    bank_name = db.Column(db.String(100), nullable=False)
    account_holder_name = db.Column(db.String(100), nullable=False)
    account_number = db.Column(db.String(50), nullable=False)
    routing_number = db.Column(db.String(20), nullable=False)
    services_description = db.Column(db.Text)
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    trust_level = db.Column(db.String(20), default='standard')  # low, standard, high
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship with invoices
    invoices = db.relationship('Invoice', backref='vendor', lazy=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'company_name': self.company_name,
            'contact_person': self.contact_person,
            'contact_email': self.contact_email,
            'phone_number': self.phone_number,
            'business_type': self.business_type,
            'vendor_category': self.vendor_category,
            'tax_id': self.tax_id,
            'bank_name': self.bank_name,
            'account_holder_name': self.account_holder_name,
            'account_number': self.account_number,
            'routing_number': self.routing_number,
            'services_description': self.services_description,
            'status': self.status,
            'trust_level': self.trust_level,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class Invoice(db.Model):
    __tablename__ = 'invoices'
    
    id = db.Column(db.Integer, primary_key=True)
    vendor_id = db.Column(db.Integer, db.ForeignKey('vendors.id'), nullable=False)
    invoice_number = db.Column(db.String(50), nullable=False, unique=True)
    amount = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text, nullable=False)
    invoice_date = db.Column(db.Date, nullable=False)
    due_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), default='submitted')  # submitted, processing, approved, rejected, paid
    ai_decision = db.Column(db.String(20))  # auto_approve, flag_review, reject
    ai_confidence = db.Column(db.Float)  # 0.0 to 1.0
    ai_reasoning = db.Column(db.Text)
    human_reviewer = db.Column(db.String(100))
    human_decision = db.Column(db.String(20))  # approve, reject
    human_notes = db.Column(db.Text)
    payment_processed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    processed_at = db.Column(db.DateTime)
    
    contains_content_anomaly = db.Column(db.Boolean, default=False)
    scenario_marker_set = db.Column(db.Boolean, default=False)
    
    def to_dict(self):
        return {
            'id': self.id,
            'vendor_id': self.vendor_id,
            'invoice_number': self.invoice_number,
            'amount': self.amount,
            'description': self.description,
            'invoice_date': self.invoice_date.isoformat() if self.invoice_date else None,
            'due_date': self.due_date.isoformat() if self.due_date else None,
            'status': self.status,
            'ai_decision': self.ai_decision,
            'ai_confidence': self.ai_confidence,
            'ai_reasoning': self.ai_reasoning,
            'human_reviewer': self.human_reviewer,
            'human_decision': self.human_decision,
            'human_notes': self.human_notes,
            'payment_processed': self.payment_processed,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'processed_at': self.processed_at.isoformat() if self.processed_at else None,
            'contains_content_anomaly': self.contains_content_anomaly,
            'scenario_marker_set': self.scenario_marker_set
        }

class FinBotConfig(db.Model):
    __tablename__ = 'finbot_config'
    
    id = db.Column(db.Integer, primary_key=True)
    auto_approve_threshold = db.Column(db.Float, default=1000.0)  # Auto approve under this amount
    manual_review_threshold = db.Column(db.Float, default=5000.0)  # Require manual review over this amount
    confidence_threshold = db.Column(db.Float, default=0.8)  # AI confidence threshold for auto approval
    speed_priority = db.Column(db.Float, default=0.7)  # 0.0 = rigor focused, 1.0 = speed focused
    integrity_checks_enabled = db.Column(db.Boolean, default=True)
    custom_goals = db.Column(db.Text, default=None)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'auto_approve_threshold': self.auto_approve_threshold,
            'manual_review_threshold': self.manual_review_threshold,
            'confidence_threshold': self.confidence_threshold,
            'speed_priority': self.speed_priority,
            'integrity_checks_enabled': self.integrity_checks_enabled,
            'custom_goals': self.custom_goals,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

