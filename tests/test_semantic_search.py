"""
Unit tests for semantic search functionality.

Tests embedding generation and document search.
"""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from semantic_search.embedding_generator import (
    split_text_into_chunks,
    generate_embeddings,
    lambda_handler as embedding_handler
)
from semantic_search.search_handler import (
    build_search_query,
    process_search_results,
    lambda_handler as search_handler
)


class TestEmbeddingGenerator:
    """Test embedding generation functionality."""
    
    def test_split_text_into_chunks_simple(self):
        """Test splitting text into chunks."""
        text = "This is a test. " * 100  # Create long text
        chunks = split_text_into_chunks(text, max_tokens=50)
        
        assert len(chunks) > 0
        for chunk in chunks:
            # Each chunk should be roughly within token limit
            # 1 token ≈ 4 characters, so 50 tokens ≈ 200 chars
            assert len(chunk) <= 250  # Allow some buffer
    
    def test_split_text_into_chunks_paragraphs(self):
        """Test splitting text respects paragraph boundaries."""
        text = "Paragraph 1.\n\nParagraph 2.\n\nParagraph 3."
        chunks = split_text_into_chunks(text, max_tokens=10)
        
        assert len(chunks) > 0
        # Each chunk should contain complete sentences
        for chunk in chunks:
            assert chunk.strip() != ""
    
    def test_split_text_empty(self):
        """Test splitting empty text."""
        chunks = split_text_into_chunks("", max_tokens=512)
        assert chunks == []
    
    @patch('semantic_search.embedding_generator.get_dynamodb_resource')
    @patch('semantic_search.embedding_generator.get_bedrock_client')
    @patch('semantic_search.embedding_generator.get_opensearch_client')
    def test_generate_embeddings_success(self, mock_opensearch, mock_bedrock, mock_dynamodb):
        """Test successful embedding generation."""
        # Mock DynamoDB response
        mock_table = Mock()
        mock_table.get_item.return_value = {
            'Item': {
                'documentId': 'doc-123',
                'tenantId': 'tenant-1',
                'projectId': 'proj-1',
                'documentType': 'SOW',
                'fileName': 'test.pdf',
                'extractedText': 'This is test content for embedding generation.',
                'uploadedAt': '2024-01-01T00:00:00Z'
            }
        }
        mock_table.update_item.return_value = {}
        mock_dynamodb_resource = Mock()
        mock_dynamodb_resource.Table.return_value = mock_table
        mock_dynamodb.return_value = mock_dynamodb_resource
        
        # Mock Bedrock response
        mock_bedrock_client = Mock()
        mock_bedrock_client.invoke_model.return_value = {
            'body': Mock(read=lambda: json.dumps({
                'embedding': [0.1] * 1536
            }).encode())
        }
        mock_bedrock.return_value = mock_bedrock_client
        
        # Mock OpenSearch client
        mock_os_client = Mock()
        mock_os_client.indices.exists.return_value = True
        mock_os_client.index.return_value = {'result': 'created'}
        mock_opensearch.return_value = mock_os_client
        
        # Call function
        generate_embeddings('tenant-1', 'doc-123', 'req-123')
        
        # Verify DynamoDB was called
        assert mock_table.get_item.called
        assert mock_table.update_item.called
        
        # Verify Bedrock was called
        assert mock_bedrock_client.invoke_model.called
        
        # Verify OpenSearch was called
        assert mock_os_client.index.called


