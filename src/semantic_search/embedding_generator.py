"""
Document embedding generation Lambda handler.

Processes document chunks (max 512 tokens per chunk).
Generates embeddings using Bedrock Titan Embeddings.
Stores embeddings in OpenSearch with k-NN index.
Index structure: {tenantId}-documents

Requirements: 13.1
"""

import json
import os
import re
from datetime import datetime
from typing import Any, Dict, List

import boto3
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth
from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.typing import LambdaContext

import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from shared.errors import ProcessingError, AppError
from shared.logger import log_error, log_data_modification

# Environment variables
OPENSEARCH_ENDPOINT = os.environ.get('OPENSEARCH_ENDPOINT')
OPENSEARCH_REGION = os.environ.get('AWS_REGION', 'us-east-1')
DOCUMENTS_TABLE = os.environ.get('DOCUMENTS_TABLE', 'ai-sw-pm-documents')

# Initialize logger
logger = Logger(service="embedding-generator")

# Constants
MAX_TOKENS_PER_CHUNK = 512
EMBEDDING_MODEL_ID = "amazon.titan-embed-text-v1"
EMBEDDING_DIMENSION = 1536

# Lazy initialization of AWS clients
_bedrock_runtime = None
_dynamodb = None


def get_bedrock_client():
    """Get or create Bedrock runtime client."""
    global _bedrock_runtime
    if _bedrock_runtime is None:
        _bedrock_runtime = boto3.client('bedrock-runtime')
    return _bedrock_runtime


def get_dynamodb_resource():
    """Get or create DynamoDB resource."""
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource('dynamodb')
    return _dynamodb


def lambda_handler(event: Dict[str, Any], context: LambdaContext) -> Dict[str, Any]:
    """
    Handle document embedding generation.
    
    Triggered after document text extraction completes.
    
    Args:
        event: Lambda event containing document information
        context: Lambda context
        
    Returns:
        Processing result
    """
    request_id = context.request_id
    
    try:
        # Parse event
        for record in event.get('Records', []):
            # Handle DynamoDB stream event or direct invocation
            if 'dynamodb' in record:
                process_dynamodb_record(record, request_id)
            else:
                # Direct invocation
                tenant_id = record.get('tenantId')
                document_id = record.get('documentId')
                
                if tenant_id and document_id:
                    generate_embeddings(tenant_id, document_id, request_id)
        
        return {
            'statusCode': 200,
            'body': json.dumps({'message': 'Embeddings generated successfully'})
        }
        
    except Exception as e:
        log_error(logger, e, context={'request_id': request_id}, severity='CRITICAL')
        raise


def process_dynamodb_record(record: Dict[str, Any], request_id: str) -> None:
    """
    Process DynamoDB stream record.
    
    Args:
        record: DynamoDB stream record
        request_id: Request ID for logging
    """
    try:
        # Check if this is a document processing completion event
        new_image = record.get('dynamodb', {}).get('NewImage', {})
        
        processing_status = new_image.get('processingStatus', {}).get('S')
        
        if processing_status == 'COMPLETED':
            # Extract tenant ID and document ID
            pk = new_image.get('PK', {}).get('S', '')
            sk = new_image.get('SK', {}).get('S', '')
            
            tenant_id = pk.replace('TENANT#', '')
            document_id = sk.replace('DOCUMENT#', '')
            
            if tenant_id and document_id:
                generate_embeddings(tenant_id, document_id, request_id)
                
    except Exception as e:
        log_error(logger, e, context={'request_id': request_id})
        raise


