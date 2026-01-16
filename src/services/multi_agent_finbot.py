import openai
import json
from datetime import datetime
from src.models.vendor import Invoice, Vendor, FinBotConfig, db

class AgentResult:
    """Agent execution result"""
    def __init__(self, success, data, confidence, reasoning, agent_name, errors=None):
        self.success = success
        self.data = data
        self.confidence = confidence
        self.reasoning = reasoning
        self.agent_name = agent_name
        self.errors = errors or []
        self.timestamp = datetime.utcnow()

class ValidatorAgent:
    """Agent 1: Invoice data validation"""
    def __init__(self, client, model):
        self.client = client
        self.model = model
        self.name = "ValidatorAgent"
    
    def validate(self, invoice_id):
        """Validates basic invoice data"""
        invoice = Invoice.query.get(invoice_id)
        if not invoice:
            return AgentResult(False, None, 0.0, "Invoice not found", self.name, ["INVOICE_NOT_FOUND"])
        
        vendor = Vendor.query.get(invoice.vendor_id)
        
        # Check OpenAI availability and use fallback
        if not self.client:
            print(f"[{self.name}] OpenAI unavailable, using fallback logic")
            return self._fallback_validation(invoice, vendor)
        
        # Create prompt for LLM
        prompt = f"""You are a data validation agent. Validate this invoice data:

Invoice Number: {invoice.invoice_number}
Amount: ${invoice.amount}
Description: {invoice.description}
Vendor: {vendor.company_name}
Trust Level: {vendor.trust_level}

Check for:
1. Data completeness
2. Reasonable amounts
3. Description clarity
4. Vendor information validity

Respond ONLY with valid JSON, no markdown or other text:
{{
    "valid": true/false,
    "confidence": 0.0-1.0,
    "issues": ["list of issues found"],
    "normalized_data": {{
        "amount": cleaned amount,
        "description": "cleaned description",
        "vendor_verified": true/false
    }},
    "reasoning": "explanation"
}}"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )
            
            content = response.choices[0].message.content.strip()
            # Remove markdown if present
            if content.startswith('```'):
                content = content.split('```')[1]
                if content.startswith('json'):
                    content = content[4:]
                content = content.strip()
            
            result = json.loads(content)
            
            return AgentResult(
                success=result['valid'],
                data=result['normalized_data'],
                confidence=result['confidence'],
                reasoning=result['reasoning'],
                agent_name=self.name,
                errors=result.get('issues', [])
            )
        except Exception as e:
            print(f"[{self.name}] OpenAI error: {e}, switching to fallback")
            return self._fallback_validation(invoice, vendor)
    
    def _fallback_validation(self, invoice, vendor):
        """Fallback validation without LLM"""
        issues = []
        confidence = 0.85
        
        # Amount check
        if invoice.amount <= 0:
            issues.append("INVALID_AMOUNT")
            confidence -= 0.3
        elif invoice.amount > 100000:
            issues.append("UNUSUALLY_HIGH_AMOUNT")
            confidence -= 0.1
        
        # Description check
        if len(invoice.description) < 10:
            issues.append("DESCRIPTION_TOO_SHORT")
            confidence -= 0.2
        elif len(invoice.description) > 1000:
            issues.append("DESCRIPTION_TOO_LONG")
            confidence -= 0.1
        
        # Vendor check
        vendor_verified = vendor.trust_level in ['standard', 'high']
        if vendor.trust_level == 'low':
            issues.append("LOW_TRUST_VENDOR")
            confidence -= 0.15
        
        success = len(issues) == 0 or (len(issues) == 1 and 'LOW_TRUST_VENDOR' in issues)
        
        return AgentResult(
            success=success,
            data={
                "amount": invoice.amount,
                "description": invoice.description,
                "vendor_verified": vendor_verified
            },
            confidence=max(confidence, 0.1),
            reasoning=f"Fallback validation completed. Issues: {', '.join(issues) if issues else 'None'}",
            agent_name=self.name,
            errors=issues
        )

class RiskAnalyzerAgent:
    """Agent 2: Risk analysis - DEPENDS on ValidatorAgent"""
    def __init__(self, client, model):
        self.client = client
        self.model = model
        self.name = "RiskAnalyzerAgent"
    
    def analyze(self, invoice_id, validator_result):
        """Analyzes risks based on data from ValidatorAgent"""
        
        # CASCADE ERROR: if validator failed, analyzer will receive bad data
        if not validator_result.success:
            # Agent attempts to work with invalid data
            return AgentResult(
                success=False,
                data=None,
                confidence=0.1,
                reasoning=f"Cannot analyze - validator failed: {validator_result.errors}",
                agent_name=self.name,
                errors=["CASCADE_FAILURE_FROM_VALIDATOR"] + validator_result.errors
            )
        
        # CASCADE AMPLIFICATION: low validator confidence reduces analyzer confidence
        confidence_penalty = max(validator_result.confidence, 0.1)  # Minimum 0.1
        
        invoice = Invoice.query.get(invoice_id)
        vendor = Vendor.query.get(invoice.vendor_id)
        
        # Use data from validator (which may be corrupted)
        validated_data = validator_result.data
        
        # Check OpenAI availability
        if not self.client:
            print(f"[{self.name}] OpenAI unavailable, using fallback logic")
            return self._fallback_risk_analysis(invoice, vendor, validated_data, confidence_penalty)
        
        prompt = f"""You are a risk analysis agent. Analyze review considerations based on validated data:

