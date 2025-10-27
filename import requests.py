import requests
 
response = requests.get("https://api.telegram.org/", verify=False, timeout=30)
if response.status_code == 200:
    print(response.text)