def generate_embeddings(tenant_id: str, document_id: str, request_id: str) -> None:
    """
    Generate embeddings for a document and store in OpenSearch.
    
    Args:
        tenant_id: Tenant ID
        document_id: Document ID
        request_id: Request ID for logging
    """
    try:
        logger.info(f"Generating embeddings for document: {document_id}")
        
        # Get document metadata and extracted text from DynamoDB
        dynamodb = get_dynamodb_resource()
        table = dynamodb.Table(DOCUMENTS_TABLE)
        response = table.get_item(
            Key={
                'PK': f"TENANT#{tenant_id}",
                'SK': f"DOCUMENT#{document_id}"
            }
        )
        
        if 'Item' not in response:
            logger.warning(f"Document not found: {document_id}")
            return
        
        document = response['Item']
        extracted_text = document.get('extractedText', '')
        
        if not extracted_text:
            logger.warning(f"No extracted text for document: {document_id}")
            return
        
        # Split text into chunks (Requirement 13.1: max 512 tokens per chunk)
        chunks = split_text_into_chunks(extracted_text, MAX_TOKENS_PER_CHUNK)
        
        logger.info(f"Split document into {len(chunks)} chunks")
        
        # Generate embeddings for each chunk
        chunk_embeddings = []
        for i, chunk_text in enumerate(chunks):
            embedding = generate_embedding(chunk_text)
            
            chunk_embeddings.append({
                'chunk_index': i,
                'text': chunk_text,
                'embedding': embedding
            })
        
        # Store embeddings in OpenSearch
        store_embeddings_in_opensearch(
            tenant_id=tenant_id,
            document_id=document_id,
            document_metadata=document,
            chunk_embeddings=chunk_embeddings
        )
        
        # Update document metadata to indicate embeddings are generated
        table.update_item(
            Key={
                'PK': f"TENANT#{tenant_id}",
                'SK': f"DOCUMENT#{document_id}"
            },
            UpdateExpression='SET embeddingsGenerated = :status, embeddingsGeneratedAt = :timestamp, '
                           'chunkCount = :count',
            ExpressionAttributeValues={
                ':status': True,
                ':timestamp': datetime.utcnow().isoformat(),
                ':count': len(chunks)
            }
        )
        
        # Log successful embedding generation
        log_data_modification(
            logger,
            user_id='SYSTEM',
            tenant_id=tenant_id,
            operation_type='UPDATE',
            entity_type='DOCUMENT',
            entity_id=document_id,
            changes={'embeddingsGenerated': True, 'chunkCount': len(chunks)}
        )
        
        logger.info(f"Successfully generated embeddings for document: {document_id}")
        
    except Exception as e:
        log_error(
            logger,
            e,
            context={
                'request_id': request_id,
                'tenant_id': tenant_id,
                'document_id': document_id
            },
            severity='ERROR'
        )
        raise


def split_text_into_chunks(text: str, max_tokens: int) -> List[str]:
    """
    Split text into chunks with maximum token count.
    
    Uses approximate token counting (1 token ≈ 4 characters).
    
    Args:
        text: Text to split
        max_tokens: Maximum tokens per chunk
        
    Returns:
        List of text chunks
    """
    # Approximate: 1 token ≈ 4 characters
    max_chars = max_tokens * 4
    
    # Split by paragraphs first
    paragraphs = text.split('\n\n')
    
    chunks = []
    current_chunk = []
    current_length = 0
    
    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        
        paragraph_length = len(paragraph)
        
        # If single paragraph exceeds max, split by sentences
        if paragraph_length > max_chars:
            sentences = re.split(r'[.!?]+\s+', paragraph)
            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue
                
                sentence_length = len(sentence)
                
                if current_length + sentence_length > max_chars:
                    if current_chunk:
                        chunks.append(' '.join(current_chunk))
                        current_chunk = []
                        current_length = 0
                
                current_chunk.append(sentence)
                current_length += sentence_length
        else:
            # Check if adding this paragraph exceeds max
            if current_length + paragraph_length > max_chars:
                if current_chunk:
                    chunks.append(' '.join(current_chunk))
                    current_chunk = []
                    current_length = 0
            
            current_chunk.append(paragraph)
            current_length += paragraph_length
    
    # Add remaining chunk
    if current_chunk:
        chunks.append(' '.join(current_chunk))
    
    return chunks


def generate_embedding(text: str) -> List[float]:
    """
    Generate embedding for text using Bedrock Titan Embeddings.
    
    Args:
        text: Text to embed
        
    Returns:
        Embedding vector
        
    Raises:
        ProcessingError: If embedding generation fails
    """
    try:
        bedrock_runtime = get_bedrock_client()
        
        # Prepare request body for Titan Embeddings
        request_body = json.dumps({
            'inputText': text
        })
        
        # Invoke Bedrock model
        response = bedrock_runtime.invoke_model(
            modelId=EMBEDDING_MODEL_ID,
            contentType='application/json',
            accept='application/json',
            body=request_body
        )
        
        # Parse response
        response_body = json.loads(response['body'].read())
        embedding = response_body.get('embedding')
        
        if not embedding:
            raise ProcessingError(
                "No embedding returned from Bedrock",
                processing_type='embedding_generation'
            )
        
        return embedding
        
    except Exception as e:
        logger.error(f"Embedding generation failed: {str(e)}")
        raise ProcessingError(
            f"Failed to generate embedding: {str(e)}",
            processing_type='embedding_generation'
        )


