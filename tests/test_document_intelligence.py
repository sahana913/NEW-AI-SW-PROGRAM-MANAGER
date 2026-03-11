"""
Tests for document intelligence service.

Tests SOW milestone extraction, SLA clause extraction, and confirmation workflow.
"""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from document_intelligence.sow_extraction import (
    extract_milestones_from_sow,
    _construct_sow_extraction_prompt,
    _parse_milestone_extraction_response,
    _store_milestone_extractions
)
from document_intelligence.sla_extraction import (
    extract_sla_clauses_from_contract,
    _construct_sla_extraction_prompt,
    _parse_sla_extraction_response,
    _store_sla_extractions
)
from document_intelligence.extraction_confirmation import (
    confirm_extraction,
    get_extractions_for_document
)
from document_intelligence.handler import lambda_handler


class TestSOWExtraction:
    """Test SOW milestone extraction."""
    
    def test_construct_sow_extraction_prompt(self):
        """Test SOW extraction prompt construction."""
        extracted_text = "Project milestone 1 due on 2024-12-31"
        
        prompt = _construct_sow_extraction_prompt(extracted_text)
        
        assert "Extract all milestones" in prompt
        assert "milestone name" in prompt.lower()
        assert "due date" in prompt.lower()
        assert "deliverables" in prompt.lower()
        assert extracted_text in prompt
        assert "JSON array" in prompt
    
    def test_parse_milestone_extraction_response_valid(self):
        """Test parsing valid milestone extraction response."""
        response_text = json.dumps([
            {
                "milestoneName": "Phase 1 Completion",
                "dueDate": "2024-12-31",
                "deliverables": ["Design docs", "Prototype"],
                "successCriteria": "All features implemented",
                "dependencies": None,
                "confidence": 0.95
            }
        ])
        
        milestones = _parse_milestone_extraction_response(response_text)
        
        assert len(milestones) == 1
        assert milestones[0]['milestoneName'] == "Phase 1 Completion"
        assert milestones[0]['dueDate'] == "2024-12-31"
        assert len(milestones[0]['deliverables']) == 2
        assert milestones[0]['confidence'] == 0.95
    
    def test_parse_milestone_extraction_response_with_explanation(self):
        """Test parsing response with additional explanation text."""
        response_text = """Here are the extracted milestones:
        [
            {
                "milestoneName": "Milestone 1",
                "dueDate": "2024-12-31",
                "deliverables": ["Item 1"],
                "successCriteria": null,
                "dependencies": null,
                "confidence": 0.8
            }
        ]
        These milestones were extracted from the SOW."""
        
        milestones = _parse_milestone_extraction_response(response_text)
        
        assert len(milestones) == 1
        assert milestones[0]['milestoneName'] == "Milestone 1"
    
    def test_parse_milestone_extraction_response_empty(self):
        """Test parsing empty response."""
        response_text = "[]"
        
        milestones = _parse_milestone_extraction_response(response_text)
        
        assert len(milestones) == 0
    
    def test_parse_milestone_extraction_response_missing_required_fields(self):
        """Test parsing response with missing required fields."""
        response_text = json.dumps([
            {
                "milestoneName": "Milestone 1",
                # Missing dueDate
                "deliverables": [],
                "confidence": 0.8
            },
            {
                "milestoneName": "Milestone 2",
                "dueDate": "2024-12-31",
                "deliverables": [],
                "confidence": 0.9
            }
        ])
        
        milestones = _parse_milestone_extraction_response(response_text)
        
        # Only the second milestone should be included
        assert len(milestones) == 1
        assert milestones[0]['milestoneName'] == "Milestone 2"
    
    @patch('document_intelligence.sow_extraction.dynamodb')
    def test_store_milestone_extractions(self, mock_dynamodb):
        """Test storing milestone extractions."""
        mock_table = Mock()
        mock_dynamodb.Table.return_value = mock_table
        
        milestones = [
            {
                'milestoneName': 'Milestone 1',
                'dueDate': '2024-12-31',
                'deliverables': ['Item 1'],
                'successCriteria': 'Complete',
                'dependencies': None,
                'confidence': 0.9
            },
            {
                'milestoneName': 'Milestone 2',
                'dueDate': '2025-01-31',
                'deliverables': ['Item 2'],
                'successCriteria': None,
                'dependencies': None,
                'confidence': 0.6  # Low confidence
            }
        ]
        
        extraction_ids = _store_milestone_extractions(
            document_id='doc-123',
            tenant_id='tenant-123',
            milestones=milestones
        )
        
        assert len(extraction_ids) == 2
        assert mock_table.put_item.call_count == 2
        
        # Check first extraction (high confidence)
        first_call = mock_table.put_item.call_args_list[0]
        first_item = first_call[1]['Item']
        assert first_item['type'] == 'MILESTONE'
        assert first_item['confidence'] == 0.9
        assert first_item['requiresReview'] is False
        assert first_item['status'] == 'PENDING_REVIEW'
        
        # Check second extraction (low confidence)
        second_call = mock_table.put_item.call_args_list[1]
        second_item = second_call[1]['Item']
        assert second_item['confidence'] == 0.6
        assert second_item['requiresReview'] is True
    
    @patch('document_intelligence.sow_extraction._call_bedrock_claude')
    @patch('document_intelligence.sow_extraction._store_milestone_extractions')
    def test_extract_milestones_from_sow_success(self, mock_store, mock_bedrock):
        """Test successful milestone extraction from SOW."""
        mock_bedrock.return_value = json.dumps([
            {
                "milestoneName": "Phase 1",
                "dueDate": "2024-12-31",
                "deliverables": ["Design"],
                "successCriteria": "Complete",
                "dependencies": None,
                "confidence": 0.95
            }
        ])
        mock_store.return_value = ['extraction-1']
        
        milestones = extract_milestones_from_sow(
            document_id='doc-123',
            tenant_id='tenant-123',
            extracted_text='SOW text with milestone information'
        )
        
        assert len(milestones) == 1
        assert milestones[0]['milestoneName'] == "Phase 1"
        mock_bedrock.assert_called_once()
        mock_store.assert_called_once()


