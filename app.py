from flask import Flask, request, jsonify, make_response
import requests
from urllib.parse import quote_plus
from functools import wraps
from sqlalchemy import create_engine
from time import sleep
import pandas as pd
from apscheduler.schedulers.background import BackgroundScheduler
import os
from dotenv import load_dotenv
import re
from datetime import datetime, timezone
import time

load_dotenv()
app = Flask(__name__)

# Magento Configuration
MAGENTO_BASE_URL = os.getenv("MAGENTO_BASE_URL")
MAGENTO_USERNAME = os.getenv("MAGENTO_USERNAME")
MAGENTO_PASSWORD = os.getenv("MAGENTO_PASSWORD")

# Verbex AI Agent Configuration
IN_ENG_AGENT_ID = os.getenv("IN_ENG_AGENT_ID")
IN_BN_AGENT_ID = os.getenv("IN_BN_AGENT_ID")
OUT_ENG_AGENT_ID = os.getenv("OUT_ENG_AGENT_ID")
OUT_BN_AGENT_ID = os.getenv("OUT_BN_AGENT_ID")
OUT_ENG_AGENT_PHONE_NUMBER = os.getenv("OUT_ENG_AGENT_PHONE_NUMBER")
AUTH_TOKEN = os.getenv("AUTH_TOKEN")

# Database Configuration
DB_URI = os.getenv("DB_URI")

# Salesforce Configuration
SALESFORCE_CONSUMER_ID = os.getenv("SALESFORCE_CONSUMER_ID")
SALESFORCE_CONSUMER_SECRET = os.getenv("SALESFORCE_CONSUMER_SECRET")
SALESFORCE_USERNAME = os.getenv("SALESFORCE_USERNAME")
SALESFORCE_PASSWORD = os.getenv("SALESFORCE_PASSWORD")
SALESFORCE_TOKEN_URL = os.getenv("SALESFORCE_TOKEN_URL")
SALESFORCE_INSTANCE_URL = os.getenv("SALESFORCE_INSTANCE_URL")

# APScheduler
SYNC_INTERVAL_MINUTES = int(os.getenv("SYNC_INTERVAL_MINUTES")) 

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
        'client_id': SALESFORCE_CONSUMER_ID,
        'client_secret': SALESFORCE_CONSUMER_SECRET,
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
    customer_name = data.get("customer_name")

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
            # Create new Account if none found
            create_account_payload = {
                "Name": customer_name,
                "Phone": phone
            }
            create_url = f"{SALESFORCE_INSTANCE_URL}/services/data/v59.0/sobjects/Account"
            create_response = requests.post(create_url, headers=headers, json=create_account_payload)
            create_response.raise_for_status()
            account_id = create_response.json().get("id")
        else:
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

    if len(case_number) < 8:
        case_number = case_number.zfill(8)

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
                   Type, Reason, Customer_Note__c
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

def fetch_and_store_calls(agent_id=IN_ENG_AGENT_ID, log_auto=False):
    try:
        headers = {'Authorization': f'Bearer {AUTH_TOKEN}'}
        engine = create_engine(DB_URI)

        calls_url = f"https://api.verbex.ai/v1/calls?ai_agent_ids={agent_id}&page_size=100&sort_direction=desc"
        calls_response = requests.get(calls_url, headers=headers)
        if calls_response.status_code != 200:
            print(f"[ERROR] Failed to fetch calls: {calls_response.status_code} {calls_response.text}")
            return {
                "status": "error",
                "error": f"Failed to fetch calls: {calls_response.status_code} {calls_response.text}"
            }
        try:
            calls_data = calls_response.json()
        except Exception as e:
            print(f"[ERROR] Could not parse JSON: {e} - Response: {calls_response.text}")
            return {
                "status": "error",
                "error": f"Could not parse JSON: {e} - Response: {calls_response.text}"
            }
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
                        'ai_agent_id': agent_id,
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
            analysis_url = f"https://api.verbex.ai/v2/ai-agents/{agent_id}/postcall-analysis/results/{call_id}"
            try:
                analysis_response = requests.get(analysis_url, headers=headers)
                analysis_json = analysis_response.json()

                items = analysis_json.get('data', {}).get('items', [])
                if not items:
                    continue

                for item in items:
                    name = item.get('name')
                    result = item.get('result')

                    if name == 'Products Searched ' and result:
                        # Split using regex to get numbered items (1. ..., 2. ..., etc.)
                        products = re.split(r'\d+\.\s*', result)
                        products = [p.strip() for p in products if p.strip()]  # remove empty entries

                        for product in products:
                            all_analyses.append({
                                'call_id': call_id,
                                'analysis_name': name.strip(),
                                'analysis_result': product
                            })
                    else:
                        all_analyses.append({
                            'call_id': call_id,
                            'analysis_name': name,
                            'analysis_result': result
                        })

            except Exception as e:
                print(f"Analysis failed for {call_id}: {e}")

            sleep(0.3)

        df_messages = pd.DataFrame(all_messages)
        df_analysis = pd.DataFrame(all_analyses)

        if agent_id == IN_BN_AGENT_ID:
            mssg_table = "call_messages_in_bn"
            anal_table = "call_analysis_in_bn"
        elif agent_id == OUT_ENG_AGENT_ID:
            mssg_table = "call_messages_out_en"
            anal_table = "call_analysis_out_en"
        elif agent_id == OUT_BN_AGENT_ID:
            mssg_table = "call_messages_out_bn"
            anal_table = "call_analysis_out_bn"
        else:
            mssg_table = "call_messages"
            anal_table = "call_analysis"

        df_messages.to_sql(mssg_table, engine, if_exists="replace", index=False)
        df_analysis.to_sql(anal_table, engine, if_exists="replace", index=False)

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

