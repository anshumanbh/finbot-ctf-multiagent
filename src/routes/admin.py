from flask import Blueprint, request, jsonify, render_template
from src.models.vendor import db, Vendor, Invoice, FinBotConfig
from src.services.finbot_agent import FinBotAgent
from src.services.multi_agent_finbot import MultiAgentFinBot
from datetime import datetime

admin_bp = Blueprint('admin', __name__)

# DO NOT initialize here

@admin_bp.route('/admin/invoices/pending', methods=['GET'])
def get_pending_invoices():
    """Get all invoices pending human review"""
    invoices = Invoice.query.filter_by(status='pending_review').order_by(Invoice.created_at.desc()).all()
    
    result = []
    for invoice in invoices:
        invoice_data = invoice.to_dict()
        vendor = Vendor.query.get(invoice.vendor_id)
        invoice_data['vendor_name'] = vendor.company_name if vendor else 'Unknown'
        invoice_data['vendor_trust_level'] = vendor.trust_level if vendor else 'unknown'
        result.append(invoice_data)
    
    return jsonify(result)

@admin_bp.route('/admin/invoices/<int:invoice_id>/review', methods=['POST'])
def review_invoice(invoice_id):
    """Human review of flagged invoice"""
    try:
        invoice = Invoice.query.get(invoice_id)
        if not invoice:
            return jsonify({"error": "Invoice not found"}), 404
        
        data = request.get_json()
        decision = data.get('decision')  # 'approve' or 'reject'
        notes = data.get('notes', '')
        reviewer = data.get('reviewer', 'Admin')
        
        if decision not in ['approve', 'reject']:
            return jsonify({"error": "Decision must be 'approve' or 'reject'"}), 400
        
        # Update invoice
        invoice.human_reviewer = reviewer
        invoice.human_decision = decision
        invoice.human_notes = notes
        
        if decision == 'approve':
            invoice.status = 'approved'
            invoice.payment_processed = True
        else:
            invoice.status = 'rejected'
        
        invoice.processed_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            "success": True,
            "invoice_id": invoice_id,
            "decision": decision,
            "message": f"Invoice {decision}d successfully"
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@admin_bp.route('/admin/finbot/config', methods=['GET'])
def get_finbot_config():
    """Get current FinBot configuration"""
    config = FinBotConfig.query.first()
    if not config:
        config = FinBotConfig()
        db.session.add(config)
        db.session.commit()
    return jsonify(config.to_dict())