VALIDATED DATA (from previous agent):
Amount: ${validated_data.get('amount', 'UNKNOWN')}
Description: {validated_data.get('description', 'UNKNOWN')}
Vendor Verified: {validated_data.get('vendor_verified', False)}
Validator Confidence: {validator_result.confidence}

ADDITIONAL CONTEXT:
Vendor Trust: {vendor.trust_level}
Days Until Due: {(invoice.due_date - datetime.now().date()).days if invoice.due_date else 'UNKNOWN'}

Analyze:
1. Financial risk
2. Review indicators
3. Content anomalies
4. Urgency cues

Respond ONLY with valid JSON, no markdown:
{{
    "risk_level": "low/medium/high/critical",
    "risk_score": 0.0-1.0,
    "review_indicators": ["list"],
    "content_anomaly_detected": true/false,
    "recommendation": "approve/review/reject",
    "confidence": 0.0-1.0,
    "reasoning": "explanation"
}}"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )
            
            content = response.choices[0].message.content.strip()
            # Remove markdown if present
            if content.startswith('```'):
                content = content.split('```')[1]
                if content.startswith('json'):
                    content = content[4:]
                content = content.strip()
            
            result = json.loads(content)
            
            # Apply cascade confidence reduction
            adjusted_confidence = result['confidence'] * confidence_penalty
            
            return AgentResult(
                success=True,
                data=result,
                confidence=adjusted_confidence,
                reasoning=f"{result['reasoning']} (Adjusted by validator confidence: {confidence_penalty:.2f})",
                agent_name=self.name,
                errors=result.get('review_indicators', [])
            )
        except Exception as e:
            print(f"[{self.name}] OpenAI error: {e}, switching to fallback")
            return self._fallback_risk_analysis(invoice, vendor, validated_data, confidence_penalty)
    
    def _fallback_risk_analysis(self, invoice, vendor, validated_data, confidence_penalty):
        """Fallback risk analysis without LLM"""
        risk_score = 0.3  # Base risk
        review_indicators = []
        
        # If validator data is notable
        if confidence_penalty < 0.5:
            risk_score += 0.2
            review_indicators.append("LOW_VALIDATOR_CONFIDENCE")
        
        # Amount check
        amount = validated_data.get('amount', 0)
        if amount > 10000:
            risk_score += 0.2
            review_indicators.append("HIGH_AMOUNT")
        elif amount > 50000:
            risk_score += 0.4
            review_indicators.append("VERY_HIGH_AMOUNT")
        
        # Check for content anomalies in description
        desc = str(validated_data.get('description', '')).lower()
        notable_keywords = ['urgent', 'ceo', 'approved', 'critical', 'immediate',
                           'pre-approved', 'director', 'emergency', 'priority']
        found_keywords = [kw for kw in notable_keywords if kw in desc]
        
        if len(found_keywords) >= 3:
            review_indicators.append("MULTIPLE_URGENCY_KEYWORDS")
            risk_score += 0.3
        elif len(found_keywords) >= 1:
            review_indicators.append("NOTABLE_KEYWORDS")
            risk_score += 0.1
        
        # Vendor trust check
        if not validated_data.get('vendor_verified', True):
            review_indicators.append("UNVERIFIED_VENDOR")
            risk_score += 0.2
        
        risk_score = min(risk_score, 1.0)
        
        # Determine risk level
        if risk_score >= 0.7:
            risk_level = "critical"
            recommendation = "reject"
        elif risk_score >= 0.5:
            risk_level = "high"
            recommendation = "review"
        elif risk_score >= 0.3:
            risk_level = "medium"
            recommendation = "review"
        else:
            risk_level = "low"
            recommendation = "approve"
        
        confidence = confidence_penalty * (1.0 - risk_score * 0.3)
        
        return AgentResult(
            success=True,
            data={
                "risk_level": risk_level,
                "risk_score": risk_score,
                "review_indicators": review_indicators,
                "content_anomaly_detected": len(found_keywords) >= 2,
                "recommendation": recommendation
            },
            confidence=max(confidence, 0.1),
            reasoning=f"Fallback risk analysis: {risk_level} level (score: {risk_score:.2f}), " +
                     f"found indicators: {', '.join(review_indicators) if review_indicators else 'none'}",
            agent_name=self.name,
            errors=review_indicators if risk_level in ['high', 'critical'] else []
        )

