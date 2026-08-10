from flask import Flask, request, jsonify
import duckdb
import os
import json
import random
from functools import wraps
import re
from datetime import datetime, timedelta, timezone
from apig_sdk import signer

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False  # 确保 JSON 响应正确显示中文

# DuckDB 数据库连接
def get_db_connection():
    """获取 DuckDB 数据库连接"""
    conn = duckdb.connect(':memory:')
    
    # 创建 work_order 表并导入 CSV 数据
    work_order_csv_path = os.path.join(os.path.dirname(__file__), 'workOrder.csv')
    conn.execute(f"""
        CREATE TABLE work_order AS 
        SELECT * FROM read_csv_auto('{work_order_csv_path}')
    """)
    
    return conn

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
BUSINESS_TYPES = ("005", "009", "018")
RESP_FLAG_OPTIONS = ("01", "02")
MESH_ORDER_CONTENTS = [
    "现场核查用户用电异常并反馈处理结果",
    "协调网格人员跟进停电诉求",
    "安排工作人员上门排查线路隐患",
    "复核客户报修地址并派发处理任务",
    "跟踪客户服务诉求闭环进度",
]

def build_mesh_order_id(order_time):
    """生成网格工单 ID，格式为 G + 年月日 + 六位随机编号。"""
    return f"G{order_time.strftime('%Y%m%d')}{random.randint(0, 999999):06d}"

def build_work_order_id(order_time, sequence):
    """生成工单 ID，格式为 WO + 处理日期 + 两位序号。"""
    return f"WO{order_time.strftime('%Y%m%d')}{sequence:02d}"

def normalize_business_type(business_type):
    """兼容模板中的中文业务类型，统一输出为 005/009/018。"""
    if business_type in BUSINESS_TYPES:
        return business_type
    return random.choice(("005", "009"))

def build_resp_flag(business_type):
    """018 必须返回 null，其余业务类型返回 01 或 02。"""
    if business_type == "018":
        return None
    return random.choice(RESP_FLAG_OPTIONS)

def rewrite_order_time_range(order, start_time, end_time):
    """将模板工单时间改写到传入的时间范围内，并保证 accepttime <= handletime。"""
    rewritten_order = dict(order)
    total_seconds = max(int((end_time - start_time).total_seconds()), 0)

    if total_seconds == 0:
        accept_time = start_time
        handle_time = start_time
    else:
        accept_offset = random.randint(0, total_seconds)
        handle_offset = random.randint(accept_offset, total_seconds)
        accept_time = start_time + timedelta(seconds=accept_offset)
        handle_time = start_time + timedelta(seconds=handle_offset)

    rewritten_order["accepttime"] = accept_time.strftime(TIME_FORMAT)
    rewritten_order["handletime"] = handle_time.strftime(TIME_FORMAT)
    if random.choice([True, False]):
        rewritten_order["meshorderid"] = build_mesh_order_id(handle_time)
        rewritten_order["meshordercontent"] = random.choice(MESH_ORDER_CONTENTS)
    else:
        rewritten_order["meshorderid"] = None
        rewritten_order["meshordercontent"] = None
    return rewritten_order

def build_random_work_orders(conn, start_time, end_time, page_num, page_size):
    """从模板工单中随机挑选几条，并将时间改写到查询时间范围内。"""
    query = """
        SELECT
            id,
            customerno,
            appno,
            orgno,
            orgname,
            parent_org_code,
            parent_org_name,
            customername,
            CAST(customerphone AS VARCHAR) AS customerphone,
            address,
            businesstype,
            category1,
            category2,
            category3,
            CAST(accepttime AS VARCHAR) AS accepttime,
            CAST(handletime AS VARCHAR) AS handletime,
            acceptcontent,
            handlecontent,
            handler,
            handle_department,
            handle_dept_name,
            CASE
                WHEN cust_impt_lv = '非重要客户' THEN '非重要用户'
                ELSE cust_impt_lv
            END AS cust_impt_lv,
            gov_live_lv,
            discipline
        FROM work_order
        ORDER BY id
    """
    rel = conn.execute(query)
    columns = [desc[0] for desc in rel.description]
    template_orders = [dict(zip(columns, row)) for row in rel.fetchall()]

    if not template_orders:
        return [], 0

    min_count = min(3, len(template_orders))
    selected_count = random.randint(min_count, len(template_orders))
    selected_templates = random.sample(template_orders, selected_count)
    selected_orders = [
        rewrite_order_time_range(order, start_time, end_time)
        for order in selected_templates
    ]
    for order in selected_orders:
        order["businesstype"] = normalize_business_type(order["businesstype"])
        order["resp_flag"] = build_resp_flag(order["businesstype"])
    selected_orders.sort(key=lambda order: order["handletime"])
    daily_id_sequences = {}
    for order in selected_orders:
        handle_time = datetime.strptime(order["handletime"], TIME_FORMAT)
        handle_date = handle_time.date()
        daily_id_sequences[handle_date] = daily_id_sequences.get(handle_date, 0) + 1
        order["id"] = build_work_order_id(handle_time, daily_id_sequences[handle_date])

    offset = (page_num - 1) * page_size
    paged_orders = selected_orders[offset:offset + page_size]
    return paged_orders, selected_count