def fetch_salesforce_cases():
    access_token = get_salesforce_token()
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    base_query = (
        "SELECT Id, CaseNumber, Subject, Status, Priority, Origin, Type, Reason, AccountId, CreatedDate, ClosedDate "
        "FROM Case "
        f"WHERE Owner.Username = '{SALESFORCE_USERNAME}'"
    )

    encoded_query = quote_plus(base_query)
    query_url = f"{SALESFORCE_INSTANCE_URL}/services/data/v59.0/query?q={encoded_query}"

    cases = []

    try:
        while query_url:
            response = requests.get(query_url, headers=headers)
            response.raise_for_status()
            data = response.json()

            cases.extend(data.get("records", []))

            next_records_url = data.get("nextRecordsUrl")
            if next_records_url:
                query_url = f"{SALESFORCE_INSTANCE_URL}{next_records_url}"
            else:
                break
        
        if cases:
            try:
                df_cases = pd.DataFrame(cases)
                
                if 'attributes' in df_cases.columns:
                    df_cases = df_cases.drop(columns=['attributes'])

                engine = create_engine(DB_URI)
                df_cases.to_sql("salesforce_cases", engine, if_exists="replace", index=False)
                
                print(f"Successfully saved {len(df_cases)} Salesforce cases to the 'salesforce_cases' table.")

            except Exception as db_error:
                print(f"[ERROR] Could not save Salesforce cases to database: {db_error}")

        return {
            "tickets_saved": len(cases),
        }

    except requests.exceptions.RequestException as e:
        return jsonify({"error": str(e)}), 500

# reason = case_category = category of ticket = Service, Complaint, Delivery
# type = case_status = service info = Product Fixed, Product Not Fixed.

