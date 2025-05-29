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

## Prerequisites

- Docker installed on your system.
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
DB_URI=""

# Salesforce Configuration
SALESFORCE_CLIENT_ID=""
SALESFORCE_CLIENT_SECRET=""
SALESFORCE_USERNAME=""
SALESFORCE_PASSWORD=""
SALESFORCE_INSTANCE_URL=""
SALESFORCE_TOKEN_URL=""

# APScheduler
SYNC_INTERVAL_MINUTES=1440 # set to 24 hours
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

## Usage

Once running, the API will listen for requests from the Verbex AI agent and proxy them to the configured third-party APIs (Magento/Salesforce). Please refer to your agent integration documentation for details on the expected endpoints and request formats.

## Configuration

All runtime configuration is handled via the `.env` file. Make sure all required fields are populated before starting the container.

## Contributing

Pull requests are welcome! For major changes, please open an issue first to discuss what you would like to change.

## License

[MIT](LICENSE)

---

Let me know if you want to add API endpoint documentation or anything else!
