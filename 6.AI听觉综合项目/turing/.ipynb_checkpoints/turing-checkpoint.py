# -*- coding: utf-8 -*-      
import json
import urllib.request
tuling='08c523158a1848f5ae4f2116ae2157a7'
api_url = "http://openapi.tuling123.com/openapi/api/v2"

while True:
    info = input('我:')
    req = {
        "perception":
        {
            "inputText":
            {
                "text": info
            },
        },
        "userInfo": 
        {
            "apiKey": "d91a2724eabd44ff9a3d4261d6ad3c32",
            "userId": "xiaowei"
        }
    }
    req = json.dumps(req).encode('utf8')
    http_post = urllib.request.Request(api_url, data=req, headers={'content-type': 'application/json'})
    response = urllib.request.urlopen(http_post)
    response_str = response.read().decode('utf8')
    response_dic = json.loads(response_str)
    results_text = response_dic['results'][0]['values']['text']
    print('机器人:' + results_text)