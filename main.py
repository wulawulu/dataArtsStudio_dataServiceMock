# coding=utf-8
import requests
from apig_sdk import signer

if __name__ == '__main__':
    sig = signer.Signer()
    sig.Key = "app_key1"
    sig.Secret = "app_secret1"

    r = signer.HttpRequest("POST",
                           "http://10.0.0.4/itg/yx20dzjx/dws/get_dim_itg_location_by_cust_no_cust_no",
                           {"x-stage": "RELEASE"},
                           "body")
    sig.Sign(r)
    print(r.headers["X-Sdk-Date"])
    print(r.headers["Authorization"])
    resp = requests.request(r.method, r.scheme + "://" + r.host + r.uri, headers=r.headers, data=r.body)
    print(resp.status_code, resp.reason)
    print(resp.content)
