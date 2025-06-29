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
- Setup Magento and Salesforce (see instructions below).
- Access credentials for Magento and Salesforce services.
- Python 3.8+ (if running outside Docker).

### <img src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/magento/magento-original.svg" alt="Magento" width="24" height="24" style="vertical-align:middle;margin-right:4px;"> Magento Setup

1. **Create Magento Directory**
    ```bash
    mkdir -p ~/Sites/magento
    cd ~/Sites/magento
    ```

2. **Initialize Project with Docker Magento Template**
    ```bash
    curl -s https://raw.githubusercontent.com/markshust/docker-magento/master/lib/template | bash
    ```

3. **Overwrite Compose File**
    - Overwrite the content of `compose.dev-linux.yaml` to `compose.dev.yaml`.

4. **Modify Healthcheck for OpenSearch**
    - In `compose.healthcheck.yaml`, replace the `opensearch` section with:
      
      ```yaml
      opensearch:
        healthcheck:
          test: "curl --fail opensearch:9200/_cat/health >/dev/null || exit 1"
          interval: 5s
          timeout: 5s
          retries: 30
      #      <<: *healthcheck-slow-start
      ```

6. **Download Magento Community Edition 2.4.8**
    ```bash
    bin/download community 2.4.8
    ```

7. **Run Magento Setup**
    ```bash
    bin/setup magento.test
    ```

8. **Deploy Sample Data**
    ```bash
    bin/magento sampledata:deploy
    ```

9. **Upgrade Magento Setup**
    ```bash
    bin/magento setup:upgrade
    ```

10. **Disable Two-Factor Authentication Modules**
    ```bash
    bin/magento module:disable Magento_TwoFactorAuth Magento_AdminAdobeImsTwoFactorAuth
    ```

11. **Upgrade Magento Setup Again**
    ```bash
    bin/magento setup:upgrade
    ```

### <img src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/salesforce/salesforce-original.svg" alt="Salesforce" width="24" height="24" style="vertical-align:middle;margin-right:4px;"> Salesforce Setup

1. Enable Connected App Creation
    - Go to **Setup** in Salesforce.
    - Search for **External Client Apps** in the Quick Find box.
    - Click on **External Client App Settings**.
    - ✅ Turn on **Allow creation of connected apps**.
    - Click on **New Connected App**.

