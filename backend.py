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

@app.route('/customer/batch', methods=['POST'])
@requires_apigateway_signature()
def get_customers_batch():
    """
    批量查询客户信息
    请求体: {"ids": ["5000000000000", "5000000000001", ...]}
    返回: [{"id": "5000000000000", "region_id": "5210000000", "location": "106.398183,29.416481"}, ...]
    """
    try:
        data = request.get_json()
        if not data or 'ids' not in data:
            return jsonify({'error': '请求体必须包含 ids 字段'}), 400
        
        ids = data['ids']
        if not isinstance(ids, list) or len(ids) == 0:
            return jsonify({'error': 'ids 必须是非空列表'}), 400
        
        conn = get_db_connection()
        
        # 构建 SQL 查询，使用参数化查询防止 SQL 注入
        placeholders = ','.join(['?' for _ in ids])
        query = f"""
            SELECT id, region_id, location 
            FROM customer 
            WHERE id IN ({placeholders})
        """
        
        result = conn.execute(query, ids).fetchall()
        conn.close()
        
        # 转换结果为字典列表
        customers = []
        for row in result:
            customers.append({
                'id': str(row[0]),        # 确保 id 是字符串类型
                'region_id': str(row[1]), # 确保 region_id 是字符串类型
                'location': row[2]        # location 保持原样（字符串）
            })
        
        response_data = {'customers': customers, 'count': len(customers)}
        response = app.response_class(
            response=json.dumps(response_data, ensure_ascii=False, indent=2),
            status=200,
            mimetype='application/json; charset=utf-8'
        )
        return response
        
    except Exception as e:
        return jsonify({'error': f'查询失败: {str(e)}'}), 500

@app.route('/region/search', methods=['POST'])
@requires_apigateway_signature()
def search_customers_by_regions():
    """
    批量按台区查询客户信息
    请求体: {"region_ids": ["5210000000", "5210000001", ...]}
    返回: [{"id": "5000000000000", "region_id": "5210000000", "location": "106.398183,29.416481"}, ...]
    """
    try:
        data = request.get_json()
        if not data or 'region_ids' not in data:
            return jsonify({'error': '请求体必须包含 region_ids 字段'}), 400
        
        region_ids = data['region_ids']
        if not isinstance(region_ids, list) or len(region_ids) == 0:
            return jsonify({'error': 'region_ids 必须是非空列表'}), 400
        
        conn = get_db_connection()
        
        # 构建 SQL 查询，使用参数化查询防止 SQL 注入
        placeholders = ','.join(['?' for _ in region_ids])
        query = f"""
            SELECT id, region_id, location 
            FROM customer 
            WHERE region_id IN ({placeholders})
            ORDER BY region_id, id
        """
        
        result = conn.execute(query, region_ids).fetchall()
        conn.close()
        
        # 转换结果为字典列表
        customers = []
        for row in result:
            customers.append({
                'id': str(row[0]),        # 确保 id 是字符串类型
                'region_id': str(row[1]), # 确保 region_id 是字符串类型
                'location': row[2]        # location 保持原样（字符串）
            })
        
        response_data = {
            'customers': customers, 
            'count': len(customers),
            'region_ids_queried': region_ids
        }
        response = app.response_class(
            response=json.dumps(response_data, ensure_ascii=False, indent=2),
            status=200,
            mimetype='application/json; charset=utf-8'
        )
        return response
        
    except Exception as e:
        return jsonify({'error': f'查询失败: {str(e)}'}), 500

@app.route('/poi/search', methods=['POST'])
@requires_apigateway_signature()
def search_poi():
    """
    POI 搜索接口
    请求体: {
        "province": "重庆市",
        "city": "重庆市", 
        "district": "大渡口区",
        "town": "",
        "village": "",
        "road": "",
        "poi": "",
        "limit": 100
    }
    支持的查询字段: province, city, district, town, village, road, poi
    多个参数使用 AND 逻辑连接
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': '请求体不能为空'}), 400
        
        conn = get_db_connection()
        
        # 构建动态查询条件
        conditions = []
        params = []
        
        # 支持的查询字段
        search_fields = ['province', 'city', 'district', 'town', 'village', 'road', 'poi']
        
        # 收集实际使用的查询参数
        query_params = {}
        
        for field in search_fields:
            value = data.get(field)
            if value and value.strip():  # 检查非空且非空白字符串
                conditions.append(f"{field} = ?")
                params.append(value.strip())
                query_params[field] = value.strip()
        
        if not conditions:
            return jsonify({'error': '至少需要提供一个非空的查询参数'}), 400
        
        # 构建完整的 SQL 查询
        base_query = "SELECT province, city, district, town, village, road, poi FROM poi"
        where_clause = " WHERE " + " AND ".join(conditions)
        query = base_query + where_clause
        
        # 限制返回结果数量，避免查询过多数据
        limit = data.get('limit', 100)
        try:
            limit = int(limit)
            if limit > 1000:
                limit = 1000
            elif limit <= 0:
                limit = 100
        except (ValueError, TypeError):
            limit = 100
        
        query += f" LIMIT {limit}"
        
        result = conn.execute(query, params).fetchall()
        conn.close()
        
        # 转换结果为字典列表
        pois = []
        for row in result:
            pois.append({
                'province': row[0],
                'city': row[1],
                'district': row[2],
                'town': row[3],
                'village': row[4],
                'road': row[5],
                'poi': row[6]
            })
        
        response_data = {
            'pois': pois, 
            'count': len(pois),
            'query_params': query_params,
            'limit': limit
        }
        response = app.response_class(
            response=json.dumps(response_data, ensure_ascii=False, indent=2),
            status=200,
            mimetype='application/json; charset=utf-8'
        )
        return response
        
    except Exception as e:
        return jsonify({'error': f'搜索失败: {str(e)}'}), 500

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
