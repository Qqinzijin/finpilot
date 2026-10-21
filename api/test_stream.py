import requests

response = requests.post(
    "http://127.0.0.1:8888/chat/stream",   # ← 端口改成 8888
    json={"message": "贵州茅台现在多少钱？"},
    stream=True,
)

print(f"状态码: {response.status_code}")
print("-" * 50)

for line in response.iter_lines(decode_unicode=True):
    if line:
        print(line)