# API Gateway 签名验证装饰器
def requires_apigateway_signature():
    def wrapper(f):
        secrets = {
            "app_key1": "app_secret1",
        }
        authorizationPattern = re.compile(
            r'SDK-HMAC-SHA256\s+Access=([^,]+),\s?SignedHeaders=([^,]+),\s?Signature=(\w+)')
        BasicDateFormat = "%Y%m%dT%H%M%SZ"

        @wraps(f)
        def wrapped(*args, **kwargs):
            if "authorization" not in request.headers:
                return jsonify({'error': 'Authorization not found.'}), 401
            authorization = request.headers['authorization']
            m = authorizationPattern.match(authorization)
            if m is None:
                return jsonify({'error': 'Authorization format incorrect.'}), 401
            signingKey = m.group(1)
            if signingKey not in secrets:
                return jsonify({'error': 'Signing key not found.'}), 401
            signingSecret = secrets[signingKey]
            signedHeaders = m.group(2).split(";")
            r = signer.HttpRequest()
            r.method = request.method
            r.uri = request.path
            r.query = {}
            for k in request.query_string.decode('utf-8').split('&'):
                spl = k.split("=", 1)
                if spl[0] != "":
                    if len(spl) < 2:
                        r.query[spl[0]] = ""
                    else:
                        r.query[spl[0]] = spl[1]

            r.headers = {}
            needbody = True
            dateHeader = None
            for k in signedHeaders:
                if k not in request.headers:
                    return jsonify({'error': f'Signed header {k} not found'}), 401
                v = request.headers[k]
                if k.lower() == 'x-sdk-content-sha256' and v == 'UNSIGNED-PAYLOAD':
                    needbody = False
                if k.lower() == 'x-sdk-date':
                    dateHeader = v
                r.headers[k] = v
            if needbody:
                r.body = request.get_data()

            if dateHeader is None:
                return jsonify({'error': 'Header x-sdk-date not found.'}), 401
            t = datetime.strptime(dateHeader, BasicDateFormat).replace(tzinfo=timezone.utc)
            if abs(t - datetime.now(timezone.utc)) > timedelta(minutes=15):
                return jsonify({'error': 'Signature expired.'}), 401

            sig = signer.Signer()
            sig.Key = signingKey
            sig.Secret = signingSecret
            if not sig.Verify(r, m.group(3)):
                return jsonify({'error': 'Verify authorization failed.'}), 401
            return f(*args, **kwargs)

        return wrapped
    return wrapper