class TestSearchHandler:
    """Test document search functionality."""
    
    def test_build_search_query_basic(self):
        """Test building basic search query."""
        query_embedding = [0.1] * 1536
        tenant_id = 'tenant-1'
        
        query = build_search_query(
            query_embedding=query_embedding,
            tenant_id=tenant_id,
            limit=10
        )
        
        assert 'query' in query
        assert 'bool' in query['query']
        assert 'must' in query['query']['bool']
        assert 'filter' in query['query']['bool']
        
        # Check tenant filter is present
        filters = query['query']['bool']['filter']
        assert any(f.get('term', {}).get('tenant_id') == tenant_id for f in filters)
    
    def test_build_search_query_with_filters(self):
        """Test building search query with filters."""
        query_embedding = [0.1] * 1536
        tenant_id = 'tenant-1'
        document_types = ['SOW', 'BRD']
        project_ids = ['proj-1', 'proj-2']
        date_range = {'start': '2024-01-01', 'end': '2024-12-31'}
        
        query = build_search_query(
            query_embedding=query_embedding,
            tenant_id=tenant_id,
            document_types=document_types,
            project_ids=project_ids,
            date_range=date_range,
            limit=20
        )
        
        filters = query['query']['bool']['filter']
        
        # Check document type filter
        assert any('terms' in f and 'document_type' in f['terms'] for f in filters)
        
        # Check project ID filter
        assert any('terms' in f and 'project_id' in f['terms'] for f in filters)
        
        # Check date range filter
        assert any('range' in f and 'uploaded_at' in f['range'] for f in filters)
    
    def test_process_search_results_empty(self):
        """Test processing empty search results."""
        response = {
            'hits': {
                'total': {'value': 0},
                'hits': []
            }
        }
        
        results = process_search_results(response, 'test query')
        assert results == []
    
    def test_process_search_results_with_highlights(self):
        """Test processing search results with highlights."""
        response = {
            'hits': {
                'total': {'value': 2},
                'hits': [
                    {
                        '_score': 0.95,
                        '_source': {
                            'document_id': 'doc-1',
                            'file_name': 'test1.pdf',
                            'document_type': 'SOW',
                            'project_id': 'proj-1',
                            'chunk_index': 0,
                            'text': 'This is the first document content.',
                            'uploaded_at': '2024-01-01T00:00:00Z'
                        },
                        'highlight': {
                            'text': ['This is the <mark>first</mark> document']
                        }
                    },
                    {
                        '_score': 0.85,
                        '_source': {
                            'document_id': 'doc-2',
                            'file_name': 'test2.pdf',
                            'document_type': 'BRD',
                            'project_id': 'proj-1',
                            'chunk_index': 0,
                            'text': 'This is the second document content.',
                            'uploaded_at': '2024-01-02T00:00:00Z'
                        },
                        'highlight': {
                            'text': ['This is the <mark>second</mark> document']
                        }
                    }
                ]
            }
        }
        
        results = process_search_results(response, 'test query')
        
        assert len(results) == 2
        assert results[0]['documentId'] == 'doc-1'  # Higher score first
        assert results[0]['relevanceScore'] == 0.95
        assert len(results[0]['highlights']) > 0
        assert '<mark>' in results[0]['highlights'][0]
    
    def test_process_search_results_groups_chunks(self):
        """Test that results from same document are grouped."""
        response = {
            'hits': {
                'total': {'value': 2},
                'hits': [
                    {
                        '_score': 0.95,
                        '_source': {
                            'document_id': 'doc-1',
                            'file_name': 'test1.pdf',
                            'document_type': 'SOW',
                            'project_id': 'proj-1',
                            'chunk_index': 0,
                            'text': 'Chunk 1 content.',
                            'uploaded_at': '2024-01-01T00:00:00Z'
                        },
                        'highlight': {
                            'text': ['Chunk 1 <mark>content</mark>']
                        }
                    },
                    {
                        '_score': 0.90,
                        '_source': {
                            'document_id': 'doc-1',
                            'file_name': 'test1.pdf',
                            'document_type': 'SOW',
                            'project_id': 'proj-1',
                            'chunk_index': 1,
                            'text': 'Chunk 2 content.',
                            'uploaded_at': '2024-01-01T00:00:00Z'
                        },
                        'highlight': {
                            'text': ['Chunk 2 <mark>content</mark>']
                        }
                    }
                ]
            }
        }
        
        results = process_search_results(response, 'test query')
        
        # Should be grouped into single document
        assert len(results) == 1
        assert results[0]['documentId'] == 'doc-1'
        assert len(results[0]['highlights']) == 2
        assert results[0]['relevanceScore'] == 0.95  # Highest score
    
    @patch('semantic_search.search_handler.get_bedrock_client')
    @patch('semantic_search.search_handler.get_opensearch_client')
    def test_search_handler_success(self, mock_opensearch, mock_bedrock):
        """Test successful search request."""
        # Mock Bedrock response
        mock_bedrock_client = Mock()
        mock_bedrock_client.invoke_model.return_value = {
            'body': Mock(read=lambda: json.dumps({
                'embedding': [0.1] * 1536
            }).encode())
        }
        mock_bedrock.return_value = mock_bedrock_client
        
        # Mock OpenSearch response
        mock_os_client = Mock()
        mock_os_client.indices.exists.return_value = True
        mock_os_client.search.return_value = {
            'hits': {
                'total': {'value': 1},
                'hits': [
                    {
                        '_score': 0.95,
                        '_source': {
                            'document_id': 'doc-1',
                            'file_name': 'test.pdf',
                            'document_type': 'SOW',
                            'project_id': 'proj-1',
                            'chunk_index': 0,
                            'text': 'Test content',
                            'uploaded_at': '2024-01-01T00:00:00Z'
                        },
                        'highlight': {
                            'text': ['<mark>Test</mark> content']
                        }
                    }
                ]
            }
        }
        mock_opensearch.return_value = mock_os_client
        
        # Create event with valid UUID tenant ID
        event = {
            'body': json.dumps({
                'query': 'test query',
                'limit': 10
            }),
            'requestContext': {
                'authorizer': {
                    'userId': '550e8400-e29b-41d4-a716-446655440000',
                    'tenantId': '550e8400-e29b-41d4-a716-446655440001'
                }
            }
        }
        
        context = Mock()
        context.request_id = 'req-123'
        
        # Call handler
        response = search_handler(event, context)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert 'results' in body
        assert len(body['results']) == 1
        assert body['results'][0]['documentId'] == 'doc-1'
    
    @patch('semantic_search.search_handler.get_bedrock_client')
    @patch('semantic_search.search_handler.get_opensearch_client')
    def test_search_handler_missing_query(self, mock_opensearch, mock_bedrock):
        """Test search request with missing query."""
        event = {
            'body': json.dumps({}),
            'requestContext': {
                'authorizer': {
                    'userId': '550e8400-e29b-41d4-a716-446655440000',
                    'tenantId': '550e8400-e29b-41d4-a716-446655440001'
                }
            }
        }
        
        context = Mock()
        context.request_id = 'req-123'
        
        response = search_handler(event, context)
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'error' in body


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
