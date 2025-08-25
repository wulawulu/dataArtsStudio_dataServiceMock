 # coding=utf-8
import requests
import json
from apig_sdk import signer

if __name__ == '__main__':
    sig = signer.Signer()
    sig.Key = "app_key1"
    sig.Secret = "app_secret1"

    r = signer.HttpRequest("POST",
                            "http://localhost:80/customer/batch",
                            {"content-type": "application/json"},
                            """
                            {
                            "ids":
                                [
                                    "5000000000000",
                                    "5000000000001",
                                    "5000000000002",
                                    "5000000000003",
                                    "5000000000004",
                                    "5000000000005",
                                    "5000000000006"
                                ]
                            }
                            """)
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

    r = signer.HttpRequest("POST",
                        "http://localhost/poi/search",
                        {"content-type": "application/json"},
                        """{
                            "province": "重庆市",
                            "city": "重庆市", 
                            "district": "大渡口区"
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

    r = signer.HttpRequest("POST",
                        "http://localhost/region/search",
                        {"content-type": "application/json"},
                        """{
                            "region_ids": ["5210000000"]
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
