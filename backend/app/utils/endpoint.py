import json
import requests
import os
import time
 
def load_token():
    if os.path.exists("token_data.json"):
        with open("token_data.json", "r") as file:
            return json.load(file)
    return {"access_token": None, "expires_at": 0}
 
def save_token(data):
    with open("token_data.json", "w") as file:
        json.dump(data, file)
 
def get_new_token():
    # print("Generating a new token...")
    payload = {
        "grant_type": "client_credentials",
        "client_id": "0oa2ghq9z2t7LY0Cl0h8",
        "client_secret": "HSfQNNVfibmWV89H7gajUyTEwnuD1WkJSdlqGiKi5832Izwi_LC3iF71zrLYzh_R",
        "scope": "customscope",
    }
    headers = {'Content-Type': "application/x-www-form-urlencoded"}
    token_url = "https://experian.oktapreview.com/oauth2/auslkzh1op2UXTy0Y0h7/v1/token"
                #"
 
    response = requests.post(token_url, data=payload, headers=headers)
 
    if response.status_code == 200:
        data = response.json()
        token_data = {
            "access_token": data['access_token'],
            "expires_at": time.time() + data['expires_in']
        }
        save_token(token_data)
        # print("New token generated and saved.")
        return token_data['access_token']
    else:
        raise Exception(f"Failed to retrieve token: {response.status_code} - {response.text}")
 
def get_active_token():
    token_data = load_token()
    if token_data['access_token'] and time.time() < token_data['expires_at']:
        # print("Using cached token.")
        return token_data['access_token']
    else:
        return get_new_token()
 
base_api_url = "https://aigateway.mn-uk-ucb.preprod-da-saas-uk.io/v2/chat/completions"
url = f"{base_api_url}"
 
token = get_active_token()
 
header = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {token}",
}
 
def sendtoEGPT(messages, max_retries=3):
 
  """
 
  Fixed version that handles both message lists and strings
 
  """
 
  if not messages:
 
    print("Error: No messages provided to sendtoEGPT")
 
    return None
 
  # Handle both list of messages (from Flask) and string input
 
  if isinstance(messages, str):
 
    formatted_messages = [{"role": "user", "content": messages}]
 
  elif isinstance(messages, list):
 
    formatted_messages = messages
 
  else:
 
    print(f"Error: Invalid message format: {type(messages)}")
 
    return None
 
  for attempt in range(max_retries):
 
    try:
 
      # Get fresh token for each retry
 
      token = get_active_token()
 
      headers = {
 
        "Content-Type": "application/json",
 
        "Authorization": f"Bearer {token}",
 
      }
 
      payload = {
 
        # "model": "gpt-4o-dev",
        # "model": "gpt-4.1-20250414-gs",
        "model":"gpt-4.1-mini-20250414-gs",
 
        "messages": formatted_messages,
 
        # "max_tokens": 4000, # Add reasonable limits
        "max_tokens": 32000, # Add reasonable limits
 
        "temperature": 0.1
 
      }
 
      print(f"Sending request to GPT (attempt {attempt + 1}/{max_retries})")
 
      response = requests.post(base_api_url, json=payload, headers=headers, timeout=300)
      print(response)
 
      if response.status_code == 200:
 
        json_response = response.json()
 
        # Check if the response has the expected structure
 
        if ("payload" in json_response and
 
          "choices" in json_response["payload"] and
 
          len(json_response["payload"]["choices"]) > 0):
 
          message = json_response["payload"]["choices"][0]["message"]["content"]
 
          print("GPT response received successfully")
 
          return message
 
        else:
 
          print(f"Unexpected response structure: {json_response}")
 
          if attempt == max_retries - 1:
 
            return None
 
      elif response.status_code == 401:
 
        print("Token expired, getting new token...")
 
        # Force token refresh
 
        get_new_token()
 
        continue
 
      else:
 
        print(f"API error: {response.status_code} - {response.text}")
 
        if attempt == max_retries - 1:
 
          return None
 
    except requests.exceptions.Timeout:
 
      print(f"Request timeout on attempt {attempt + 1}")
 
      if attempt == max_retries - 1:
 
        return None
 
    except requests.exceptions.RequestException as e:
 
      print(f"Request error on attempt {attempt + 1}: {e}")
 
      if attempt == max_retries - 1:
 
        return None
 
    except Exception as e:
 
      print(f"Unexpected error on attempt {attempt + 1}: {e}")
 
      if attempt == max_retries - 1:
 
        return None
 
    # Wait before retry
 
    if attempt < max_retries - 1:
 
      time.sleep(2 ** attempt) # Exponential backoff
 
  return None
 
 
def getEmbeddingFromEGPT(text_input: str):
    token = get_active_token()
    url = "https://aigateway.mn-uk-ucb.preprod-da-saas-uk.io/v2/embeddings"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = json.dumps({
        "input": text_input,
        "model": "egpt-dev-ada"
    })
    response = requests.post(url, headers=headers, data=payload)
    if response.status_code == 200:
        json_response = response.json()
        data = json_response.get("data", [])
        if not data or "embedding" not in data[0]:
            print(f"Embedding API returned no data or missing embedding: {json_response}")
            return []
        embedding = data[0]["embedding"]
        return embedding
    else:
        print(f"Embedding API error: {response.status_code}, {response.text}")
        return []