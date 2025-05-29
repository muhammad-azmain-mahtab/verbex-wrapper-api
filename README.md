# Verbex Wrapper API

This repository provides an API wrapper to handle tool calls for the [Verbex AI Voice Agent](https://verbex.ai/). It acts as a middleware to facilitate communication between the Verbex agent and third-party APIs such as Magento and Salesforce.

## Purpose

The main purpose of this API is to:
- Receive tool call requests from the Verbex AI voice agent.
- Interact with external APIs (Magento, Salesforce) as required by the agent.
- Process and return the responses to the Verbex agent.

## Features

- Handles authentication and session management for Magento and Salesforce.
- Designed for easy integration with Verbex AI agent workflows.
- Configurable via environment variables.
- Includes scheduled and manual data sync for analytical dashboards.

## Prerequisites

- Docker and Docker Compose installed on your system.
- Access credentials for Magento and Salesforce services.
- Python 3.8+ (if running outside Docker).

## Setup & Installation

### 1. Clone the Repository

```bash
git clone https://github.com/muhammad-azmain-mahtab/verbex-wrapper-api.git
cd verbex-wrapper-api
```

### 2. Prepare Environment Variables

Create a `.env` file in the root directory with the following content:

```env
# Magento Configuration
MAGENTO_BASE_URL=""
MAGENTO_USERNAME=""
MAGENTO_PASSWORD=""

# Verbex AI Agent Configuration
AI_AGENT_ID=""
AUTH_TOKEN=""

# Database Configuration
# Example: "postgresql+psycopg2://verbex:verbex@192.168.12.163:5432/verbex_db"
DB_URI=""

# Salesforce Configuration
SALESFORCE_CLIENT_ID=""
SALESFORCE_CLIENT_SECRET=""
SALESFORCE_USERNAME=""
SALESFORCE_PASSWORD=""
SALESFORCE_INSTANCE_URL=""
SALESFORCE_TOKEN_URL=""

# APScheduler
SYNC_INTERVAL_MINUTES=1440
```

Fill in the values as appropriate for your environment.  
For `DB_URI`, the generic format is:
```
postgresql+psycopg2://<username>:<password>@<host>:<port>/<database>
```
Example:
```
postgresql+psycopg2://verbex:verbex@192.168.12.163:5432/verbex_db
```

### 3. Build and Run with Docker Compose

```bash
docker compose up -d
```

This command will build (if necessary) and start the API service in detached mode.

## API Endpoints

### 1. Health Check

**Endpoint:** `/`  
**Method:** `GET`  
**Response Example:**
```json
{
  "status": "API is running"
}
```

---

### 2. Get Products from Magento

**Endpoint:** `/products`  
**Method:** `POST`  
**Request Body:**
```json
{
  "keyword": "search_term"
}
```
**Response Example:**
```json
{
  "products": [
    {
      "name": "Product Name",
      "price": 99.99,
      "sku": "SKU123",
      "stock_qty": 10
    }
  ]
}
```

---

### 3. Get Salesforce Account by Phone

**Endpoint:** `/salesforce-account`  
**Method:** `POST`  
**Request Body:**
```json
{
  "phone": "1234567890"
}
```
**Response Example:**

```json
{
    "Customer Name": "Customer",
    "Customer Phone": "1234567890",
    "Past Purchase": "Fridge",
    "Purchase ID": "84ajflaw23",
    "Purchased on": "2025-08-02"
}
```

---

### 4. Create Salesforce Ticket

**Endpoint:** `/create-salesforce-ticket`  
**Method:** `POST`  
**Request Body:**
```json
{
  "phone": "1234567890",
  "subject": "Subject here",
  "description": "Ticket description",
  "type": "Type of case",
  "reason": "Reason for case"
}
```
**Response Example:**
```json
{
  "message": "Case created successfully",
  "case_id": "daw223da",
  "case_number": "00001001"
}
```

---

### 5. Get Salesforce Case Info

**Endpoint:** `/get-case-info`  
**Method:** `POST`  
**Request Body:**
```json
{
  "case_number": "00001001"
}
```
**Response Example:**

```json
{
    "AccountId": "hafl23j11",
    "CaseNumber": "00001050",
    "ClosedDate": "2025-05-24T07:40:46.000+0000",
    "CreatedDate": "2025-05-24T07:39:37.000+0000",
    "Description": "TV display broken.",
    "Id": "daw223da",
    "Priority": "Medium",
    "Reason": "Pending",
    "Status": "Closed",
    "Subject": "TV Issue",
    "Type": "Service",
    "attributes": {
        "type": "Case",
        "url": "/services/data/v59.0/sobjects/Case/daw223da"
    }
}
```

---

### 6. Fetch Verbex Call Logs (Scheduled & Manual)

**Purpose:**  
Fetches all call logs and related info from the Verbex internal API, used for visualization in PowerBI or similar tools.

- **Scheduled Fetch:**  
  - Runs automatically every `SYNC_INTERVAL_MINUTES` (as set in `.env`).
  - No user action required.

- **Manual Fetch Endpoint:**  
  - **Endpoint:** `/fetch-call-logs`
  - **Method:** `POST`
  - **Description:** Triggers immediate fetching of call logs from Verbex internal API.
  - **Request Body:** (empty)
  - **Response Example:**
    
    ```json
    {
        "calls_processed": 55,
        "messages_saved": 679,
        "analyses_saved": 3,
        "status": "success"
    }
    ```

---

## Usage

 - Once running, the API will listen for requests from the Verbex AI agent and proxy them to the configured third-party APIs (Magento/Salesforce).  
 - The scheduled sync task will automatically fetch call logs for analytics at the defined interval.  
 - You can also trigger call log synchronization manually via the `/fetch-call-logs` endpoint.

## Configuration

All runtime configuration is handled via the `.env` file. Make sure all required fields are populated before starting the container.

## Contributing

Pull requests are welcome! For major changes, please open an issue first to discuss what you would like to change.

## License

[MIT](LICENSE)
