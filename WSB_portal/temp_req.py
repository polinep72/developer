import requests
init = requests.get('http://127.0.0.1:8090/api/dashboard/init').json()
payload = {
    'equipment': init['equipment'],
    'start_date': init['dateRange']['min'],
    'end_date': init['dateRange']['max'],
    'target_load': 8
}
resp = requests.post('http://127.0.0.1:8090/api/dashboard/data', json=payload)
print(resp.status_code)
print(resp.text[:200])
