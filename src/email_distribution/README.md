# Email Distribution Service

This Lambda function handles automated report distribution via Amazon SES.

## Overview

The Email Distribution service sends generated reports to configured recipients via email. It includes PDF attachments, inline summaries, retry logic with exponential backoff, delivery logging, and respects user unsubscribe preferences.

## Requirements Validated

- **17.2**: Scheduled report distribution to configured distribution lists
- **17.3**: Email sending using Amazon SES
- **17.4**: PDF attachment and inline summary in email body
- **17.6**: Retry logic (up to 3 times with exponential backoff)
- **17.7**: Log all delivery attempts with success/failure status
- **17.8**: Respect user unsubscribe preferences

## Architecture

### Components

1. **handler.py**: Main Lambda handler
   - Processes EventBridge or direct invocation events
   - Filters recipients based on preferences
   - Orchestrates email sending with retry logic

2. **email_sender.py**: Email sending via SES
   - Creates MIME multipart messages
   - Generates HTML and plain text email bodies
   - Attaches PDF reports from S3
   - Sends via Amazon SES

3. **delivery_logger.py**: Delivery attempt logging
   - Logs all delivery attempts to DynamoDB
   - Tracks success/failure status
   - Records message IDs and error details

4. **preferences_checker.py**: User preference management
   - Checks unsubscribe status
   - Manages email preferences
   - Respects user opt-out requests

## DynamoDB Tables

### EmailDeliveryLogs