@app.route('/itg/yx20dzjx/dws/get_dim_itg_location_by_cust_no_cust_no', methods=['POST'])
@requires_apigateway_signature()
def search_customers():
    """
    工单查询接口 - 根据处理时间返回工单信息
    请求体: {
        "startTime": "2026-01-14 16:30:00", ## 必须
        "endTime": "2026-01-15 10:20:00", ## 必须
        "pageNum": 1, ## 必须
        "pageSize": 100 ## 必须
    }
    支持的查询字段: startTime, endTime
    查询逻辑:
    1. 按处理时间（handletime）查询工单
    2. 按处理时间排序并分页
    
    返回数据格式:
    {
        "requestId": "1234567890",
        "errCode": "DLM.0",
        "errMsg": null, ## null或者"错误信息"
        "data": {
            "totalSize": null, ## null或者总条数
            "rowSize": 100,
            "columnSize": 27,
            "data": [
                {
                    "id": "WO2026011601",
                    "meshorderid": "G20260116000010", ## null 或网格工单ID
                    "meshordercontent": "现场核查用户用电异常并反馈处理结果", ## null 或网格工单内容
                    "customerno": "CUST0001",
                    "appno": "APP20260116001",
                    "orgno": "ORG001",
                    "orgname": "城区供电局",
                    "parent_org_code": "PARENT001", ## null 或父单位 ID
                    "parent_org_name": "上海市供电公司", ## null 或父单位名称
                    "customername": "张伟",
                    "customerphone": "13800000001",
                    "address": "上海市浦东新区世纪大道100号",
                    "businesstype": "005", ## 可选值 005/009/018
                    "resp_flag": "01", ## 可选值 null/"01"/"02"；businesstype=018 时必为 null
                    "category1": "供电质量",
                    "category2": "停电",
                    "category3": "计划停电",
                    "accepttime": "2026-01-15 09:30:00",
                    "handletime": "2026-01-16 14:20:00",
                    "acceptcontent": "线路停电影响正常用电",
                    "handlecontent": "已处理",
                    "handler": "李强",
                    "handle_department": "HD001",
                    "handle_dept_name": "抢修一班",
                    "cust_impt_lv": "一级重要用户",
                    "gov_live_lv": "政府民生服务保障用户-一级",
                    "discipline": "配电专业"
                }
            ],
            "columnNames": [
                "id",
                "meshorderid",
                "meshordercontent",
                "customerno",
                "appno",
                "orgno",
                "orgname",
                "parent_org_code",
                "parent_org_name",
                "customername",
                "customerphone",
                "address",
                "businesstype",
                "resp_flag",
                "category1",
                "category2",
                "category3",
                "accepttime",
                "handletime",
                "acceptcontent",
                "handlecontent",
                "handler",
                "handle_department",
                "handle_dept_name",
                "cust_impt_lv",
                "gov_live_lv",
                "discipline"
            ]
        }
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': '请求体不能为空'}), 400
        
        # 验证时间参数
        if 'startTime' not in data or data['startTime'] is None:
            return jsonify({'error': '请求体必须包含 startTime 字段'}), 400
        if 'endTime' not in data or data['endTime'] is None:
            return jsonify({'error': '请求体必须包含 endTime 字段'}), 400
        
        # 验证分页参数是否存在
        if 'pageNum' not in data or data['pageNum'] is None:
            return jsonify({'error': '请求体必须包含 pageNum 字段'}), 400
        
        if 'pageSize' not in data or data['pageSize'] is None:
            return jsonify({'error': '请求体必须包含 pageSize 字段'}), 400
        
        # 获取并验证分页参数
        try:
            pageNum = int(data['pageNum'])
            pageSize = int(data['pageSize'])
            
            if pageNum < 1:
                return jsonify({'error': 'pageNum 必须大于 0'}), 400
            
            if pageSize < 1:
                return jsonify({'error': 'pageSize 必须大于 0'}), 400
            elif pageSize > 2000:  # 限制最大页面大小
                return jsonify({'error': 'pageSize 不能超过 2000'}), 400
                
        except (ValueError, TypeError):
            return jsonify({'error': 'pageNum 和 pageSize 必须是有效的整数'}), 400
        
        start_time_raw = str(data['startTime']).strip()
        end_time_raw = str(data['endTime']).strip().rstrip(',')
        try:
            start_time = datetime.strptime(start_time_raw, TIME_FORMAT)
            end_time = datetime.strptime(end_time_raw, TIME_FORMAT)
        except ValueError:
            return jsonify({'error': 'startTime 和 endTime 必须是有效的时间格式 YYYY-MM-DD HH:MM:SS'}), 400

        if start_time > end_time:
            start_time, end_time = end_time, start_time

        conn = get_db_connection()
        paged_orders, total_count = build_random_work_orders(
            conn,
            start_time,
            end_time,
            pageNum,
            pageSize
        )
        conn.close()
        
        # 构建响应数据
        response_data = {
            "requestId": "1234567890",
            "errCode": "DLM.0",
            "errMsg": None, ## null或者"错误信息"
            "data":{
                "totalSize": total_count, ## null或者总条数
                "rowSize": len(paged_orders),
                "columnSize": 27,
                "data": paged_orders,
                "columnNames": [
                    "id",
                    "meshorderid",
                    "meshordercontent",
                    "customerno",
                    "appno",
                    "orgno",
                    "orgname",
                    "parent_org_code",
                    "parent_org_name",
                    "customername",
                    "customerphone",
                    "address",
                    "businesstype",
                    "resp_flag",
                    "category1",
                    "category2",
                    "category3",
                    "accepttime",
                    "handletime",
                    "acceptcontent",
                    "handlecontent",
                    "handler",
                    "handle_department",
                    "handle_dept_name",
                    "cust_impt_lv",
                    "gov_live_lv",
                    "discipline"
                ]
            }
        }
        
        response = app.response_class(
            response=json.dumps(response_data, ensure_ascii=False, indent=2),
            status=200,
            mimetype='application/json; charset=utf-8'
        )
        return response
        
    except Exception as e:
        return jsonify({'error': f'查询失败: {str(e)}'}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """健康检查接口，无需签名验证"""
    return jsonify({'status': 'healthy', 'message': 'API Gateway Backend is running'})

if __name__ == '__main__':
    app.run(
        host='0.0.0.0',
        port=80,
        debug=True
    )
