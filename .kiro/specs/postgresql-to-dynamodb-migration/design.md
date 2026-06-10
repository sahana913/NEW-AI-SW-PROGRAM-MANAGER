# PostgreSQL to DynamoDB Migration Bugfix Design

## Overview

This design document outlines the complete migration from PostgreSQL to DynamoDB to resolve critical data persistence failures in the AI SW Program Manager serverless architecture. The current hybrid database approach causes Lambda functions to fail when connecting to RDS PostgreSQL, resulting in the system falling back to demo data instead of persisting real user uploads and project information. The migration will establish a fully serverless architecture using only DynamoDB for data persistence, ensuring reliable data storage and retrieval across all Lambda functions.

## Glossary

- **Bug_Condition (C)**: The condition that triggers data persistence failures - when Lambda functions attempt to connect to RDS PostgreSQL in serverless deployment
- **Property (P)**: The desired behavior when data operations are performed - successful persistence and retrieval using DynamoDB without connection failures
- **Preservation**: Existing API response formats, data structures, and business logic that must remain unchanged after migration
- **Single Table Design**: DynamoDB pattern using one table with composite keys to store multiple entity types
- **GSI (Global Secondary Index)**: DynamoDB secondary indexes enabling efficient query patterns beyond the primary key
- **Tenant Isolation**: Data separation mechanism ensuring multi-tenant security using partition key prefixes
- **Connection Pool**: PostgreSQL connection management that will be eliminated in favor of DynamoDB SDK calls

## Bug Details

### Bug Condition

The bug manifests when Lambda functions attempt to connect to RDS PostgreSQL in the serverless deployment environment. The `psycopg2` library and connection pooling mechanisms fail due to VPC networking issues, cold start timeouts, and incompatible serverless architecture patterns.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type DatabaseOperation
  OUTPUT: boolean
  
  RETURN input.database_type == 'POSTGRESQL'
         AND input.deployment_environment == 'SERVERLESS'
         AND (input.operation IN ['INSERT', 'UPDATE', 'SELECT', 'DELETE'])
         AND connection_requires_vpc_networking(input.connection)
END FUNCTION
```

### Examples

- **Project Data Storage**: When users upload project documents, `store_jira_project_data()` fails to connect to PostgreSQL and the system returns demo project data instead of storing actual uploads
- **Health Score Calculation**: When `insert_health_scores()` attempts to persist calculated metrics, PostgreSQL connection failures cause the system to display cached sample health scores
- **Sprint Data Ingestion**: When Jira integration fetches sprint data, `insert_sprints()` fails to store the data in PostgreSQL, causing dashboard to show static demo sprint information
- **Dashboard Queries**: When `get_dashboard_overview()` queries project metrics, PostgreSQL connection timeouts force the system to return hardcoded sample data instead of real project analytics

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- API Gateway endpoints must continue to return the same JSON response structures for dashboard, projects, risks, predictions, reports, and documents
- Frontend components must continue to receive data in the same format without requiring changes to React components
- Authentication and authorization flows must remain unchanged using Cognito User Pool
- Multi-tenant data isolation must continue to work with the same security boundaries
- Caching mechanisms must continue to provide performance optimization without affecting data consistency
- Integration with external systems (Jira, Azure DevOps) must continue to fetch and process data with the same validation rules
- Report generation must continue to produce downloadable reports with the same content format and structure

**Scope:**
All operations that do NOT involve database persistence should be completely unaffected by this migration. This includes:
- API Gateway request routing and response formatting
- Lambda function business logic and data processing
- S3 document storage and retrieval operations
- CloudWatch logging and monitoring
- Cognito authentication flows

## Hypothesized Root Cause

Based on the bug analysis and codebase examination, the root causes are:

1. **VPC Networking Complexity**: RDS PostgreSQL requires VPC configuration with private subnets, security groups, and NAT gateways, creating networking complexity that conflicts with serverless Lambda deployment patterns

2. **Connection Pool Management**: The `psycopg2` connection pooling in `shared/database.py` is designed for long-running applications, not serverless functions that start and stop frequently, leading to connection exhaustion and timeout errors

3. **Cold Start Performance**: PostgreSQL connections have significant overhead during Lambda cold starts, causing timeout failures when functions attempt to establish database connections within the execution time limit

4. **Dependency Management**: The `psycopg2-binary` dependency adds significant deployment package size and requires native libraries that may not be compatible with Lambda runtime environments

5. **Architecture Mismatch**: PostgreSQL is designed for persistent connections and ACID transactions, while the serverless use case requires fast, stateless operations that align better with DynamoDB's design patterns

## Correctness Properties

Property 1: Bug Condition - Serverless Data Persistence

_For any_ database operation where the bug condition holds (PostgreSQL connection in serverless environment), the migrated system SHALL successfully persist and retrieve data using DynamoDB without connection failures, VPC networking issues, or timeout errors.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7**

Property 2: Preservation - API Response Compatibility

_For any_ API request that does NOT involve the underlying database technology (authentication, response formatting, business logic), the migrated system SHALL produce exactly the same response structure and behavior as the original PostgreSQL-based system, preserving all existing frontend compatibility.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7**

## Fix Implementation

### Changes Required

**Phase 1: DynamoDB Table Schema Design**

**File**: `infrastructure/stacks/dynamodb_stack.py`

**Specific Changes**:
1. **Expand Table Schema**: Replace simple single-entity tables with comprehensive multi-entity tables supporting all PostgreSQL entities
   - Add `ProjectsTable` with GSIs for tenant and source queries
   - Add `SprintsTable` with GSIs for project and date range queries  
   - Add `BacklogItemsTable` with GSIs for project and status queries
   - Add `MilestonesTable` with GSIs for project and due date queries
   - Add `ResourcesTable` with GSIs for project and week queries
   - Add `DependenciesTable` with GSIs for project and task queries
   - Add `HealthScoresTable` with GSIs for project and calculation time queries

2. **Implement Single Table Design Pattern**: Create unified table structure with composite keys
   - Primary Key: `PK = TENANT#{tenantId}`, `SK = ENTITY#{entityType}#{entityId}`
   - GSI1: `GSI1PK = PROJECT#{projectId}`, `GSI1SK = ENTITY#{entityType}#{timestamp}`
   - GSI2: `GSI2PK = TENANT#{tenantId}#TYPE#{entityType}`, `GSI2SK = TIMESTAMP#{timestamp}`

