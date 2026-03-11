# Semantic Document Search

This module implements semantic document search functionality using Amazon Bedrock Titan Embeddings and Amazon OpenSearch.

## Components

### 1. Embedding Generator (`embedding_generator.py`)

Processes documents and generates embeddings for semantic search.

**Features:**
- Splits documents into chunks (max 512 tokens per chunk)
- Generates embeddings using Bedrock Titan Embeddings
- Stores embeddings in OpenSearch with k-NN index
- Index structure: `{tenantId}-documents`

**Trigger:**
- DynamoDB stream event when document processing completes
- Direct invocation with tenant ID and document ID

**Environment Variables:**
- `OPENSEARCH_ENDPOINT`: OpenSearch domain endpoint
- `AWS_REGION`: AWS region (default: us-east-1)
- `DOCUMENTS_TABLE`: DynamoDB table name for documents

### 2. Search Handler (`search_handler.py`)

Implements the document search API endpoint.

**Features:**
- Converts natural language queries to embeddings
- Performs k-NN search in OpenSearch
- Ranks results by relevance score
- Highlights relevant text passages
- Filters by tenant ID, document type, project ID, date range

**API Endpoint:** `POST /documents/search`

**Request Body:**
```json
{
  "query": "milestone deliverables",
  "documentTypes": ["SOW", "BRD"],
  "projectIds": ["proj-1", "proj-2"],
  "dateRange": {
    "start": "2024-01-01",
    "end": "2024-12-31"
  },
  "limit": 10
}
```

**Response:**
```json
{
  "results": [
    {
      "documentId": "doc-123",
      "documentName": "project-sow.pdf",
      "documentType": "SOW",
      "projectId": "proj-1",
      "relevanceScore": 0.95,
      "highlights": [
        "Milestone 1: <mark>deliverables</mark> include...",
        "The project <mark>milestone</mark> schedule..."
      ],
      "uploadedAt": "2024-01-15T10:00:00Z"
    }
  ],
  "totalResults": 1,
  "responseTimeMs": 245
}
```

**Environment Variables:**
- `OPENSEARCH_ENDPOINT`: OpenSearch domain endpoint
- `AWS_REGION`: AWS region (default: us-east-1)

## OpenSearch Index Configuration

### Index Name
`{tenantId}-documents` (e.g., `550e8400-e29b-41d4-a716-446655440001-documents`)

### Index Settings
```json
{
  "settings": {
    "index": {
      "knn": true,
      "knn.algo_param.ef_search": 512
    }
  }
}
```

### Index Mappings
```json
{
  "mappings": {
    "properties": {
      "document_id": {"type": "keyword"},
      "tenant_id": {"type": "keyword"},
      "project_id": {"type": "keyword"},
      "document_type": {"type": "keyword"},
      "file_name": {"type": "text"},
      "chunk_index": {"type": "integer"},
      "text": {
        "type": "text",
        "analyzer": "standard"
      },
      "embedding": {
        "type": "knn_vector",
        "dimension": 1536,
        "method": {
          "name": "hnsw",
          "space_type": "cosinesimil",
          "engine": "nmslib",
          "parameters": {
            "ef_construction": 512,
            "m": 16
          }
        }
      },
      "uploaded_at": {"type": "date"},
      "indexed_at": {"type": "date"}
    }
  }
}
```

## Workflow

1. **Document Upload**
   - User uploads document via `/documents/upload` endpoint
   - Document stored in S3 with tenant-specific prefix

2. **Text Extraction**
   - Document processing Lambda extracts text using AWS Textract
   - Extracted text stored in DynamoDB

3. **Embedding Generation**
   - Embedding generator triggered by DynamoDB stream
   - Text split into chunks (max 512 tokens)
   - Each chunk embedded using Bedrock Titan Embeddings
   - Embeddings stored in OpenSearch with k-NN index

4. **Search**
   - User submits natural language query
   - Query converted to embedding
   - k-NN search performed in OpenSearch
   - Results ranked by relevance score
   - Highlights extracted from matching chunks
   - Results grouped by document

## Performance

- **Search Response Time:** < 2 seconds for queries across 10,000 documents
- **Embedding Dimension:** 1536 (Titan Embeddings v1)
- **k-NN Algorithm:** HNSW (Hierarchical Navigable Small World)
- **Similarity Metric:** Cosine similarity

## Security

- **Tenant Isolation:** All queries filtered by tenant ID
- **Authentication:** JWT token validation via Lambda Authorizer
- **Authorization:** User must belong to tenant to search documents
- **Data Encryption:** 
  - At rest: OpenSearch encryption enabled
  - In transit: TLS 1.2+ for all API calls

## Requirements Mapping

- **Requirement 13.1:** Generate embeddings for document chunks
- **Requirement 13.2:** Convert search query to embeddings
- **Requirement 13.3:** Perform k-NN search and rank results
- **Requirement 13.5:** Highlight relevant text passages
- **Requirement 13.7:** Filter results by tenant boundaries

## Testing

Run unit tests:
```bash
pytest tests/test_semantic_search.py -v
```

## Dependencies

- `boto3`: AWS SDK for Python
- `opensearch-py`: OpenSearch Python client
- `requests-aws4auth`: AWS authentication for OpenSearch
- `aws-lambda-powertools`: Lambda utilities and logging