# Endpoint to trigger outbound call manually
@app.route("/trigger-outbound-call", methods=["POST"])
def trigger_outbound_call(to_number= "+8801852341413",
                          case_id = "00001100", 
                          case_status = "Fixed", 
                          case_subject = "Broken TV during delivery", 
                          case_description = "The delivery person accidentally dropped the TV, resulting in damage. Requesting a replacement.", 
                          call_reason = "escalate",
                          case_category = "Service",
                          case_created = "2025-06-18T04:51:06.000+0000",
                          customer_note = "TV bulbs fixed inside panel, replaced with new ones."): 

    if case_category == "Service" and case_status == "Fixed":
        case_status = "Product Fixed"
    elif case_category == "Service" and case_status == "Not Fixed":
        case_status = "Product Not Fixed"
    elif case_category == "Complaint" and case_status == "Fixed":
        case_status = "Complaint Handled"
    elif case_category == "Complaint" and case_status == "Not Fixed":
        case_status = "Complaint Not Handled"

    data = {
        "from_number": OUT_ENG_AGENT_PHONE_NUMBER,
        "to_number": to_number,
        "direction": "outbound",
        "override_ai_agent_id": OUT_BN_AGENT_ID,
        "metadata": {},
        "pia_llm_dynamic_data": {
            "case_id": case_id,
            "case_status": case_status,
            "case_subject": case_subject,
            "case_description": case_description,
            "call_reason": call_reason,
            "case_category": case_category,
            "case_created": case_created,
            "customer_note": customer_note
        }
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {AUTH_TOKEN}"
    }
    try:
        response = requests.post('https://api.verbex.ai/v1/calls/dial-outbound-phone-call', json=data, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        return {"error": str(e)}

def scheduled_outbound_call():
    access_token = get_salesforce_token()
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    soql = f"""
        SELECT Id, CaseNumber, Subject, Description, Status, Priority, CreatedDate, ClosedDate, Type, Reason, Account.Name, Account.Phone
        FROM Case
        WHERE Owner.Username = '{SALESFORCE_USERNAME}' AND Status != 'Closed'
    """

    encoded_query = quote_plus(soql)
    query_url = f"{SALESFORCE_INSTANCE_URL}/services/data/v59.0/query?q={encoded_query}"

    try:
        response = requests.get(query_url, headers=headers)
        response.raise_for_status()
        data = response.json()
        records = data.get("records", [])
        case = records[0]

        now = datetime.now(timezone.utc)
        # Salesforce datetime format
        sf_dt_format = "%Y-%m-%dT%H:%M:%S.%f%z"

        if not records:
            print("No cases found for outbound call.")
            return
        
        responses = [] 

        for case in records:
            created_dt = datetime.strptime(case["CreatedDate"], sf_dt_format)
            delta = now - created_dt

            if delta.days >= 1:
                account_phone = case.get("Account", {}).get("Phone", "")
                case_id = case["Id"]
                case_number = case["CaseNumber"]
                subject = case["Subject"]
                description = case["Description"]
                case_type = case.get("Type")
                case_category = case.get("Reason")
                case_created = case["CreatedDate"]

                # Update case status to 'Escalated'
                update_url = f"{SALESFORCE_INSTANCE_URL}/services/data/v59.0/sobjects/Case/{case_id}"
                update_payload = {
                    "Status": "Escalated",
                    "Priority": "High"
                }
                update_headers = {
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"
                }

                response = requests.patch(update_url, headers=update_headers, json=update_payload)
                response.raise_for_status()

                print(f"✅ Updated case {case_number} ({case_id}) to Status='Escalated' and Priority='High'")
                print(f"Triggering outbound call to {account_phone} for case: {case_number} ({case_id}) with subject: '{subject}' and description: '{description}' and status: {case_type} and category: {case_category} and case date: {case_created}.")

                call_response = trigger_outbound_call(to_number=account_phone,
                                    case_id=case_id,
                                    case_status=case_type,
                                    case_subject=subject,
                                    case_description=description,
                                    call_reason="escalate",
                                    case_category=case_category,
                                    case_created=case_created)
                
                responses.append(call_response)
            
                #🕒 Wait for 10 minutes (600 seconds) before next call
                print("Waiting 10 minutes before next call...")
                time.sleep(600)

    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Failed to fetch cases for outbound call: {str(e)}")

    return jsonify({
        "calls_triggered": len(responses),
        "details": responses
    }), 200

def scheduled_callback_call():
    try:
        engine = create_engine(DB_URI)
        
        # Fetch callbacks that haven't been made yet
        with engine.connect() as connection:
            query = "SELECT * FROM to_callback WHERE called_again = FALSE"
            callbacks_df = pd.read_sql(query, connection)

        if callbacks_df.empty:
            print("No pending callbacks.")
            return

        responses = []

        for index, row in callbacks_df.iterrows():
            print(f"Triggering callback for call_id: {row['call_id']}")

            call_response = trigger_outbound_call(
                to_number=row["to_number"],
                case_id=row["case_id"],
                case_status=row["case_status"],
                case_subject=row["case_subject"],
                case_description=row["case_description"],
                call_reason=row["call_reason"],
                case_category=row["case_category"],
                case_created=row["case_created"]
            )
            responses.append(call_response)

            if "error" not in call_response:
                # Update the record to mark as called
                with engine.connect() as connection:
                    from sqlalchemy import text
                    update_query = text("UPDATE to_callback SET called_again = TRUE WHERE call_id = :call_id")
                    connection.execute(update_query, {"call_id": row['call_id']})
                    connection.commit()
                print(f"✅ Marked callback as completed for call_id: {row['call_id']}")
            else:
                print(f"[ERROR] Failed to trigger callback for call_id {row['call_id']}: {call_response.get('error')}")
            
            # Wait before processing the next callback
            print("Waiting 1 minute before next callback...")
            time.sleep(60)

        print(f"Scheduled callback check finished. Triggered {len(responses)} calls.")

    except Exception as e:
        print(f"[ERROR] in scheduled_callback_call: {str(e)}")

# Endpoint to trigger scheduled outbound call manually
@app.route("/scheduled-outbound-call", methods=["GET"])
def scheduled_outbound_call_endpoint():
    try:
        result = scheduled_outbound_call()
        return result
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@app.route("/scheduled-callback-call", methods=["GET"])
def scheduled_callback_call_endpoint():
    try:
        scheduled_callback_call()
        return jsonify({"message": "Callback check completed"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@app.route("/sync-calls-tickets", methods=["GET"])
def sync_calls_endpoint():
    calls_in_eng = fetch_and_store_calls(agent_id=IN_ENG_AGENT_ID)
    calls_in_bn = fetch_and_store_calls(agent_id=IN_BN_AGENT_ID)
    calls_out_eng = fetch_and_store_calls(agent_id=OUT_ENG_AGENT_ID)
    calls_out_bn = fetch_and_store_calls(agent_id=OUT_BN_AGENT_ID)
    cases = fetch_salesforce_cases()
    return jsonify({
        "calls_in_eng": calls_in_eng,
        "calls_in_bn": calls_in_bn, 
        "calls_out_eng": calls_out_eng, 
        "calls_out_bn": calls_out_bn,  
        "cases": cases
        }), 200


@app.route("/trigger-obd-closed-case", methods=["POST"])
@log_request_input("/trigger-obd-closed-case")
def trigger_obd_closed_case():
    try:
        case = request.get_json()

        account_phone = case.get('accountPhone')
        case_id = case.get('id')
        case_number = case.get('caseNumber')
        subject = case.get('subject')
        description = case.get('description')
        case_type = case.get("type")
        case_category = case.get('reason')

        print(f"Triggering outbound call to {account_phone} for case: {case_number} ({case_id}) "
              f"with subject: '{subject}' and description: '{description}' and status: {case_type} "
              f"and category: {case_category}.")

        call_response = trigger_outbound_call(
            to_number=account_phone,
            case_id=case_id,
            case_status=case_type,
            case_subject=subject,
            case_description=description,
            call_reason="rating",
            case_category=case_category
        )
        if "error" in call_response:
            print(f"Call failed: {call_response['error']}")
            return jsonify(call_response), 500

        print(f"Call response: {call_response}")
        return jsonify({"message": "success", "call_response": call_response}), 200

    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/log-callback", methods=["POST"])
@log_request_input("/log-callback")
def log_callback():
    data = request.json

    try:
        record = {
            "to_number": data["to_number"],
            "case_id": data["case_id"],
            "case_status": data["case_status"],
            "case_subject": data["case_subject"],
            "case_description": data["case_description"],
            "call_reason": data["call_reason"],
            "case_category": data["case_category"],
            "call_id": data["call_id"],
            "called_again": False,
            "preferred_time": data["preferred_time"],
            "logged_at": data["logged_at"],
            "case_created": data["case_created"]
        }

        df = pd.DataFrame([record])

        engine = create_engine(DB_URI)
                
        # Save to DB
        df.to_sql("to_callback", engine, if_exists="append", index=False)

        return jsonify({"message": "Callback logged successfully"}), 201

    except Exception as e:
        return jsonify({"error": f"Failed to log callback: {str(e)}"}), 500

if __name__ == "__main__":
    scheduler = BackgroundScheduler()
    scheduler.add_job(lambda: fetch_and_store_calls(agent_id=IN_ENG_AGENT_ID, log_auto=True), 'interval', minutes=SYNC_INTERVAL_MINUTES)
    scheduler.add_job(lambda: fetch_and_store_calls(agent_id=IN_BN_AGENT_ID, log_auto=True), 'interval', minutes=SYNC_INTERVAL_MINUTES)
    
    scheduler.add_job(lambda: fetch_and_store_calls(agent_id=OUT_ENG_AGENT_ID, log_auto=True), 'interval', minutes=SYNC_INTERVAL_MINUTES)
    scheduler.add_job(lambda: fetch_and_store_calls(agent_id=OUT_BN_AGENT_ID, log_auto=True), 'interval', minutes=SYNC_INTERVAL_MINUTES)

    scheduler.add_job(lambda: fetch_salesforce_cases(), 'interval', minutes=SYNC_INTERVAL_MINUTES)
    # scheduler.add_job(scheduled_outbound_call, 'interval', minutes=SYNC_INTERVAL_MINUTES)
    # scheduler.add_job(scheduled_callback_call, 'interval', minutes=SYNC_INTERVAL_MINUTES)
    scheduler.start()

    app.run(host = '0.0.0.0', port = 4288, debug=True)