class TestSLAExtraction:
    """Test SLA clause extraction."""
    
    def test_construct_sla_extraction_prompt(self):
        """Test SLA extraction prompt construction."""
        extracted_text = "System uptime must be 99.9% monthly"
        
        prompt = _construct_sla_extraction_prompt(extracted_text)
        
        assert "Extract all SLA" in prompt
        assert "metric name" in prompt.lower()
        assert "threshold" in prompt.lower()
        assert "measurement period" in prompt.lower()
        assert "penalty" in prompt.lower()
        assert extracted_text in prompt
        assert "JSON array" in prompt
    
    def test_parse_sla_extraction_response_valid(self):
        """Test parsing valid SLA extraction response."""
        response_text = json.dumps([
            {
                "slaMetricName": "System Uptime",
                "targetThreshold": "99.9%",
                "measurementPeriod": "monthly",
                "penaltyClause": "$1000 per hour of downtime",
                "reportingRequirements": "Monthly report",
                "confidence": 0.92
            }
        ])
        
        sla_clauses = _parse_sla_extraction_response(response_text)
        
        assert len(sla_clauses) == 1
        assert sla_clauses[0]['slaMetricName'] == "System Uptime"
        assert sla_clauses[0]['targetThreshold'] == "99.9%"
        assert sla_clauses[0]['measurementPeriod'] == "monthly"
        assert sla_clauses[0]['confidence'] == 0.92
    
    def test_parse_sla_extraction_response_missing_required_fields(self):
        """Test parsing response with missing required fields."""
        response_text = json.dumps([
            {
                "slaMetricName": "Uptime",
                # Missing targetThreshold and measurementPeriod
                "confidence": 0.8
            },
            {
                "slaMetricName": "Response Time",
                "targetThreshold": "< 2 seconds",
                "measurementPeriod": "per request",
                "confidence": 0.9
            }
        ])
        
        sla_clauses = _parse_sla_extraction_response(response_text)
        
        # Only the second SLA should be included
        assert len(sla_clauses) == 1
        assert sla_clauses[0]['slaMetricName'] == "Response Time"
    
    @patch('document_intelligence.sla_extraction.dynamodb')
    def test_store_sla_extractions(self, mock_dynamodb):
        """Test storing SLA extractions."""
        mock_table = Mock()
        mock_dynamodb.Table.return_value = mock_table
        
        sla_clauses = [
            {
                'slaMetricName': 'Uptime',
                'targetThreshold': '99.9%',
                'measurementPeriod': 'monthly',
                'penaltyClause': '$1000/hour',
                'reportingRequirements': 'Monthly',
                'confidence': 0.85
            }
        ]
        
        extraction_ids = _store_sla_extractions(
            document_id='doc-123',
            tenant_id='tenant-123',
            sla_clauses=sla_clauses
        )
        
        assert len(extraction_ids) == 1
        assert mock_table.put_item.call_count == 1
        
        call_args = mock_table.put_item.call_args
        item = call_args[1]['Item']
        assert item['type'] == 'SLA'
        assert item['confidence'] == 0.85
        assert item['status'] == 'PENDING_REVIEW'


