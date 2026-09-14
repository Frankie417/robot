#-*- coding: utf-8 -*-
import requests
import time
import hashlib
import base64
import re
import struct

URL = "http://openapi.xfyun.cn/v2/aiui"
APPID = "5beaacac"
API_KEY = "4227d60d150c455db467b623d7ae183d"
AUE = "raw"
AUTH_ID = "2894c985bf8b1111c6728db79d3479ae"
DATA_TYPE = "audio"
SAMPLE_RATE = "16000"
SCENE = "main"
RESULT_LEVEL = "complete"
LAT = "39.938838"
LNG = "116.368624"
#个性化参数，需转义
PERS_PARAM = "{\\\"auth_id\\\":\\\"2894c985bf8b1111c6728db79d3479ae\\\"}"
FILE_PATH = "record.wav"


def buildHeader():
    curTime = str(int(time.time()))
    param = "{\"result_level\":\""+RESULT_LEVEL+"\",\"auth_id\":\""+AUTH_ID+"\",\"data_type\":\""+DATA_TYPE+"\",\"sample_rate\":\""+SAMPLE_RATE+"\",\"scene\":\""+SCENE+"\",\"lat\":\""+LAT+"\",\"lng\":\""+LNG+"\"}"
    #使用个性化参数时参数格式如下：
    #param = "{\"result_level\":\""+RESULT_LEVEL+"\",\"auth_id\":\""+AUTH_ID+"\",\"data_type\":\""+DATA_TYPE+"\",\"sample_rate\":\""+SAMPLE_RATE+"\",\"scene\":\""+SCENE+"\",\"lat\":\""+LAT+"\",\"lng\":\""+LNG+"\",\"pers_param\":\""+PERS_PARAM+"\"}"
    paramBase64 = base64.b64encode(param.encode('utf-8'))

    m2 = hashlib.md5()
    m2.update((API_KEY + curTime + str(paramBase64, 'utf-8')).encode('utf-8'))
    checkSum = m2.hexdigest()

    header = {
        'X-CurTime': curTime,
        'X-Param': paramBase64,
        'X-Appid': APPID,
        'X-CheckSum': checkSum,
    }
    return header

def readFile(filePath):
    binfile = open(filePath, 'rb')
    data = binfile.read()
    return data

r = requests.post(URL, headers=buildHeader(), data=readFile(FILE_PATH))
#print(r.content)
dic_json = r.json()
for i in dic_json['data']:
    if(i['sub'] == "nlp" and i['intent'] != {}):
        try:
            text = i['intent']['answer']['text']
        except:
            text = "不明白你再说什么，你还是说中文吧"
        print('我 :'+i['intent']['text'])
        print('机器人 :'+text)
        break
else:
    print('没有检测到人声'.decode('UTF-8'))