3. **Configure Optimized Indexes**: Add GSIs for all query patterns identified in PostgreSQL schema
   - Project-based queries (all entities for a project)
   - Time-based queries (entities within date ranges)
   - Status-based queries (entities by status/priority)
   - Tenant isolation queries (all entities for a tenant)

**Phase 2: Data Access Layer Migration**

**File**: `src/shared/database.py`

**Specific Changes**:
1. **Remove PostgreSQL Dependencies**: Eliminate all `psycopg2` imports and connection pool logic
   - Remove `get_connection_pool()`, `get_db_connection()`, `get_db_credentials()`
   - Remove `execute_query()`, `execute_batch()` functions
   - Remove Secrets Manager integration for database credentials

2. **Implement DynamoDB Operations**: Replace PostgreSQL operations with DynamoDB SDK calls
   - Add `get_dynamodb_client()` function using boto3
   - Add `put_item()`, `get_item()`, `query()`, `batch_write_item()` wrappers
   - Add `query_by_project()`, `query_by_tenant()`, `query_by_date_range()` functions

3. **Maintain Function Signatures**: Keep existing function names and parameters for compatibility
   - `insert_project()` → DynamoDB PutItem operation
   - `insert_sprints()` → DynamoDB BatchWriteItem operation
   - `insert_backlog_items()` → DynamoDB BatchWriteItem operation
   - `insert_milestones()` → DynamoDB BatchWriteItem operation
   - `insert_resources()` → DynamoDB BatchWriteItem operation
   - `insert_dependencies()` → DynamoDB BatchWriteItem operation

**Phase 3: Lambda Function Updates**

**Files**: All Lambda handlers in `src/*/handler.py`

**Specific Changes**:
1. **Remove PostgreSQL Imports**: Update all Lambda functions to remove `psycopg2` dependencies
   - Update `src/dashboard/handler.py` to use DynamoDB queries
   - Update `src/data_storage/handler.py` to use DynamoDB operations
   - Update `src/jira_integration/data_storage.py` to use DynamoDB operations
   - Update `src/database_maintenance/handler.py` to use DynamoDB operations

2. **Update Query Logic**: Replace SQL queries with DynamoDB query patterns
   - Dashboard overview queries → DynamoDB Query with GSI
   - Project-specific queries → DynamoDB Query with project partition key
   - Time-range queries → DynamoDB Query with sort key conditions
   - Aggregation queries → Lambda-side aggregation of DynamoDB results

