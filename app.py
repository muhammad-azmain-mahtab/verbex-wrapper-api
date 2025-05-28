from flask import Flask, request, jsonify, make_response
from requests_oauthlib import OAuth1
import requests
from urllib.parse import quote_plus
from functools import wraps
from sqlalchemy import create_engine
from time import sleep
import json
import pandas as pd
from apscheduler.schedulers.background import BackgroundScheduler
import os
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

# Magento Configuration
MAGENTO_BASE_URL = os.getenv("MAGENTO_BASE_URL")
MAGENTO_USERNAME = os.getenv("MAGENTO_USERNAME")
MAGENTO_PASSWORD = os.getenv("MAGENTO_PASSWORD")

# Verbex AI Agent Configuration
AI_AGENT_ID = os.getenv("AI_AGENT_ID")
AUTH_TOKEN = os.getenv("AUTH_TOKEN")

# Database Configuration
DB_URI = os.getenv("DB_URI")

# Salesforce Configuration
SALESFORCE_CLIENT_ID = os.getenv("SALESFORCE_CLIENT_ID")
SALESFORCE_CLIENT_SECRET = os.getenv("SALESFORCE_CLIENT_SECRET")
SALESFORCE_USERNAME = os.getenv("SALESFORCE_USERNAME")
SALESFORCE_PASSWORD = os.getenv("SALESFORCE_PASSWORD")
SALESFORCE_TOKEN_URL = os.getenv("SALESFORCE_TOKEN_URL")
SALESFORCE_INSTANCE_URL = os.getenv("SALESFORCE_INSTANCE_URL")

# APScheduler
SYNC_INTERVAL_MINUTES = int(os.getenv("SYNC_INTERVAL_MINUTES", 1440)) # 24 Hours

def log_request_input(endpoint_name):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            data = request.get_json()
            print("===============================================================================")
            print(f"[{endpoint_name}] Request:")
            print(data)

            response = func(*args, **kwargs)

            resp = make_response(response)
            print(f"[{endpoint_name}] Response:")
            print(resp.get_data(as_text=True))
            print("===============================================================================")

            return response
        return wrapper
    return decorator

@app.route("/", methods=["GET"])
def health_check():
    return jsonify({"status": "API is running"}), 200

def get_magento_token():
    url = f"{MAGENTO_BASE_URL}/rest/V1/integration/admin/token"
    payload = {
        'username': MAGENTO_USERNAME,
        'password': MAGENTO_PASSWORD
    }

    try:
        response = requests.post(url, json=payload, verify=False)
        response.raise_for_status()
        return response.text.strip('"')  # Remove quotes from raw string
    except requests.exceptions.HTTPError as http_err:
        print(f"Failed to get token: {http_err} - {response.text}")
    except Exception as err:
        print(f"Unexpected error: {err}")
    return None

def get_salesforce_token():
    payload = {
        'grant_type': 'password',
        'client_id': SALESFORCE_CLIENT_ID,
        'client_secret': SALESFORCE_CLIENT_SECRET,
        'username': SALESFORCE_USERNAME,
        'password': SALESFORCE_PASSWORD
    }
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}

    response = requests.post(SALESFORCE_TOKEN_URL, headers=headers, data=payload)
    response.raise_for_status()
    return response.json()["access_token"]

@app.route("/products", methods=["POST"])
@log_request_input("/products")
def get_products():
    data = request.get_json()
    keyword = data.get("keyword", "") if data else ""

    token = get_magento_token()
    if not token:
        return jsonify({"error": "Failed to authenticate with Magento"}), 500

    headers = {
        "Authorization": f"Bearer {token}"
    }

    product_search_url = f"{MAGENTO_BASE_URL}/rest/V1/products"
    search_params = {
        "searchCriteria[filterGroups][0][filters][0][field]": "name",
        "searchCriteria[filterGroups][0][filters][0][value]": f"%{keyword}%",
        "searchCriteria[filterGroups][0][filters][0][condition_type]": "like"
    }

    try:
        response = requests.get(product_search_url, headers=headers, params=search_params, verify=False)
        response.raise_for_status()
        products_data = response.json()

        simplified_products = []

        for item in products_data.get("items", []):
            sku = item.get("sku")
            name = item.get("name")
            price = item.get("price")

            # Fetch stock quantity for each product
            stock_url = f"{MAGENTO_BASE_URL}/rest/default/V1/stockItems/{sku}"
            try:
                stock_response = requests.get(stock_url, headers=headers, verify=False)
                stock_response.raise_for_status()
                stock_data = stock_response.json()
                qty = stock_data.get("qty")
            except requests.exceptions.RequestException:
                qty = None 

            simplified_products.append({
                "name": name,
                "price": price,
                "sku": sku,
                "stock_qty": qty
            })

        return jsonify({"products": simplified_products}), 200

    except requests.exceptions.RequestException as e:
        return jsonify({"error": str(e)}), 500
    
