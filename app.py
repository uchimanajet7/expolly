#!/usr/bin/env python
# -*- coding: utf-8 -*-

import boto3
import os
import requests
import json

from chalice import Chalice
from urlparse import parse_qsl
from datetime import datetime

app = Chalice(app_name='expolly')

SLACK_TOKEN = os.environ.get('slack_token')
API_KEY = os.environ.get('api_key')
TRIGGER_WORD = os.environ.get('trigger_word')
S3_BUCKET = os.environ.get('s3_bucket')


@app.route('/slack', methods=['POST'],
           content_types=['application/x-www-form-urlencoded'])
def slack():
    body = app.current_request.raw_body
    parsed_l = dict(parse_qsl(body))

    slack_token = parsed_l.get('token')
    if slack_token != SLACK_TOKEN:
        return {"text": "slack token not valid!"}

    slack_text = parsed_l.get('text')
    if slack_text:
        print('slack_text={}'.format(slack_text))

        slack_text = slack_text.lstrip(TRIGGER_WORD)
        slack_text = slack_text.replace(u"　", " ")
        slack_text = slack_text.strip()

        print('slack_text={}'.format(slack_text))
        if slack_text == "":
            return {"text": "I can not find the blank"}

        eki_list = slack_text.split()
        eki_from = None
        eki_to = None
        for eki_item in eki_list:
            if eki_from is None:
                eki_from = eki_item
            elif eki_to is None:
                eki_to = eki_item
            else:
                break

        if eki_from is None or eki_to is None:
            return {"text": "Either one is blank"}

        if eki_from == eki_to:
            return {"text": "The same station name is specified"}

        # get eki info
        response = searchCourse(eki_from, eki_to)
        if response.status_code != 200:
            return createResultMsg(response.json(), eki_from, eki_to)

        # create polly message
        msg = createMsg(response.json())
        print('msg={}'.format(msg))

        # create mp3
        content_type, stream = createMp3(msg)
        print('content_type={}'.format(content_type))
        print('stream={}'.format(stream))

        file_name = eki_from + "-" + eki_to + "_" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".mp3"
        s3_url = putS3(S3_BUCKET, file_name, stream.read(), content_type)
        print('s3_url={}'.format(s3_url))

        return {"text": msg + "\n" + s3_url}

    return {"text": "post successful."}


# exp error check and create return text
def createResultMsg(resp_json, exp_from, exp_to):
    exp_err = resp_json.get("ResultSet").get("Error")
    err_code = exp_err.get("code")
    err_text = exp_err.get("Message")

    msg = "response status code is not 200\n" + err_code + ": " + err_text

    # station error
    if err_code == "E102":
        st_text = None

        if exp_from in err_text:
            st_text = exp_from
        elif exp_to in err_text:
            st_text = exp_to

        # get station info
        response = stationLight(st_text)
        if response.status_code == 200:
            st_lsit = getStationList(response.json())
            if len(st_lsit) != 0:
                msg = msg + "\nplease specify with a unique station name.\n" + "　".join(st_lsit)

    return {"text": msg}


# get station list
def getStationList(resp_json):
    result = list()
    for point in getSafeList(resp_json.get('ResultSet').get('Point')):
        result.append(point.get("Station").get("Name"))
    return result


# stationLight
def stationLight(st_name):
    url = "https://api.apigw.smt.docomo.ne.jp/ekispertCorp/v1/stationLight"
    params = {"APIKEY": API_KEY, "name": st_name}
    headers = {"Accept": "application/json"}

    response = requests.get(url, params=params, headers=headers)
    print('stationLight={}'.format(response.text))

    return response


# safe get list
def getSafeList(item):
    if not isinstance(item, list):
        result = list()
        result.append(item)
        return result
    return item


# searchCourse
def searchCourse(eki_from, eki_to):
    url = "https://api.apigw.smt.docomo.ne.jp/ekispertCorp/v1/searchCourse"
    params = {"APIKEY": API_KEY, "from": eki_from, "to": eki_to}
    headers = {"Accept": "application/json"}

    response = requests.get(url, params=params, headers=headers)
    print('searchCourse={}'.format(response.text))

    return response


# put S3
def putS3(bucket, key, body, content_type):
    try:
        client_s3 = boto3.client('s3')

        response = client_s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
        )
        print('put_object={}'.format(response))

        url = client_s3.generate_presigned_url(
            ClientMethod='get_object',
            Params={'Bucket': bucket, 'Key': key},
            ExpiresIn=3600,
            HttpMethod='GET'
        )
    except Exception as e:
        print(e.args)

    return url


