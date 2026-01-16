# FinBot Demo Guide

## Purpose

This guide describes how to explore the FinBot multi-agent invoice workflow and review the resulting analysis.

## Getting Started

1. Start the app:
   ```bash
   python app.py
   ```
2. Register a vendor in the Vendor Portal.
3. Submit an invoice and review the status updates.

## Vendor Portal

- Submit invoices and track status changes.
- Review invoice history entries with confidence and reasoning summaries.
- Content anomaly notes and scenario markers appear when applicable.

## Admin Dashboard

- Configure thresholds, speed priority, and integrity checks.
- Review pending invoices.
- Browse scenario markers and cascade analysis summaries.

## Suggested Scenarios

- Clean invoice with complete documentation
- Incomplete data to trigger early review
- Priority/urgency-heavy description to observe handling
- Medium amount with low trust vendor
- Large amount with full documentation

## Observability

- Agent chain output is stored in `ai_reasoning` as JSON
- Cascade analysis summarizes confidence aggregation and outcomes
- Scenario markers indicate selected processing paths

## Operating Guidelines

- Use the demo within its intended scope.
- Avoid placing sensitive data in invoice descriptions.