@app.route("/salesforce-account", methods=["POST"])
@log_request_input("/salesforce-account")
def get_salesforce_account():
    data = request.get_json()
    phone = data.get("phone")

    if not phone:
        return jsonify({"error": "Missing 'phone' in request body"}), 400

    access_token = get_salesforce_token()
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    try:
        # Get Account by phone
        account_query = f"SELECT Id, Name, Phone FROM Account WHERE Phone='{phone}' ORDER BY CreatedDate DESC LIMIT 1"
        encoded_account_query = quote_plus(account_query)
        account_url = f"{SALESFORCE_INSTANCE_URL}/services/data/v59.0/query?q={encoded_account_query}"

        account_response = requests.get(account_url, headers=headers)
        account_response.raise_for_status()
        account_data = account_response.json()

        if not account_data["records"]:
            return jsonify({"error": "No account found for this phone number."}), 404

        account = account_data["records"][0]
        account_name = account["Name"]
        account_phone = account.get("Phone", "")

        # Get latest Opportunity linked to Account by name, including Id and CloseDate
        opportunity_query = f"""
            SELECT Id, Name, CloseDate, Account.Name, Account.Phone
            FROM Opportunity
            WHERE Account.Name = '{account_name}'
            ORDER BY CloseDate DESC
            LIMIT 1
        """
        encoded_opportunity_query = quote_plus(opportunity_query)
        opportunity_url = f"{SALESFORCE_INSTANCE_URL}/services/data/v59.0/query?q={encoded_opportunity_query}"

        opportunity_response = requests.get(opportunity_url, headers=headers)
        opportunity_response.raise_for_status()
        opportunity_data = opportunity_response.json()

        opportunity = opportunity_data["records"][0] if opportunity_data["records"] else None

        response = {
            "Customer Name": account_name,
            "Customer Phone": account_phone,
            "Past Purchase": opportunity["Name"] if opportunity else "N/A",
            "Purchased on": opportunity["CloseDate"] if opportunity else "N/A",
            "Purchase ID": opportunity["Id"] if opportunity else "N/A"
        }

        return jsonify(response), 200

    except requests.exceptions.RequestException as e:
        return jsonify({"error": str(e)}), 500

@app.route("/create-salesforce-ticket", methods=["POST"])
@log_request_input("/create-salesforce-ticket")
def create_salesforce_ticket():
    data = request.get_json()
    phone = data.get("phone")
    subject = data.get("subject", "Service")
    description = data.get("description", "No description provided.")
    # priority = data.get("priority", "Medium")
    # status = data.get("status", "New")
    status = "New"
    priority = "Medium"
    case_type = data.get("type", "Pending")
    case_reason = data.get("reason", "Pending")

    if not phone:
        return jsonify({"error": "Missing 'phone' in request body"}), 400

    access_token = get_salesforce_token()
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    try:
        # Get Account ID using phone number
        account_query = f"SELECT Id FROM Account WHERE Phone = '{phone}' ORDER BY CreatedDate DESC LIMIT 1"
        encoded_query = quote_plus(account_query)
        account_url = f"{SALESFORCE_INSTANCE_URL}/services/data/v59.0/query?q={encoded_query}"

        account_response = requests.get(account_url, headers=headers)
        account_response.raise_for_status()
        account_data = account_response.json()

        if not account_data["records"]:
            return jsonify({"error": "No account found for this phone number."}), 404

        account_id = account_data["records"][0]["Id"]

        # Create Case
        payload = {
            "Subject": subject,
            "Description": description,
            "Status": status,
            "Priority": priority,
            "Origin": "Web",
            "AccountId": account_id,
            "Type": case_type,
            "Reason": case_reason
        }

        case_url = f"{SALESFORCE_INSTANCE_URL}/services/data/v59.0/sobjects/Case"
        case_response = requests.post(case_url, headers=headers, json=payload)
        case_response.raise_for_status()

        case_id = case_response.json().get("id")

        # Get Case Number using Case ID
        case_lookup_url = f"{SALESFORCE_INSTANCE_URL}/services/data/v59.0/sobjects/Case/{case_id}"
        case_lookup_response = requests.get(case_lookup_url, headers=headers)
        case_lookup_response.raise_for_status()

        case_data = case_lookup_response.json()
        case_number = case_data.get("CaseNumber")

        return jsonify({
            "message": "Case created successfully",
            "case_id": case_id,
            "case_number": case_number
        }), 201

    except requests.exceptions.RequestException as e:
        return jsonify({"error": str(e)}), 500

