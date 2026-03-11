from flask import Flask, request, jsonify
import duckdb
import os
import json
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
            "columnSize": 19,
            "data": [
                {
                    "id": "WO2026011601",
                    "customerno": "CUST0001",
                    "appno": "APP20260116001",
                    "orgno": "ORG001",
                    "orgname": "城区供电局",
                    "customername": "张伟",
                    "customerphone": "13800000001",
                    "address": "上海市浦东新区世纪大道100号",
                    "businesstype": "电力服务",
                    "category1": "供电质量",
                    "category2": "停电",
                    "category3": "计划停电",
                    "accepttime": "2026-01-15 09:30:00",
                    "handletime": "2026-01-16 14:20:00",
                    "acceptcontent": "线路停电影响正常用电",
                    "handlecontent": "已处理",
                    "handler": "李强",
                    "handle_department": "抢修一班"
                }
            ],
            "columnNames": [
                "id",
                "customerno",
                "appno",
                "orgno",
                "orgname",
                "customername",
                "customerphone",
                "address",
                "businesstype",
                "category1",
                "category2",
                "category3",
                "accepttime",
                "handletime",
                "acceptcontent",
                "handlecontent",
                "handler",
                "handle_department"
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
        time_format = "%Y-%m-%d %H:%M:%S"
        try:
            start_time = datetime.strptime(start_time_raw, time_format)
            end_time = datetime.strptime(end_time_raw, time_format)
        except ValueError:
            return jsonify({'error': 'startTime 和 endTime 必须是有效的时间格式 YYYY-MM-DD HH:MM:SS'}), 400

        conn = get_db_connection()

        count_query = """
            SELECT COUNT(*)
            FROM work_order
            WHERE CAST(handletime AS TIMESTAMP) BETWEEN ? AND ?
        """
        total_count = conn.execute(count_query, [start_time, end_time]).fetchone()[0]

        offset = (pageNum - 1) * pageSize
        query = """
            SELECT
                id,
                customerno,
                appno,
                orgno,
                orgname,
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
                handle_department
            FROM work_order
            WHERE CAST(handletime AS TIMESTAMP) BETWEEN ? AND ?
            ORDER BY CAST(handletime AS TIMESTAMP)
            LIMIT ? OFFSET ?
        """
        rel = conn.execute(query, [start_time, end_time, pageSize, offset])
        columns = [desc[0] for desc in rel.description]
        rows = rel.fetchall()
        conn.close()

        paged_orders = [dict(zip(columns, row)) for row in rows]
        
        # 构建响应数据
        response_data = {
            "requestId": "1234567890",
            "errCode": "DLM.0",
            "errMsg": None, ## null或者"错误信息"
            "data":{
                "totalSize": total_count, ## null或者总条数
                "rowSize": len(paged_orders),
                "columnSize": 18,
                "data": paged_orders,
                "columnNames": [
                    "id",
                    "customerno",
                    "appno",
                    "orgno",
                    "orgname",
                    "customername",
                    "customerphone",
                    "address",
                    "businesstype",
                    "category1",
                    "category2",
                    "category3",
                    "accepttime",
                    "handletime",
                    "acceptcontent",
                    "handlecontent",
                    "handler",
                    "handle_department"
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