2. For Salesforce setup, please complete **steps 2 and 3** at the following link:  
[https://docs.verbex.ai/tools/custom-tools-salesforce](https://docs.verbex.ai/tools/custom-tools-salesforce)

3. Generate Access Token:  
   In Setup, go to **Identity → OAuth and OpenID Connect Settings**.  
    - ✅ Turn on **Allow OAuth Username-Password Flows**

4. Use the following curl command template to get your access token:
    ```bash
    curl -X POST "https://login.salesforce.com/services/oauth2/token" \
    -d "grant_type=password" \
    -d "client_id=CONSUMER_KEY" \
    -d "client_secret=CONSUMER_SECRET" \
    -d "username=YOUR_SALESFORCE_USER_NAME" \
    -d "password=YOUR_SALESFORCE_PASSWORD"
    ```

   The response will include:
    ```json
    {
      "access_token": "YOUR_ACCESS_TOKEN",
      "instance_url": "https://your-instance.salesforce.com",
      "id": "...",
      "token_type": "Bearer",
      "issued_at": "...",
      "signature": "..."
    }
    ```

5. Test your access token and data sending with CURL or Postman:
    ```bash
    curl -X POST "<instance_url>/services/data/v59.0/sobjects/Lead/" \
         -H 'Authorization: Bearer <access_token>' \
         -H "Content-Type: application/json" \
         -d '{
             "LastName": "abc",
             "Company": "xyz",
             "Email": "abc.xyz@example.com"
         }'
    ```

    The response will look like:
    ```json
    {"id":"...","success":true,"errors":[]}%  
    ```

6. Setup the Cases Object in Salesforce (for Tickets)
    - Go to **Sales Console** in Salesforce.
    - Click on the downward arrow on the right of **Home** tab.
    - Click on **Edit** and add **Cases** object. 
    - Go to **Setup** in from the top right corner.
    - Search for **Support Settings** in the Quick Find box.
    - Click on **Support Settings**.
    - ✅ Turn on **Show Closed Statuses in Case Status Field**.

### 📘 Salesforce Case Trigger Integration with Verbex Wrapper API

  This guide helps you set up a Salesforce **Apex Trigger** that sends Case data to an external API (`{VERBEX_WRAPPER_API_URL}/trigger-obd-closed-case`) when a Case is **closed**.

  ---

  #### ✅ Features

  - Detects when a Case status changes to `"Closed"`
  - Sends JSON data via HTTP POST to your API
  - Includes important Case and Account fields

  ---

  #### 📦 JSON Fields Sent to API

  | Field          | Description                       |
  |----------------|-----------------------------------|
  | `id`           | Salesforce Case ID                |
  | `caseNumber`   | Case Number (e.g., "00012345")    |
  | `subject`      | Case Subject                      |
  | `description`  | Case Description                  |
  | `status`       | Will always be `"Closed"`         |
  | `priority`     | Priority level                    |
  | `createdDate`  | Case creation time                |
  | `closedDate`   | Case closure time                 |
  | `type`         | Case type                         |
  | `reason`       | Reason for case                   |
  | `accountName`  | Name of related Account           |
  | `accountPhone` | Phone number of the Account       |

  ---

#### 🔧 Setup Instructions

##### 1. 🔐 Add Remote Site Setting

1. In Salesforce, go to **Setup → Remote Site Settings**
2. Click **New Remote Site**
   - **Remote Site Name:** `VerbexAPI`
   - **Remote Site URL:** `{VERBEX_WRAPPER_API_URL}`
   - Click **Save**

---

##### 2. 🧠 Create Apex Class: `CaseAPIHandler`

In Developer Console:

1. Go to `File → New → Apex Class`
2. Name it `CaseAPIHandler`
3. Paste:

    ```apex
    public class CaseAPIHandler {

        @future(callout=true)
        public static void sendCaseData(Id caseId) {
            try {
                Case c = [
                    SELECT 
                        Id, CaseNumber, Subject, Description, Status, Priority,
                        CreatedDate, ClosedDate, Type, Reason,
                        Account.Name, Account.Phone
                    FROM Case 
                    WHERE Id = :caseId
                    LIMIT 1
                ];

                Map<String, Object> data = new Map<String, Object>{
                    'id' => c.Id,
                    'caseNumber' => c.CaseNumber,
                    'subject' => c.Subject,
                    'description' => c.Description,
                    'status' => c.Status,
                    'priority' => c.Priority,
                    'createdDate' => String.valueOf(c.CreatedDate),
                    'closedDate' => String.valueOf(c.ClosedDate),
                    'type' => c.Type,
                    'reason' => c.Reason,
                    'accountName' => c.Account != null ? c.Account.Name : null,
                    'accountPhone' => c.Account != null ? c.Account.Phone : null
                };

                String jsonPayload = JSON.serialize(data);

                HttpRequest req = new HttpRequest();
                req.setEndpoint('{VERBEX_WRAPPER_API_URL}/trigger-obd-closed-case');
                req.setMethod('POST');
                req.setHeader('Content-Type', 'application/json');
                req.setBody(jsonPayload);

                Http http = new Http();
                HttpResponse res = http.send(req);

                System.debug('API Response: ' + res.getBody());
            } catch (Exception e) {
                System.debug('Callout error: ' + e.getMessage());
            }
        }
    }
    ```

---

##### 3. ⚙️ Create Trigger: `CaseTrigger`

1. Go to `File → New → Apex Trigger`
2. Name: `CaseTrigger`
3. SObject: `Case`
4. Paste:

    ```apex
    trigger CaseTrigger on Case (after update) {
        for (Case c : Trigger.new) {
            Case oldCase = Trigger.oldMap.get(c.Id);
            if (c.Status == 'Closed') {
                CaseAPIHandler.sendCaseData(c.Id);
            }
        }
    }
    ```


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
IN_ENG_AGENT_ID=""
IN_BN_AGENT_ID=""
OUT_ENG_AGENT_ID=""
OUT_ENG_AGENT_PHONE_NUMBER=""
OUT_BN_AGENT_ID=""
AUTH_TOKEN=""

# Database Configuration
DB_URI=""

# Salesforce Configuration
SALESFORCE_CONSUMER_ID=""
SALESFORCE_CONSUMER_SECRET=""
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