@app.route("/get-case-info", methods=["POST"])
@log_request_input("/get-case-info")
def get_case_info():
    data = request.get_json()
    case_number = data.get("case_number") if data else None

    if not case_number:
        return jsonify({"error": "Missing 'case_number' in request body"}), 400

    try:
        access_token = get_salesforce_token()
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        # Query for case info using CaseNumber
        soql = f"""
            SELECT Id, CaseNumber, Subject, Description, Status,
                   Priority, AccountId, CreatedDate, ClosedDate,
                   Type, Reason
            FROM Case
            WHERE CaseNumber = '{case_number}'
        """
        query_url = f"{SALESFORCE_INSTANCE_URL}/services/data/v59.0/query?q={quote_plus(soql)}"

        response = requests.get(query_url, headers=headers)
        response.raise_for_status()

        data = response.json()
        records = data.get("records", [])

        if not records:
            return jsonify({"error": "No case found with that CaseNumber."}), 404

        return jsonify(records[0]), 200

    except requests.exceptions.RequestException as e:
        return jsonify({"error": str(e)}), 500

def fetch_and_store_calls(log_auto=False):
    try:
        headers = {'Authorization': f'Bearer {AUTH_TOKEN}'}
        engine = create_engine(DB_URI)

        calls_url = f"https://api.verbex.ai/v1/calls/?ai_agent_ids={AI_AGENT_ID}&page_size=1000"
        calls_response = requests.get(calls_url, headers=headers)
        calls_data = calls_response.json()
        calls = calls_data.get('calls', [])

        all_messages = []
        all_analyses = []

        for call in calls:
            call_id = call.get("_id")
            ai_agent_name = call.get("ai_agent_name")
            call_status = call.get("call_status")
            call_start_time = call.get("call_start_time")
            call_end_time = call.get("call_end_time")
            recorded_call_audio_url = call.get("recorded_call_audio_url")
            call_duration_seconds = call.get("call_duration_seconds")
            call_type = call.get("call_type")
            call_finish_reason = call.get("call_finish_reason")
            initial_response_time = None
            messages = call.get("messages", [])

            if not isinstance(messages, list):
                continue

            for msg_index, message in enumerate(messages):
                message_role = message.get('role')
                message_content = message.get('content')

                if isinstance(message_content, str):
                    try:
                        ts_part, message_content = message_content.split('s - ', 1)
                        if ts_part.startswith('('):
                            ts_part = ts_part[1:]

                        if 'Playing welcome message' in message_content:
                            initial_response_time = ts_part

                        message_content = message_content.split(')', 1)[1].strip()
                        message_timestamp_seconds = float(ts_part)
                    except Exception:
                        message_timestamp_seconds = None
                        message_content = message.get('content')

                if message_content != '':
                    all_messages.append({
                        'call_id': call_id,
                        'ai_agent_id': AI_AGENT_ID,
                        'ai_agent_name': ai_agent_name,
                        'call_status': call_status,
                        'call_start_time': call_start_time,
                        'call_end_time': call_end_time,
                        'call_duration_seconds': call_duration_seconds,
                        'call_type': call_type,
                        'call_finish_reason': call_finish_reason,
                        'recorded_call_audio_url': recorded_call_audio_url,
                        'message_index': msg_index,
                        'message_role': message_role,
                        'message_content': message_content,
                        'message_timestamp_seconds': message_timestamp_seconds,
                        'initial_response_time': initial_response_time
                    })

            # Post-call analysis
            analysis_url = f"https://api.verbex.ai/v2/ai-agents/{AI_AGENT_ID}/postcall-analysis/results/{call_id}"
            try:
                analysis_response = requests.get(analysis_url, headers=headers)
                analysis_json = analysis_response.json()
                if analysis_json.get('status') != 200:
                    continue

                items = analysis_json.get('data', {}).get('items', [])
                if not items:
                    continue

                all_analyses.append({
                    'call_id': call_id,
                    'analysis_name': items[0].get('name'),
                    'analysis_result': items[0].get('result')
                })

            except Exception as e:
                print(f"Analysis failed for {call_id}: {e}")

            sleep(0.3)

        df_messages = pd.DataFrame(all_messages)
        df_analysis = pd.DataFrame(all_analyses)

        df_messages.to_sql("call_messages", engine, if_exists="replace", index=False)
        df_analysis.to_sql("call_analysis", engine, if_exists="replace", index=False)

        if log_auto:
            print(f"[AUTO SYNC] Synced {len(calls)} calls, {len(df_messages)} messages, {len(df_analysis)} analyses.")

        return {
            "status": "success",
            "calls_processed": len(calls),
            "messages_saved": len(df_messages),
            "analyses_saved": len(df_analysis)
        }

    except Exception as e:
        print(f"[ERROR] {str(e)}")
        return {
            "status": "error",
            "error": str(e)
        }

@app.route("/sync-calls", methods=["GET"])
def sync_calls_endpoint():
    result = fetch_and_store_calls()
    return jsonify(result), 200

if __name__ == "__main__":
    scheduler = BackgroundScheduler()
    scheduler.add_job(lambda: fetch_and_store_calls(log_auto=True), 'interval', minutes=SYNC_INTERVAL_MINUTES)
    scheduler.start()

    app.run(host = '0.0.0.0', port = 4288, debug=True)