class TestExtractionConfirmation:
    """Test extraction confirmation workflow."""
    
    @patch('document_intelligence.extraction_confirmation.dynamodb')
    @patch('document_intelligence.extraction_confirmation._create_milestone_record')
    def test_confirm_extraction_milestone_confirmed(self, mock_create_milestone, mock_dynamodb):
        """Test confirming a milestone extraction."""
        # Mock DynamoDB table
        mock_table = Mock()
        mock_dynamodb.Table.return_value = mock_table
        mock_dynamodb.resource.return_value = mock_dynamodb
        
        # Mock get_item to return extraction
        extraction_data = {
            'extractionId': 'ext-123',
            'documentId': 'doc-123',
            'tenantId': 'tenant-123',
            'type': 'MILESTONE',
            'content': json.dumps({
                'milestoneName': 'Phase 1',
                'dueDate': '2024-12-31',
                'deliverables': ['Design']
            }),
            'confidence': 0.9,
            'status': 'PENDING_REVIEW'
        }
        mock_table.get_item.return_value = {'Item': extraction_data}
        
        # Confirm extraction
        result = confirm_extraction(
            extraction_id='ext-123',
            document_id='doc-123',
            tenant_id='tenant-123',
            user_id='user-123',
            confirmed=True
        )
        
        # Verify update was called
        assert mock_table.update_item.called
        update_call = mock_table.update_item.call_args
        assert ':status' in update_call[1]['ExpressionAttributeValues']
        assert update_call[1]['ExpressionAttributeValues'][':status'] == 'CONFIRMED'
        
        # Verify milestone creation was called
        mock_create_milestone.assert_called_once()
    
    @patch('document_intelligence.extraction_confirmation.dynamodb')
    def test_confirm_extraction_rejected(self, mock_dynamodb):
        """Test rejecting an extraction."""
        mock_table = Mock()
        mock_dynamodb.Table.return_value = mock_table
        
        extraction_data = {
            'extractionId': 'ext-123',
            'documentId': 'doc-123',
            'tenantId': 'tenant-123',
            'type': 'MILESTONE',
            'content': '{}',
            'confidence': 0.5,
            'status': 'PENDING_REVIEW'
        }
        mock_table.get_item.return_value = {'Item': extraction_data}
        
        result = confirm_extraction(
            extraction_id='ext-123',
            document_id='doc-123',
            tenant_id='tenant-123',
            user_id='user-123',
            confirmed=False
        )
        
        # Verify status updated to REJECTED
        update_call = mock_table.update_item.call_args
        assert update_call[1]['ExpressionAttributeValues'][':status'] == 'REJECTED'
    
    @patch('document_intelligence.extraction_confirmation.dynamodb')
    def test_get_extractions_for_document(self, mock_dynamodb):
        """Test getting extractions for a document."""
        mock_table = Mock()
        mock_dynamodb.Table.return_value = mock_table
        
        # Mock query response
        mock_table.query.return_value = {
            'Items': [
                {
                    'extractionId': 'ext-1',
                    'tenantId': 'tenant-123',
                    'confidence': 0.9,
                    'requiresReview': False,
                    'status': 'PENDING_REVIEW'
                },
                {
                    'extractionId': 'ext-2',
                    'tenantId': 'tenant-123',
                    'confidence': 0.6,
                    'requiresReview': True,
                    'status': 'PENDING_REVIEW'
                }
            ]
        }
        
        extractions = get_extractions_for_document(
            document_id='doc-123',
            tenant_id='tenant-123'
        )
        
        assert len(extractions) == 2
        # Should be sorted with requiresReview=True first, then by confidence
        # ext-2 has requiresReview=True, so it should be first
        assert extractions[0]['extractionId'] == 'ext-2'
        assert extractions[0]['confidence'] == 0.6
        assert extractions[0]['requiresReview'] is True
        # ext-1 has requiresReview=False, so it should be second
        assert extractions[1]['extractionId'] == 'ext-1'
        assert extractions[1]['confidence'] == 0.9
        assert extractions[1]['requiresReview'] is False


