import requests

TOKEN = "8906564302:AAFMPnXvenSWnXwOa-UJFBgU_9e2V2e2FcU"

URL = f"https://api.telegram.org/bot{TOKEN}/getMe"

response = requests.get(URL)
print(response.json())