# create polly sound
def createMp3(msg):
    try:
        client_polly = boto3.client('polly', region_name="us-east-1")

        response = client_polly.synthesize_speech(
            OutputFormat='mp3',
            Text=msg,
            TextType='text',
            VoiceId='Mizuki'
        )
    except Exception as e:
        print(e.args)

    print('synthesize_speech={}'.format(response))
    return (response.get("ContentType"), response.get("AudioStream"))


# create polly message
def createMsg(resp_json):
    result_msg = None

    # Make sentences to tell
    # only one course use
    for course_item in getSafeList(resp_json.get('ResultSet').get('Course')):
        # fare
        fare_msg = None
        for fare_item in getSafeList(course_item.get('Price')):
            if fare_item.get('kind') == 'FareSummary':
                fare_msg = fare_item.get('Oneway')
                break

        print('fare_msg={}'.format(fare_msg))

        # Route
        route_item = course_item.get('Route')
        time_msg = int(route_item.get("timeOther")) + int(route_item.get("timeOnBoard")) + int(route_item.get("timeWalk"))
        transfer_cnt_msg = int(route_item.get("transferCount"))

        print('time_msg={}'.format(time_msg))
        print('transfer_cnt_msg={}'.format(transfer_cnt_msg))

        # Line
        from_train_name = None
        from_dest_datetime = None
        train_name = None
        arri_datetime = None
        for line_item in getSafeList(route_item.get("Line")):
            train_name = line_item.get("Name")
            arri_datetime = line_item.get("ArrivalState").get("Datetime").get("text")
            dest_datetime = line_item.get("DepartureState").get("Datetime").get("text")

            if from_train_name is None:
                from_train_name = train_name

            if from_dest_datetime is None:
                from_dest_datetime = dest_datetime

        to_train_name = train_name
        to_arri_datetime = arri_datetime

        print('from_train_name={}'.format(from_train_name))
        print('from_dest_datetime={}'.format(from_dest_datetime))
        print('to_train_name={}'.format(to_train_name))
        print('to_arri_datetime={}'.format(to_arri_datetime))

        if from_train_name.endswith("行"):
            from_train_name = from_train_name + "き"

        if to_train_name.endswith("行"):
            to_train_name = to_train_name + "き"

        from_date = from_dest_datetime[0:from_dest_datetime.find('T')]
        from_time = from_dest_datetime[from_dest_datetime.find('T')+1:from_dest_datetime.find('+')]
        from_time = from_time[0:from_time.rfind(":")]
        to_date = to_arri_datetime[0:to_arri_datetime.find('T')]
        to_time = to_arri_datetime[to_arri_datetime.find('T')+1:to_arri_datetime.find('+')]
        to_time = to_time[0:to_time.rfind(":")]

        # Point
        st_list = list()
        for point_item in getSafeList(route_item.get("Point")):
            st_name = point_item.get("Station").get("Name")
            st_type = point_item.get("Station").get("Type")

            st_suffix = "停"
            if st_type == "train":
                st_suffix = "駅"
            elif st_type in ["plane", "ship", "walk", "strange"]:
                st_suffix = ""

            st_list.append(st_name + st_suffix)

        print('from_st_msg={}'.format(st_list[0]))
        print('to_st_msg={}'.format(st_list[len(st_list)-1]))

        # result msg
        msg_list = list()
        msg_list.append(st_list[0])
        msg_list.append("を")
        msg_list.append(from_time)
        msg_list.append("に")
        msg_list.append(from_train_name)
        msg_list.append("にて出発すると、")
        msg_list.append(st_list[len(st_list)-1])
        msg_list.append("には")
        msg_list.append(to_time)
        msg_list.append("に")
        if from_train_name != to_train_name:
            msg_list.append(to_train_name)
            msg_list.append("にて")
        msg_list.append("到着します。")
        msg_list.append("片道")
        msg_list.append(fare_msg)
        msg_list.append("円で")
        msg_list.append(str(time_msg))
        msg_list.append("分かかります。")
        if transfer_cnt_msg > 0:
            msg_list.append("乗換が途中")
            msg_list.append(str(transfer_cnt_msg))
            msg_list.append("回必要で")
            msg_list.append("、".join(st_list[1:-1]))
            msg_list.append("にて乗り換えてください。")

        result_msg = "".join(msg_list)
        break

    return result_msg