3. **Maintain Response Formats**: Ensure all Lambda functions return the same JSON structures
   - Transform DynamoDB items to match PostgreSQL result format
   - Preserve field names, data types, and nested structures
   - Maintain pagination and sorting behavior

**Phase 4: Infrastructure Updates**

**File**: `infrastructure/app.py`

**Specific Changes**:
1. **Remove RDS Components**: Eliminate all PostgreSQL infrastructure
   - Remove RDS instance definitions
   - Remove VPC, subnets, and security groups for database
   - Remove database credentials in Secrets Manager
   - Remove database maintenance Lambda functions

2. **Update Environment Variables**: Replace PostgreSQL connection variables with DynamoDB table names
   - Remove `DB_SECRET_NAME`, `DB_HOST`, `DB_PORT`, `DB_NAME`
   - Add `PROJECTS_TABLE_NAME`, `SPRINTS_TABLE_NAME`, etc.
   - Update all Lambda function environment variable configurations

3. **Update IAM Permissions**: Replace RDS permissions with DynamoDB permissions
   - Remove VPC and RDS access permissions
   - Add DynamoDB read/write permissions for all tables
   - Add DynamoDB index query permissions

**Phase 5: Data Migration Strategy**

**File**: `migration/postgresql_to_dynamodb.py` (new)

**Specific Changes**:
1. **Create Migration Script**: Build one-time data migration utility
   - Extract all data from PostgreSQL using existing connection logic
   - Transform relational data to DynamoDB item format
   - Batch write data to DynamoDB tables with proper error handling
   - Validate data integrity after migration

2. **Implement Rollback Capability**: Create rollback mechanism for migration safety
   - Export PostgreSQL data to S3 before migration
   - Create DynamoDB table snapshots after migration
   - Provide rollback script to restore PostgreSQL if needed

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the PostgreSQL connection bug BEFORE implementing the DynamoDB migration. Confirm or refute the root cause analysis.

**Test Plan**: Deploy Lambda functions with PostgreSQL dependencies to serverless environment and simulate database operations. Run these tests on the UNFIXED code to observe connection failures and understand the root cause.

**Test Cases**:
1. **Cold Start Connection Test**: Deploy fresh Lambda and attempt PostgreSQL connection (will fail on unfixed code)
2. **VPC Networking Test**: Test PostgreSQL connection from Lambda in VPC configuration (will fail on unfixed code)  
3. **Connection Pool Test**: Test connection pool behavior under concurrent Lambda executions (will fail on unfixed code)
4. **Timeout Test**: Test PostgreSQL operations under Lambda timeout constraints (will fail on unfixed code)

**Expected Counterexamples**:
- Connection timeout errors during Lambda cold starts
- VPC networking failures preventing database access
- Connection pool exhaustion under concurrent executions
- Possible causes: VPC misconfiguration, connection pool limits, cold start overhead, dependency conflicts

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the migrated system produces the expected behavior using DynamoDB.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := dynamodb_operation(input)
  ASSERT successful_persistence_and_retrieval(result)
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the migrated system produces the same result as the original system.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT postgresql_system_response(input) = dynamodb_system_response(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the API input domain
- It catches edge cases that manual unit tests might miss  
- It provides strong guarantees that API behavior is unchanged for all non-database operations

**Test Plan**: Capture API responses from PostgreSQL system first, then write property-based tests to verify DynamoDB system produces identical responses.

**Test Cases**:
1. **API Response Preservation**: Verify all API endpoints return identical JSON structures after migration
2. **Authentication Preservation**: Verify Cognito authentication continues to work identically
3. **Business Logic Preservation**: Verify data processing and validation logic continues to work
4. **Integration Preservation**: Verify external system integrations continue to work

### Unit Tests

- Test DynamoDB operations for each entity type (projects, sprints, backlog items, milestones, resources, dependencies)
- Test GSI query patterns for all access patterns identified in PostgreSQL schema
- Test data transformation between PostgreSQL and DynamoDB formats
- Test error handling for DynamoDB throttling and capacity limits

### Property-Based Tests

- Generate random project data and verify DynamoDB storage and retrieval works correctly
- Generate random API requests and verify response format preservation across migration
- Test that all non-database operations continue to work across many scenarios
- Generate random tenant configurations and verify data isolation is preserved

### Integration Tests

- Test full project lifecycle with DynamoDB (create, update, query, delete)
- Test dashboard data aggregation with DynamoDB queries
- Test external system integration (Jira, Azure DevOps) with DynamoDB storage
- Test concurrent Lambda executions with DynamoDB operations
- Test data migration script with sample PostgreSQL data