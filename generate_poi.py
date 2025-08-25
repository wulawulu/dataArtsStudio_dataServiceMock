import json
import csv
import random
import numpy as np
from typing import List, Tuple, Dict
from math import cos, sin, radians, sqrt, atan2


def parse_polyline(polyline_str: str) -> List[Tuple[float, float]]:
    """解析polyline字符串，返回坐标点列表"""
    polygons = []
    
    # 分割多个多边形
    polygon_parts = polyline_str.split('|')
    
    for part in polygon_parts:
        if not part.strip():
            continue
            
        coords = []
        points = part.split(';')
        
        for point in points:
            if ',' in point:
                lng, lat = map(float, point.split(','))
                coords.append((lng, lat))
        
        if coords:
            polygons.append(coords)
    
    return polygons


def point_in_polygon(point: Tuple[float, float], polygon: List[Tuple[float, float]]) -> bool:
    """判断点是否在多边形内部（射线法）"""
    x, y = point
    n = len(polygon)
    inside = False
    
    p1x, p1y = polygon[0]
    for i in range(1, n + 1):
        p2x, p2y = polygon[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y
    
    return inside


def point_in_region(point: Tuple[float, float], polygons: List[List[Tuple[float, float]]]) -> bool:
    """判断点是否在区域内（任意一个多边形内）"""
    return any(point_in_polygon(point, polygon) for polygon in polygons)


def get_region_bounds(polygons: List[List[Tuple[float, float]]]) -> Tuple[float, float, float, float]:
    """获取区域的边界框"""
    all_lngs = []
    all_lats = []
    
    for polygon in polygons:
        for lng, lat in polygon:
            all_lngs.append(lng)
            all_lats.append(lat)
    
    return min(all_lngs), min(all_lats), max(all_lngs), max(all_lats)


def distance_km(point1: Tuple[float, float], point2: Tuple[float, float]) -> float:
    """计算两点间距离（公里）"""
    lng1, lat1 = point1
    lng2, lat2 = point2
    
    R = 6371  # 地球半径
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    
    return R * c


def generate_district_centers(polygons: List[List[Tuple[float, float]]], num_districts: int = 1000) -> List[Tuple[float, float]]:
    """在区域内生成台区中心点"""
    min_lng, min_lat, max_lng, max_lat = get_region_bounds(polygons)
    centers = []
    
    # 先尝试生成网格式分布，再补充随机点
    grid_points = []
    
    # 计算合适的网格密度
    region_width_km = distance_km((min_lng, min_lat), (max_lng, min_lat))
    region_height_km = distance_km((min_lng, min_lat), (min_lng, max_lat))
    
    # 根据要求的台区数量计算网格大小
    # 假设台区直径约3公里，适当密一些
    grid_spacing_km = 0.4  # 网格间距400米，更密集
    
    grid_x_count = int(region_width_km / grid_spacing_km) + 1
    grid_y_count = int(region_height_km / grid_spacing_km) + 1
    
    # 生成网格点
    for i in range(grid_x_count):
        for j in range(grid_y_count):
            lng = min_lng + (max_lng - min_lng) * i / max(1, grid_x_count - 1)
            lat = min_lat + (max_lat - min_lat) * j / max(1, grid_y_count - 1)
            
            # 添加小的随机偏移避免过于规整
            lng += random.uniform(-0.002, 0.002)
            lat += random.uniform(-0.002, 0.002)
            
            point = (lng, lat)
            if point_in_region(point, polygons):
                grid_points.append(point)
    
    print(f"网格生成候选点: {len(grid_points)} 个")
    
    # 从网格点中选择，允许更密集的分布
    for point in grid_points:
        if len(centers) >= num_districts:
            break
        centers.append(point)
    
    # 如果网格点不够，补充随机点
    max_attempts = (num_districts - len(centers)) * 20
    attempts = 0
    
    while len(centers) < num_districts and attempts < max_attempts:
        # 随机生成候选点
        lng = random.uniform(min_lng, max_lng)
        lat = random.uniform(min_lat, max_lat)
        point = (lng, lat)
        
        # 检查是否在区域内
        if point_in_region(point, polygons):
            centers.append(point)
        
        attempts += 1
    
    print(f"成功生成 {len(centers)} 个台区中心点")
    return centers


def generate_customers_for_district(center: Tuple[float, float], district_id: str, num_customers: int = 1000, start_id: int = 0) -> List[Dict]:
    """为单个台区生成用户数据"""
    customers = []
    center_lng, center_lat = center
    
    # 台区半径1.5-2.5公里（对应直径3-5公里）
    max_radius_km = random.uniform(1.5, 2.5)
    max_radius_deg = max_radius_km / 111.0  # 粗略转换为度数
    
    for i in range(num_customers):
        # 在台区中心周围随机分布用户
        # 使用极坐标生成更自然的分布
        angle = random.uniform(0, 2 * np.pi)
        # 使用sqrt让分布更均匀（而不是集中在中心）
        radius = sqrt(random.uniform(0, 1)) * max_radius_deg
        
        # 转换为经纬度偏移
        lng_offset = radius * cos(angle)
        lat_offset = radius * sin(angle)
        
        customer_lng = center_lng + lng_offset
        customer_lat = center_lat + lat_offset
        
        # 生成唯一的用户ID（户号），基于全局计数器确保唯一性
        customer_id = f"{5000000000000 + start_id + i}"
        
        customers.append({
            'id': customer_id,
            'region_id': district_id,
            'location': f"{customer_lng:.6f},{customer_lat:.6f}"
        })
    
    return customers


def generate_all_data():
    """主函数：生成所有台区和用户数据"""
    # 读取区域数据
    print("读取大渡口区域数据...")
    with open('region.json', 'r', encoding='utf-8') as f:
        region_data = json.load(f)
    
    # 解析多边形边界
    polyline = region_data['polyline']
    polygons = parse_polyline(polyline)
    print(f"解析到 {len(polygons)} 个多边形区域")
    
    # 生成台区中心点
    print("生成台区中心点...")
    district_centers = generate_district_centers(polygons, 1000)
    
    # 生成所有用户数据
    print("生成用户数据...")
    all_customers = []
    customer_id_counter = 0
    
    for i, center in enumerate(district_centers):
        district_id = f"{5210000000 + i:010d}"  # 生成台区ID
        customers = generate_customers_for_district(center, district_id, 1000, customer_id_counter)
        all_customers.extend(customers)
        customer_id_counter += 1000  # 每个台区1000个用户
        
        if (i + 1) % 100 == 0:
            print(f"已完成 {i + 1}/{len(district_centers)} 个台区")
    
    print(f"总共生成 {len(all_customers)} 个用户数据")
    
    # 写入CSV文件
    print("写入customer.csv文件...")
    with open('csv/customer.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['id', 'region_id', 'location'], quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(all_customers)
    
    print("数据生成完成！")


if __name__ == "__main__":
    generate_all_data()