def store_embeddings_in_opensearch(
    tenant_id: str,
    document_id: str,
    document_metadata: Dict[str, Any],
    chunk_embeddings: List[Dict[str, Any]]
) -> None:
    """
    Store document embeddings in OpenSearch with k-NN index.
    
    Index structure: {tenantId}-documents (Requirement 13.1)
    
    Args:
        tenant_id: Tenant ID
        document_id: Document ID
        document_metadata: Document metadata
        chunk_embeddings: List of chunk embeddings
    """
    try:
        # Initialize OpenSearch client
        opensearch_client = get_opensearch_client()
        
        # Index name: {tenantId}-documents
        index_name = f"{tenant_id.lower()}-documents"
        
        # Create index if it doesn't exist
        create_index_if_not_exists(opensearch_client, index_name)
        
        # Index each chunk
        for chunk_data in chunk_embeddings:
            doc_id = f"{document_id}_{chunk_data['chunk_index']}"
            
            document_chunk = {
                'document_id': document_id,
                'tenant_id': tenant_id,
                'project_id': document_metadata.get('projectId'),
                'document_type': document_metadata.get('documentType'),
                'file_name': document_metadata.get('fileName'),
                'chunk_index': chunk_data['chunk_index'],
                'text': chunk_data['text'],
                'embedding': chunk_data['embedding'],
                'uploaded_at': document_metadata.get('uploadedAt'),
                'indexed_at': datetime.utcnow().isoformat()
            }
            
            opensearch_client.index(
                index=index_name,
                id=doc_id,
                body=document_chunk
            )
        
        logger.info(f"Stored {len(chunk_embeddings)} chunks in OpenSearch index: {index_name}")
        
    except Exception as e:
        logger.error(f"Failed to store embeddings in OpenSearch: {str(e)}")
        raise ProcessingError(
            f"Failed to store embeddings: {str(e)}",
            processing_type='opensearch_indexing'
        )


def get_opensearch_client() -> OpenSearch:
    """
    Get OpenSearch client with AWS authentication.
    
    Returns:
        OpenSearch client
    """
    # Get AWS credentials for signing requests
    credentials = boto3.Session().get_credentials()
    awsauth = AWS4Auth(
        credentials.access_key,
        credentials.secret_key,
        OPENSEARCH_REGION,
        'es',
        session_token=credentials.token
    )
    
    # Create OpenSearch client
    client = OpenSearch(
        hosts=[{'host': OPENSEARCH_ENDPOINT, 'port': 443}],
        http_auth=awsauth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection
    )
    
    return client


def create_index_if_not_exists(client: OpenSearch, index_name: str) -> None:
    """
    Create OpenSearch index with k-NN configuration if it doesn't exist.
    
    Args:
        client: OpenSearch client
        index_name: Index name
    """
    try:
        if not client.indices.exists(index=index_name):
            # Create index with k-NN settings
            index_body = {
                'settings': {
                    'index': {
                        'knn': True,
                        'knn.algo_param.ef_search': 512
                    }
                },
                'mappings': {
                    'properties': {
                        'document_id': {'type': 'keyword'},
                        'tenant_id': {'type': 'keyword'},
                        'project_id': {'type': 'keyword'},
                        'document_type': {'type': 'keyword'},
                        'file_name': {'type': 'text'},
                        'chunk_index': {'type': 'integer'},
                        'text': {
                            'type': 'text',
                            'analyzer': 'standard'
                        },
                        'embedding': {
                            'type': 'knn_vector',
                            'dimension': EMBEDDING_DIMENSION,
                            'method': {
                                'name': 'hnsw',
                                'space_type': 'cosinesimil',
                                'engine': 'nmslib',
                                'parameters': {
                                    'ef_construction': 512,
                                    'm': 16
                                }
                            }
                        },
                        'uploaded_at': {'type': 'date'},
                        'indexed_at': {'type': 'date'}
                    }
                }
            }
            
            client.indices.create(index=index_name, body=index_body)
            logger.info(f"Created OpenSearch index: {index_name}")
            
    except Exception as e:
        logger.error(f"Failed to create index: {str(e)}")
        raise
