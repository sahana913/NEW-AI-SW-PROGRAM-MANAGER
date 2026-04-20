"""
Document search Lambda handler.

Implements search_documents endpoint.
Converts search query to embeddings.
Performs k-NN search in OpenSearch.
Ranks results by relevance score.
Highlights relevant text passages.
Filters results by tenant ID, document type, date range.

Requirements: 13.2, 13.3, 13.5, 13.7
"""

from shared.validators import validate_required_fields, validate_tenant_id
from shared.logger import log_api_request, log_error
from shared.errors import AppError, ValidationError
import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

import boto3
from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.typing import LambdaContext
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))


# Environment variables
OPENSEARCH_ENDPOINT = os.environ.get("OPENSEARCH_ENDPOINT")
OPENSEARCH_REGION = os.environ.get("AWS_REGION", "us-east-1")

# Initialize logger
logger = Logger(service="document-search")

# Constants
EMBEDDING_MODEL_ID = "amazon.titan-embed-text-v1"
DEFAULT_SEARCH_LIMIT = 10
MAX_SEARCH_LIMIT = 100
SEARCH_TIMEOUT_SECONDS = 2

# Lazy initialization of AWS clients
_bedrock_runtime = None


def get_bedrock_client():
    """Get or create Bedrock runtime client."""
    global _bedrock_runtime
    if _bedrock_runtime is None:
        _bedrock_runtime = boto3.client("bedrock-runtime")
    return _bedrock_runtime


def lambda_handler(event: Dict[str, Any], context: LambdaContext) -> Dict[str, Any]:
    """
    Handle document search request.

    Performs semantic search across documents using natural language queries.

    Args:
        event: Lambda event containing request data
        context: Lambda context

    Returns:
        API Gateway response with search results
    """
    request_id = context.request_id
    start_time = datetime.utcnow()

    try:
        # Parse request body
        body = json.loads(event.get("body", "{}"))

        # Extract authorization context
        authorizer_context = event.get("requestContext", {}).get("authorizer", {})
        user_id = authorizer_context.get("userId")
        tenant_id = authorizer_context.get("tenantId")

        if not user_id or not tenant_id:
            raise ValidationError("Missing authorization context")

        # Validate tenant ID
        tenant_id = validate_tenant_id(tenant_id)

        # Validate required fields
        validate_required_fields(body, ["query"])

        # Extract search parameters
        query = body["query"]
        document_types = body.get("documentTypes", [])
        project_ids = body.get("projectIds", [])
        date_range = body.get("dateRange")
        limit = min(int(body.get("limit", DEFAULT_SEARCH_LIMIT)), MAX_SEARCH_LIMIT)

        # Validate query
        if not query or len(query.strip()) == 0:
            raise ValidationError("Query cannot be empty", field="query")

        # Perform search
        search_results = search_documents(
            tenant_id=tenant_id,
            query=query,
            document_types=document_types,
            project_ids=project_ids,
            date_range=date_range,
            limit=limit,
        )

        # Calculate response time
        response_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

        # Log API request (Requirement 13.7: search results within 2 seconds)
        log_api_request(
            logger,
            request_id=request_id,
            user_id=user_id,
            tenant_id=tenant_id,
            endpoint="/documents/search",
            method="POST",
            response_time_ms=response_time_ms,
            status_code=200,
        )

        # Return response
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps(
                {
                    "results": search_results["results"],
                    "totalResults": search_results["total"],
                    "responseTimeMs": response_time_ms,
                }
            ),
        }

    except ValidationError as e:
        response_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        log_error(logger, e, context={"request_id": request_id})

        if "user_id" in locals() and "tenant_id" in locals():
            log_api_request(
                logger,
                request_id=request_id,
                user_id=user_id,
                tenant_id=tenant_id,
                endpoint="/documents/search",
                method="POST",
                response_time_ms=response_time_ms,
                status_code=e.status_code,
                error=e.message,
            )

        return {
            "statusCode": e.status_code,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps(e.to_dict()),
        }

    except Exception as e:
        response_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        log_error(logger, e, context={"request_id": request_id}, severity="CRITICAL")

        if "user_id" in locals() and "tenant_id" in locals():
            log_api_request(
                logger,
                request_id=request_id,
                user_id=user_id,
                tenant_id=tenant_id,
                endpoint="/documents/search",
                method="POST",
                response_time_ms=response_time_ms,
                status_code=500,
                error=str(e),
            )

        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps(
                {
                    "error": {
                        "code": "INTERNAL_ERROR",
                        "message": "An internal error occurred",
                    }
                }
            ),
        }


def search_documents(
    tenant_id: str,
    query: str,
    document_types: Optional[List[str]] = None,
    project_ids: Optional[List[str]] = None,
    date_range: Optional[Dict[str, str]] = None,
    limit: int = DEFAULT_SEARCH_LIMIT,
) -> Dict[str, Any]:
    """
    Search documents using semantic search.

    Args:
        tenant_id: Tenant ID for filtering (Requirement 13.7)
        query: Natural language search query
        document_types: Optional document type filters
        project_ids: Optional project ID filters
        date_range: Optional date range filter
        limit: Maximum number of results

    Returns:
        Search results with highlights
    """
    try:
        logger.info(f"Searching documents for tenant: {tenant_id}, query: {query}")

        # Convert query to embedding (Requirement 13.2)
        query_embedding = generate_query_embedding(query)

        # Initialize OpenSearch client
        opensearch_client = get_opensearch_client()

        # Index name: {tenantId}-documents
        index_name = f"{tenant_id.lower()}-documents"

        # Check if index exists
        if not opensearch_client.indices.exists(index=index_name):
            logger.info(f"Index does not exist: {index_name}")
            return {"results": [], "total": 0}

        # Build search query
        search_body = build_search_query(
            query_embedding=query_embedding,
            tenant_id=tenant_id,
            document_types=document_types,
            project_ids=project_ids,
            date_range=date_range,
            limit=limit,
        )

        # Perform k-NN search (Requirement 13.3)
        response = opensearch_client.search(
            index=index_name, body=search_body, request_timeout=SEARCH_TIMEOUT_SECONDS
        )

        # Process and rank results (Requirement 13.3)
        search_results = process_search_results(response, query)

        logger.info(f"Found {len(search_results)} results")

        return {"results": search_results, "total": response["hits"]["total"]["value"]}

    except Exception as e:
        logger.error(f"Search failed: {str(e)}")
        raise