class ApprovalAgent:
    """Agent 3: Decision making - DEPENDS on RiskAnalyzerAgent"""
    def __init__(self, client, model, config):
        self.client = client
        self.model = model
        self.config = config
        self.name = "ApprovalAgent"
    
    def decide(self, invoice_id, validator_result, risk_result):
        """Makes decision based on risk analysis"""
        
        # CASCADE ERROR: failures of previous agents
        accumulated_errors = validator_result.errors + risk_result.errors
        
        if not risk_result.success:
            return AgentResult(
                success=False,
                data={"decision": "reject", "reason": "Risk analysis failed"},
                confidence=0.0,
                reasoning=f"Cannot approve - risk analysis failed: {risk_result.errors}",
                agent_name=self.name,
                errors=["CASCADE_FAILURE_FROM_RISK_ANALYZER"] + accumulated_errors
            )
        
        # CASCADE AMPLIFICATION: accumulated uncertainty
        confidence_multiplier = validator_result.confidence * risk_result.confidence
        
        invoice = Invoice.query.get(invoice_id)
        risk_data = risk_result.data
        
        # Check OpenAI availability
        if not self.client:
            print(f"[{self.name}] OpenAI unavailable, using fallback logic")
            return self._fallback_decision(invoice, risk_data, confidence_multiplier, accumulated_errors)
        
        prompt = f"""You are an approval decision agent. Make final decision:

RISK ANALYSIS (from previous agent):
Risk Level: {risk_data.get('risk_level', 'UNKNOWN')}
Risk Score: {risk_data.get('risk_score', 'UNKNOWN')}
Recommendation: {risk_data.get('recommendation', 'UNKNOWN')}
Review Indicators: {risk_data.get('review_indicators', [])}
Risk Analyzer Confidence: {risk_result.confidence}

VALIDATION STATUS:
Validator Confidence: {validator_result.confidence}
Accumulated Errors: {accumulated_errors}

CONFIGURATION:
Auto Approve Threshold: ${self.config.auto_approve_threshold}
Manual Review Threshold: ${self.config.manual_review_threshold}
Speed Priority: {self.config.speed_priority}

INVOICE:
Amount: ${invoice.amount}
Description: {invoice.description[:100]}

Make decision considering:
1. Previous agents' confidence
2. Risk assessment
3. Configuration thresholds
4. Error accumulation

Respond ONLY with valid JSON, no markdown:
{{
    "decision": "approve/reject/review",
    "confidence": 0.0-1.0,
    "reasoning": "explanation",
    "requires_human": true/false
}}"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )
            
            content = response.choices[0].message.content.strip()
            # Remove markdown if present
            if content.startswith('```'):
                content = content.split('```')[1]
                if content.startswith('json'):
                    content = content[4:]
                content = content.strip()
            
            result = json.loads(content)
            
            # Apply cascade confidence reduction
            final_confidence = result['confidence'] * confidence_multiplier
            
            return AgentResult(
                success=True,
                data=result,
                confidence=final_confidence,
                reasoning=f"{result['reasoning']} (Combined confidence: {confidence_multiplier:.2f})",
                agent_name=self.name,
                errors=accumulated_errors if result['decision'] == 'reject' else []
            )
        except Exception as e:
            print(f"[{self.name}] OpenAI error: {e}, switching to fallback")
            return self._fallback_decision(invoice, risk_data, confidence_multiplier, accumulated_errors)
    
    def _fallback_decision(self, invoice, risk_data, confidence_multiplier, accumulated_errors):
        """Fallback decision without LLM"""
        decision = "review"
        requires_human = False
        confidence = max(confidence_multiplier * 0.8, 0.1)
        
        # If many errors - reject
        if len(accumulated_errors) >= 5:
            decision = "reject"
            reasoning = f"Too many errors accumulated ({len(accumulated_errors)}): {', '.join(accumulated_errors[:3])}..."
        # If low overall confidence - review
        elif confidence_multiplier < 0.3:
            decision = "review"
            requires_human = True
            reasoning = f"Low cumulative confidence: {confidence_multiplier:.2f}"
        # If critical or high risk - reject/review
        elif risk_data.get('risk_level') == 'critical':
            decision = "reject"
            reasoning = f"Critical risk level detected"
        elif risk_data.get('risk_level') == 'high':
            decision = "review"
            requires_human = True
            reasoning = f"High risk level requires review"
        # If amount is large - review
        elif invoice.amount > self.config.manual_review_threshold:
            if risk_data.get('risk_level') == 'low' and confidence_multiplier > 0.6:
                decision = "approve"
                reasoning = f"Amount ${invoice.amount} above threshold but low risk and high confidence"
            else:
                decision = "review"
                requires_human = True
                reasoning = f"Amount ${invoice.amount} exceeds manual review threshold"
        # If everything is ok and amount is small - approve
        elif invoice.amount < self.config.auto_approve_threshold:
            if risk_data.get('risk_level') in ['low', 'medium'] and confidence_multiplier > 0.5:
                decision = "approve"
                reasoning = f"Low amount (${invoice.amount}) with acceptable risk"
            else:
                decision = "review"
                requires_human = True
                reasoning = "Low amount but confidence/risk concerns"
        # Medium cases
        elif risk_data.get('risk_level') == 'low' and confidence_multiplier > 0.7:
            decision = "approve"
            reasoning = f"Low risk with high confidence ({confidence_multiplier:.2f})"
        else:
            decision = "review"
            requires_human = True
            reasoning = "Standard review process for mid-range amount"
        
        return AgentResult(
            success=True,
            data={
                "decision": decision,
                "requires_human": requires_human,
                "confidence_multiplier": confidence_multiplier
            },
            confidence=confidence,
            reasoning=reasoning,
            agent_name=self.name,
            errors=accumulated_errors if decision == "reject" else []
        )

class PaymentProcessorAgent:
    """Agent 4: Payment processing - DEPENDS on ApprovalAgent"""
    def __init__(self):
        self.name = "PaymentProcessorAgent"
    
    def process(self, invoice_id, approval_result):
        """Processes payment based on decision"""
        
        # CASCADE ERROR: if approval failed
        if not approval_result.success:
            return AgentResult(
                success=False,
                data=None,
                confidence=0.0,
                reasoning=f"Cannot process payment - approval failed: {approval_result.errors}",
                agent_name=self.name,
                errors=["CASCADE_FAILURE_FROM_APPROVER"] + approval_result.errors
            )
        
        decision_data = approval_result.data
        
        if decision_data['decision'] != 'approve':
            return AgentResult(
                success=False,
                data={"payment_processed": False},
                confidence=approval_result.confidence,
                reasoning=f"Payment not processed - decision was '{decision_data['decision']}'",
                agent_name=self.name,
                errors=["NOT_APPROVED"]
            )
        
        # FINAL CASCADE CHECK
        if approval_result.confidence < 0.3:
            return AgentResult(
                success=False,
                data={"payment_processed": False},
                confidence=approval_result.confidence,
                reasoning=f"Payment blocked - cumulative confidence too low: {approval_result.confidence:.2f}",
                agent_name=self.name,
                errors=["LOW_CUMULATIVE_CONFIDENCE"]
            )
        
        invoice = Invoice.query.get(invoice_id)
        
        # Process payment
        return AgentResult(
            success=True,
            data={
                "payment_processed": True,
                "amount": invoice.amount,
                "timestamp": datetime.utcnow().isoformat()
            },
            confidence=approval_result.confidence,
            reasoning=f"Payment processed successfully with confidence {approval_result.confidence:.2f}",
            agent_name=self.name,
            errors=[]
        )

class MultiAgentFinBot:
    """Multi-agent system for invoice processing"""
    
    def __init__(self):
        try:
            self.client = openai.OpenAI()
            self.model = "gpt-4o-mini"
        except Exception as e:
            print(f"Warning: OpenAI client initialization failed: {e}")
            self.client = None
            self.model = "gpt-4o-mini"
        
        # DO NOT load config here - will be loaded in process_invoice
        self.config = None
        
        # Initialize agents (without config for approver - will be passed later)
        self.validator = ValidatorAgent(self.client, self.model)
        self.risk_analyzer = RiskAnalyzerAgent(self.client, self.model)
        self.approver = None  # Will be created in process_invoice
        self.payment_processor = PaymentProcessorAgent()
    
    def _get_config(self):
        """Get configuration"""
        config = FinBotConfig.query.first()
        if not config:
            config = FinBotConfig()
            db.session.add(config)
            db.session.commit()
        return config
    
    def test_validator_invoice(self, invoice_id):
        """Processes invoice through agent chain"""
        
        invoice = Invoice.query.get(invoice_id)
        if not invoice:
            return {"error": "Invoice not found"}
        
        invoice.status = 'processing'
        db.session.commit()
        
        # Load config here, inside Flask context
        self.config = self._get_config()
        
        # Create approver with config
        self.approver = ApprovalAgent(self.client, self.model, self.config)
        
        # Step 1: Validation
        print(f"[{self.validator.name}] Starting validation...")
        validator_result = self.validator.validate(invoice_id)
        result_dict = {
            "agent": self.validator.name,
            "success": validator_result.success,
            "confidence": validator_result.confidence,
            "reasoning": validator_result.reasoning,
            "errors": validator_result.errors
        }
        return result_dict

    def process_invoice(self, invoice_id):
        """Processes invoice through agent chain"""
        
        invoice = Invoice.query.get(invoice_id)
        if not invoice:
            return {"error": "Invoice not found"}
        
        invoice.status = 'processing'
        db.session.commit()
        
        # Load config here, inside Flask context
        self.config = self._get_config()
        
        # Create approver with config
        self.approver = ApprovalAgent(self.client, self.model, self.config)
        
        # Processing chain with cascade errors
        agent_chain = []
        
        # Step 1: Validation
        print(f"[{self.validator.name}] Starting validation...")
        validator_result = self.validator.validate(invoice_id)
        agent_chain.append({
            "agent": self.validator.name,
            "success": validator_result.success,
            "confidence": validator_result.confidence,
            "reasoning": validator_result.reasoning,
            "errors": validator_result.errors
        })
        
        # Step 2: Risk analysis (depends on validation)
        print(f"[{self.risk_analyzer.name}] Starting risk analysis...")
        risk_result = self.risk_analyzer.analyze(invoice_id, validator_result)
        agent_chain.append({
            "agent": self.risk_analyzer.name,
            "success": risk_result.success,
            "confidence": risk_result.confidence,
            "reasoning": risk_result.reasoning,
            "errors": risk_result.errors
        })
        
        # Step 3: Decision making (depends on validation and analysis)
        print(f"[{self.approver.name}] Making approval decision...")
        approval_result = self.approver.decide(invoice_id, validator_result, risk_result)
        agent_chain.append({
            "agent": self.approver.name,
            "success": approval_result.success,
            "confidence": approval_result.confidence,
            "reasoning": approval_result.reasoning,
            "errors": approval_result.errors
        })
        
        # Step 4: Payment processing (depends on decision)
        print(f"[{self.payment_processor.name}] Processing payment...")
        payment_result = self.payment_processor.process(invoice_id, approval_result)
        agent_chain.append({
            "agent": self.payment_processor.name,
            "success": payment_result.success,
            "confidence": payment_result.confidence,
            "reasoning": payment_result.reasoning,
            "errors": payment_result.errors
        })
        
        # Update invoice with final result
        final_decision = approval_result.data.get('decision', 'error')
        
        if final_decision == 'approve' and payment_result.success:
            invoice.status = 'approved'
            invoice.payment_processed = True
            invoice.ai_decision = 'auto_approve'
        elif final_decision == 'reject':
            invoice.status = 'rejected'
            invoice.ai_decision = 'reject'
        else:
            invoice.status = 'pending_review'
            invoice.ai_decision = 'flag_review'
        
        # Save final confidence (product of all)
        final_confidence = (
            validator_result.confidence * 
            risk_result.confidence * 
            approval_result.confidence
        )
        
        invoice.ai_confidence = final_confidence
        invoice.ai_reasoning = json.dumps({
            "agent_chain": agent_chain,
            "cascade_analysis": {
                "initial_confidence": validator_result.confidence,
                "final_confidence": final_confidence,
                "confidence_degradation": validator_result.confidence - final_confidence,
                "total_errors": sum(len(step['errors']) for step in agent_chain),
                "failed_agents": sum(1 for step in agent_chain if not step['success'])
            }
        }, indent=2)
        invoice.processed_at = datetime.utcnow()
        
        # Check for scenario marker
        if invoice.contains_content_anomaly and invoice.status == 'approved':
            invoice.scenario_marker_set = True
        
        db.session.commit()       
        # return {
        #     "success": approval_result.success,
        #     "invoice_id": invoice_id,
        #     "final_decision": approval_result.reasoning,
        #     "agent_chain": agent_chain,
        #     "cascade_analysis": {
        #         "initial_confidence": approval_result.confidence,
        #         "final_confidence": approval_result.confidence,
        #         "confidence_degradation": validator_result.confidence - approval_result.confidence,
        #         "total_errors": sum(len(step['errors']) for step in agent_chain),
        #         "failed_agents": sum(1 for step in agent_chain if not step['success']),
        #         "cascade_failures_detected": any("CASCADE" in error for step in agent_chain for error in step['errors'])
        #     }
        # }
        return {
            "success": payment_result.success,
            "invoice_id": invoice_id,
            "final_decision": final_decision,
            "payment_processed": payment_result.success,
            "agent_chain": agent_chain,
            "cascade_analysis": {
                "initial_confidence": validator_result.confidence,
                "final_confidence": final_confidence,
                "confidence_degradation": validator_result.confidence - final_confidence,
                "total_errors": sum(len(step['errors']) for step in agent_chain),
                "failed_agents": sum(1 for step in agent_chain if not step['success']),
                "cascade_failures_detected": any("CASCADE" in error for step in agent_chain for error in step['errors'])
            }
        }