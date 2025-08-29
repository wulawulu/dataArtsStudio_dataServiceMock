from flask import Flask, request, jsonify
import duckdb
import os
import json
from functools import wraps
import re
from datetime import datetime, timedelta
from apig_sdk import signer

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False  # 确保 JSON 响应正确显示中文

# DuckDB 数据库连接
def get_db_connection():
    """获取 DuckDB 数据库连接"""
    conn = duckdb.connect(':memory:')
    
    # 创建 customer 表并导入 CSV 数据
    customer_csv_path = os.path.join(os.path.dirname(__file__), 'csv', 'customer.csv')
    conn.execute(f"""
        CREATE TABLE customer AS 
        SELECT * FROM read_csv_auto('{customer_csv_path}')
    """)
    
    # 创建 poi 表并导入 CSV 数据
    poi_csv_path = os.path.join(os.path.dirname(__file__), 'csv', 'poi.csv')
    conn.execute(f"""
        CREATE TABLE poi AS 
        SELECT 
            "省份" as province,
            "城市" as city, 
            "区" as district,
            "街道" as town,
            "社区" as village,
            "道路" as road,
            "小区" as poi
        FROM read_csv_auto('{poi_csv_path}')
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
            t = datetime.strptime(dateHeader, BasicDateFormat)
            if abs(t - datetime.utcnow()) > timedelta(minutes=15):
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
    客户搜索接口 - 根据客户ID返回所在台区信息
    请求体: {
        "ids": ["1234567890", "1234567891"], ## 必须
        "pageNum": 1, ## 必须
        "pageSize": 100 ## 必须
    }
    支持的查询字段: ids
    查询逻辑:
    1. 根据提供的客户ID列表，查找这些客户所在的台区ID
    2. 返回这些台区内所有客户的信息（不仅仅是查询的客户）
    
    返回数据格式:
    {
        "requestId": "1234567890",
        "errCode": "DLM.0",
        "errMsg": null, ## null或者"错误信息"
        "data": {
            "totalSize": null, ## null或者总条数
            "rowSize": 100,
            "columnSize": 6,
            "data": [
                {
                    "cust_no": "1234567890",
                    "tg_no": "1234567890",
                    "gps_longitude": 106.5,
                    "gps_latitude": 29.5,
                    "ec_addr": "重庆市巴南区鱼洞街道办事处莲花社区秦家院53",
                    "install_addr": "荆竹村7队"
                }
            ],
            "columnNames": [
                "cust_no",
                "tg_no",
                "gps longitude",
                "gps latitude",
                "ec addr",
                "install addr"
            ]
        }
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': '请求体不能为空'}), 400
        
        # 验证 ids 参数
        if 'ids' not in data or data['ids'] is None:
            return jsonify({'error': '请求体必须包含 ids 字段'}), 400
        
        ids = data['ids']
        if not isinstance(ids, list) or len(ids) == 0:
            return jsonify({'error': 'ids 必须是非空列表'}), 400
        
        search_values = ids
        search_field = 'id'
        
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
        
        conn = get_db_connection()
        
        # 构建 SQL 查询，使用参数化查询防止 SQL 注入
        placeholders = ','.join(['?' for _ in search_values])
        
        # 第一步：根据客户ID查找对应的台区ID
        region_query = f"""
            SELECT DISTINCT region_id 
            FROM customer 
            WHERE {search_field} IN ({placeholders})
        """
        region_result = conn.execute(region_query, search_values).fetchall()
        
        if not region_result:
            # 如果没有找到任何台区，返回空结果
            conn.close()
            response_data = {
                "requestId": "1234567890",
                "errCode": "DLM.0",
                "errMsg": None,
                "data": {
                    "totalSize": 0,
                    "rowSize": 0,
                    "columnSize": 6,
                    "data": [],
                    "columnNames": [
                        "cust_no",
                        "tg_no", 
                        "gps longitude",
                        "gps latitude",
                        "ec addr",
                        "install addr"
                    ]
                }
            }
            response = app.response_class(
                response=json.dumps(response_data, ensure_ascii=False, indent=2),
                status=200,
                mimetype='application/json; charset=utf-8'
            )
            return response
        
        # 提取台区ID列表
        region_ids = [row[0] for row in region_result]
        region_placeholders = ','.join(['?' for _ in region_ids])
        
        # 第二步：查询这些台区下的所有客户总数
        count_query = f"""
            SELECT COUNT(*) 
            FROM customer 
            WHERE region_id IN ({region_placeholders})
        """
        total_count = conn.execute(count_query, region_ids).fetchone()[0]
        
        # 计算分页信息
        total_pages = (total_count + pageSize - 1) // pageSize  # 向上取整
        offset = (pageNum - 1) * pageSize
        
        # 第三步：查询这些台区下的所有客户分页数据
        query = f"""
            SELECT id, region_id, location 
            FROM customer 
            WHERE region_id IN ({region_placeholders})
            ORDER BY region_id, id
            LIMIT {pageSize} OFFSET {offset}
        """
        
        result = conn.execute(query, region_ids).fetchall()
        conn.close()
        
        # 转换结果为指定格式
        data = []
        for row in result:
            # 解析经纬度字符串 "longitude,latitude"
            location_parts = row[2].split(',')
            longitude = float(location_parts[0]) if len(location_parts) >= 1 else 0.0
            latitude = float(location_parts[1]) if len(location_parts) >= 2 else 0.0
            
            data.append({
                'cust_no': str(row[0]),           # 客户编号
                'gps_longitude': longitude,        # 经度
                'gps_latitude': latitude,          # 纬度
                'install_addr': "荆竹村7队",       # 安装地址（示例数据）
                'tg_no': str(row[1]),             # 台区编号
                'ec_addr': "重庆市巴南区鱼洞街道办事处莲花社区秦家院53"  # 电表地址（示例数据）
            })
        
        # 构建响应数据
        response_data = {
            "requestId": "1234567890",
            "errCode": "DLM.0",
            "errMsg": None, ## null或者"错误信息"
            "data":{
                "totalSize": total_count, ## null或者总条数
                "rowSize": len(data),
                "columnSize": 6,
                "data": data,
                "columnNames": [
                    "cust_no",
                    "tg_no", 
                    "gps longitude",
                    "gps latitude",
                    "ec addr",
                    "install addr"
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