def generate_query_embedding(query: str) -> List[float]:
    """
    Convert search query to embedding vector.

    Args:
        query: Search query text

    Returns:
        Query embedding vector
    """
    try:
        bedrock_runtime = get_bedrock_client()

        # Prepare request body for Titan Embeddings
        request_body = json.dumps({"inputText": query})

        # Invoke Bedrock model
        response = bedrock_runtime.invoke_model(
            modelId=EMBEDDING_MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=request_body,
        )

        # Parse response
        response_body = json.loads(response["body"].read())
        embedding = response_body.get("embedding")

        if not embedding:
            raise AppError("No embedding returned from Bedrock")

        return embedding

    except Exception as e:
        logger.error(f"Query embedding generation failed: {str(e)}")
        raise


def build_search_query(
    query_embedding: List[float],
    tenant_id: str,
    document_types: Optional[List[str]] = None,
    project_ids: Optional[List[str]] = None,
    date_range: Optional[Dict[str, str]] = None,
    limit: int = DEFAULT_SEARCH_LIMIT,
) -> Dict[str, Any]:
    """
    Build OpenSearch query with k-NN and filters.

    Args:
        query_embedding: Query embedding vector
        tenant_id: Tenant ID for filtering
        document_types: Optional document type filters
        project_ids: Optional project ID filters
        date_range: Optional date range filter
        limit: Maximum number of results

    Returns:
        OpenSearch query body
    """
    # Build filter conditions
    filter_conditions = [
        {"term": {"tenant_id": tenant_id}}  # Tenant isolation (Requirement 13.7)
    ]

    # Add document type filter if provided
    if document_types:
        filter_conditions.append({"terms": {"document_type": document_types}})

    # Add project ID filter if provided
    if project_ids:
        filter_conditions.append({"terms": {"project_id": project_ids}})

    # Add date range filter if provided
    if date_range:
        date_filter = {"range": {"uploaded_at": {}}}
        if "start" in date_range:
            date_filter["range"]["uploaded_at"]["gte"] = date_range["start"]
        if "end" in date_range:
            date_filter["range"]["uploaded_at"]["lte"] = date_range["end"]
        filter_conditions.append(date_filter)

    # Build k-NN query
    search_body = {
        "size": limit,
        "query": {
            "bool": {
                "must": [
                    {"knn": {"embedding": {"vector": query_embedding, "k": limit}}}
                ],
                "filter": filter_conditions,
            }
        },
        "highlight": {
            "fields": {
                "text": {
                    "fragment_size": 150,
                    "number_of_fragments": 3,
                    "pre_tags": ["<mark>"],
                    "post_tags": ["</mark>"],
                }
            }
        },
        "_source": [
            "document_id",
            "file_name",
            "document_type",
            "project_id",
            "chunk_index",
            "text",
            "uploaded_at",
        ],
    }

    return search_body


def process_search_results(
    response: Dict[str, Any], query: str
) -> List[Dict[str, Any]]:
    """
    Process and format search results.

    Groups chunks by document and highlights relevant passages (Requirement 13.5).

    Args:
        response: OpenSearch response
        query: Original search query

    Returns:
        Formatted search results
    """
    hits = response.get("hits", {}).get("hits", [])

    # Group results by document
    documents = {}

    for hit in hits:
        source = hit["_source"]
        document_id = source["document_id"]
        relevance_score = hit["_score"]

        # Get highlighted text (Requirement 13.5)
        highlights = hit.get("highlight", {}).get("text", [])

        if document_id not in documents:
            documents[document_id] = {
                "documentId": document_id,
                "documentName": source["file_name"],
                "documentType": source["document_type"],
                "projectId": source.get("project_id"),
                "relevanceScore": relevance_score,
                "highlights": [],
                "uploadedAt": source["uploaded_at"],
            }

        # Add highlights from this chunk
        if highlights:
            documents[document_id]["highlights"].extend(highlights)
        else:
            # If no highlights, use text snippet
            text = source.get("text", "")
            snippet = text[:150] + "..." if len(text) > 150 else text
            documents[document_id]["highlights"].append(snippet)

        # Keep the highest relevance score for the document
        if relevance_score > documents[document_id]["relevanceScore"]:
            documents[document_id]["relevanceScore"] = relevance_score

    # Convert to list and sort by relevance score (Requirement 13.3)
    results = list(documents.values())
    results.sort(key=lambda x: x["relevanceScore"], reverse=True)

    # Limit highlights per document to top 3
    for result in results:
        result["highlights"] = result["highlights"][:3]

    return results


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
        "es",
        session_token=credentials.token,
    )

    # Create OpenSearch client
    client = OpenSearch(
        hosts=[{"host": OPENSEARCH_ENDPOINT, "port": 443}],
        http_auth=awsauth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
    )

    return client