@admin_bp.route('/admin/finbot/config', methods=['POST'])
def update_finbot_config():
    """Update FinBot configuration"""
    try:
        data = request.get_json()
        
        config = FinBotConfig.query.first()
        if not config:
            config = FinBotConfig()
            db.session.add(config)
        
        if 'auto_approve_threshold' in data:
            config.auto_approve_threshold = data['auto_approve_threshold']
        if 'manual_review_threshold' in data:
            config.manual_review_threshold = data['manual_review_threshold']
        if 'confidence_threshold' in data:
            config.confidence_threshold = data['confidence_threshold']
        if 'speed_priority' in data:
            config.speed_priority = data['speed_priority']
        if 'integrity_checks_enabled' in data:
            config.integrity_checks_enabled = data['integrity_checks_enabled']
        if 'custom_goals' in data:
            config.custom_goals = data['custom_goals']
        
        config.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            "success": True,
            "config": config.to_dict(),
            "message": "FinBot configuration updated successfully"
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin_bp.route('/admin/finbot/goals', methods=['POST'])
def update_finbot_goals():
    """Update FinBot goals"""
    try:
        data = request.get_json()
        
        if 'goals' not in data:
            return jsonify({"error": "Goals field is required"}), 400
        
        config = FinBotConfig.query.first()
        if not config:
            config = FinBotConfig()
            db.session.add(config)
        
        config.custom_goals = data['goals']
        config.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "FinBot goals updated successfully",
            "new_goals": data['goals']
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin_bp.route('/admin/finbot/reprocess/<int:invoice_id>', methods=['POST'])
def reprocess_invoice(invoice_id):
    """Reprocess an invoice with FinBot"""
    try:
        invoice = Invoice.query.get(invoice_id)
        if not invoice:
            return jsonify({"error": "Invoice not found"}), 404
        
        # Reset invoice status
        invoice.status = 'submitted'
        invoice.ai_decision = None
        invoice.ai_confidence = None
        invoice.ai_reasoning = None
        invoice.processed_at = None
        db.session.commit()
        
        # Use multi-agent system
        multi_agent_finbot = MultiAgentFinBot()
        result = multi_agent_finbot.process_invoice(invoice_id)
        
        return jsonify({
            "success": True,
            "invoice_id": invoice_id,
            "processing_result": result
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@admin_bp.route('/admin/dashboard', methods=['GET'])
def get_dashboard_stats():
    """Get dashboard statistics"""
    try:
        total_invoices = Invoice.query.count()
        pending_review = Invoice.query.filter_by(status='pending_review').count()
        approved = Invoice.query.filter_by(status='approved').count()
        rejected = Invoice.query.filter_by(status='rejected').count()
        processing = Invoice.query.filter_by(status='processing').count()
        
        scenario_markers_set = Invoice.query.filter_by(scenario_marker_set=True).count()
        content_anomalies_detected = Invoice.query.filter_by(contains_content_anomaly=True).count()
        
        # Recent invoices
        recent_invoices = Invoice.query.order_by(Invoice.created_at.desc()).limit(10).all()
        recent_data = []
        for invoice in recent_invoices:
            invoice_data = invoice.to_dict()
            vendor = Vendor.query.get(invoice.vendor_id)
            invoice_data['vendor_name'] = vendor.company_name if vendor else 'Unknown'
            recent_data.append(invoice_data)
        
        return jsonify({
            "stats": {
                "total_invoices": total_invoices,
                "pending_review": pending_review,
                "approved": approved,
                "rejected": rejected,
                "processing": processing,
                "scenario_markers_set": scenario_markers_set,
                "content_anomalies_detected": content_anomalies_detected
            },
            "recent_invoices": recent_data
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin_bp.route('/admin/scenario/markers', methods=['GET'])
def get_scenario_markers():
    """Get all invoices with scenario markers set"""
    flagged_invoices = Invoice.query.filter_by(scenario_marker_set=True).all()
    
    result = []
    for invoice in flagged_invoices:
        invoice_data = invoice.to_dict()
        vendor = Vendor.query.get(invoice.vendor_id)
        invoice_data['vendor_name'] = vendor.company_name if vendor else 'Unknown'
        result.append(invoice_data)
    
    return jsonify(result)

@admin_bp.route('/admin/vendors/<int:vendor_id>/trust', methods=['POST'])
def update_vendor_trust(vendor_id):
    """Update vendor trust level"""
    try:
        vendor = Vendor.query.get(vendor_id)
        if not vendor:
            return jsonify({"error": "Vendor not found"}), 404
        
        data = request.get_json()
        trust_level = data.get('trust_level')
        
        if trust_level not in ['low', 'standard', 'high']:
            return jsonify({"error": "Trust level must be 'low', 'standard', or 'high'"}), 400
        
        vendor.trust_level = trust_level
        db.session.commit()
        
        return jsonify({
            "success": True,
            "vendor_id": vendor_id,
            "trust_level": trust_level,
            "message": "Vendor trust level updated successfully"
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@admin_bp.route('/log-agreement', methods=['POST'])
def log_agreement():
    """Log user agreement for audit purposes"""
    try:
        data = request.get_json()
        
        # Log agreement data (you can store this in database if needed)
        agreement_log = {
            'agreed': data.get('agreed', False),
            'timestamp': data.get('timestamp'),
            'user_agent': data.get('userAgent'),
            'referrer': data.get('referrer'),
            'ip_address': request.remote_addr
        }
        
        # For now, just log to console (implement database storage if needed)
        print(f"User Agreement Logged: {agreement_log}")
        
        return jsonify({"success": True, "message": "Agreement logged successfully"})
        
    except Exception as e:
        print(f"Error logging agreement: {e}")
        return jsonify({"error": "Failed to log agreement"}), 500