class TestDocumentIntelligenceHandler:
    """Test document intelligence Lambda handler."""
    
    @patch('document_intelligence.handler.extract_milestones_from_sow')
    @patch('document_intelligence.handler.dynamodb')
    def test_handle_extract_request_sow(self, mock_dynamodb, mock_extract):
        """Test handling SOW extraction request."""
        mock_table = Mock()
        mock_dynamodb.Table.return_value = mock_table
        
        # Mock document lookup
        mock_table.scan.return_value = {
            'Items': [{
                'documentId': 'doc-123',
                'tenantId': 'tenant-123',
                'documentType': 'SOW',
                'processingStatus': 'COMPLETED',
                'extractedText': 'SOW text with milestones'
            }]
        }
        
        # Mock extraction
        mock_extract.return_value = [
            {'milestoneName': 'Phase 1', 'dueDate': '2024-12-31'}
        ]
        
        event = {
            'httpMethod': 'POST',
            'path': '/documents/doc-123/extract',
            'pathParameters': {'documentId': 'doc-123'},
            'requestContext': {
                'authorizer': {
                    'userId': 'user-123',
                    'tenantId': 'tenant-123'
                }
            }
        }
        
        context = Mock()
        context.request_id = 'req-123'
        
        response = lambda_handler(event, context)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['extractionType'] == 'MILESTONE'
        assert body['extractionCount'] == 1
        mock_extract.assert_called_once()
    
    @patch('document_intelligence.handler.get_extractions_for_document')
    def test_handle_get_extractions_request(self, mock_get_extractions):
        """Test handling get extractions request."""
        mock_get_extractions.return_value = [
            {
                'extractionId': 'ext-1',
                'type': 'MILESTONE',
                'content': json.dumps({'milestoneName': 'Phase 1'}),
                'confidence': 0.9,
                'requiresReview': False,
                'status': 'PENDING_REVIEW',
                'createdAt': '2024-01-01T00:00:00Z'
            }
        ]
        
        event = {
            'httpMethod': 'GET',
            'path': '/documents/doc-123/extractions',
            'pathParameters': {'documentId': 'doc-123'},
            'queryStringParameters': None,
            'requestContext': {
                'authorizer': {
                    'userId': 'user-123',
                    'tenantId': 'tenant-123'
                }
            }
        }
        
        context = Mock()
        context.request_id = 'req-123'
        
        response = lambda_handler(event, context)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['totalCount'] == 1
        assert len(body['extractions']) == 1
        assert body['extractions'][0]['type'] == 'MILESTONE'
    
    @patch('document_intelligence.handler.confirm_extraction')
    def test_handle_confirm_extraction_request(self, mock_confirm):
        """Test handling extraction confirmation request."""
        mock_confirm.return_value = {
            'extractionId': 'ext-123',
            'status': 'CONFIRMED'
        }
        
        event = {
            'httpMethod': 'PUT',
            'path': '/documents/doc-123/extractions/ext-123/confirm',
            'pathParameters': {
                'documentId': 'doc-123',
                'extractionId': 'ext-123'
            },
            'body': json.dumps({
                'confirmed': True
            }),
            'requestContext': {
                'authorizer': {
                    'userId': 'user-123',
                    'tenantId': 'tenant-123'
                }
            }
        }
        
        context = Mock()
        context.request_id = 'req-123'
        
        response = lambda_handler(event, context)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['status'] == 'CONFIRMED'
        mock_confirm.assert_called_once()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
