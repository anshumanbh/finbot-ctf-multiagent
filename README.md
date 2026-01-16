# Multi-Agent FinBot: Workflow Propagation Extension

## Overview

This project extends a single-agent invoice processor into a multi-agent pipeline to observe how decisions, confidence, and status updates propagate across agents.

## Multi-Agent Pipeline

- **ValidatorAgent** – validates invoice data structure and completeness
- **RiskAnalyzerAgent** – reviews financial indicators and consistency signals
- **ApprovalAgent** – decides approve/reject/review
- **PaymentProcessorAgent** – executes or blocks payment

The agents run in a linear chain: `Validator → Risk Analyzer → Approval → Payment Processor`.

Each agent:
- Uses a specialized prompt
- Returns structured JSON
- Passes results downstream

## Cascade Behavior

The system records agent outputs and produces a cascade analysis (confidence aggregation, accumulated signals, and agent outcomes). This helps review how upstream decisions influence downstream outcomes.

### Scenario Types

1. **Data Quality Interruption** – invalid or incomplete data triggers early review
2. **Early Agent Divergence** – early-stage decision results in a partial chain
3. **Midchain Divergence** – mid-stage decision changes the final outcome
4. **Full Propagation** – an early classification flows through the full chain

## Implementation Details

Core logic lives in `src/services/multi_agent_finbot.py`:

- `AgentResult` structure for success, confidence, reasoning, and errors
- Agent classes for validation, analysis, approval, and payment processing
- Orchestration and cascade analysis summary

## Demonstration Script

Run `python cascade_failure_demo.py` to submit sample invoices covering:

- Clean invoice processing
- Invalid data scenarios
- Priority escalation cases
- Confidence degradation cases
- Full propagation cases
- Midchain break cases

## Usage

1. Start the Flask app:
   ```bash
   python app.py
   ```
2. Submit invoices via:
   ```bash
   POST /api/vendors/{vendor_id}/invoices
   ```
3. Review results in the Vendor Portal and Admin Dashboard.

## Notes

The single-agent `FinBotAgent` remains available in `src/services/finbot_agent.py` for comparison.

## License

Apache License, Version 2.0. See `LICENSE`.
