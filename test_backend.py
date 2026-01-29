 # coding=utf-8
import requests
import json
from apig_sdk import signer

if __name__ == '__main__':
    sig = signer.Signer()
    sig.Key = "app_key1"
    sig.Secret = "app_secret1"

    r = signer.HttpRequest("POST",
                        "http://localhost:80/itg/yx20dzjx/dws/get_dim_itg_location_by_cust_no_cust_no",
                        {"content-type": "application/json"},
                        """{
                            "startTime": "2026-01-14 16:30:00",
                            "endTime": "2026-01-15 10:20:00",
                            "pageNum": 1,
                            "pageSize": 100
                        }""")
    sig.Sign(r)
    print(r.headers["X-Sdk-Date"])
    print(r.headers["Authorization"])
    resp = requests.request(r.method, r.scheme + "://" + r.host + r.uri, headers=r.headers, data=r.body)
    print(resp.status_code, resp.reason)
    # 如果是 JSON 响应，格式化输出中文
    if resp.headers.get('content-type', '').startswith('application/json'):
        try:
            data = resp.json()
            print(json.dumps(data, ensure_ascii=False, indent=2))
        except:
            print(resp.content.decode('utf-8'))
    else:
        print(resp.content.decode('utf-8'))
