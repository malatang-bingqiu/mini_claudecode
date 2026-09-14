# tools.py
import asyncio
import json
import requests

import winsdk.windows.devices.geolocation as wdg
from learn001.config import BAIDU_MAP_AK

# ============ 工具注册表 ============
# 所有工具函数都放这里，Agent 会自动把它们暴露给模型
TOOL_REGISTRY = {}


def register_tool(func):
    """装饰器：把函数注册为可被模型调用的工具"""
    TOOL_REGISTRY[func.__name__] = func
    return func


def get_tool_schemas():
    """返回给 Ollama 的工具描述列表"""
    return list(TOOL_REGISTRY.values())


def call_tool(name: str, arguments: dict) -> str:
    """根据模型给出的函数名和参数，执行对应工具，统一返回字符串"""
    if name not in TOOL_REGISTRY:
        return json.dumps({"error": f"未知工具: {name}"}, ensure_ascii=False)
    func = TOOL_REGISTRY[name]
    try:
        result = func(**arguments)
        # 保证返回字符串
        if not isinstance(result, str):
            result = json.dumps(result, ensure_ascii=False)
        return result
    except Exception as e:
        return json.dumps({"error": f"工具执行失败: {e}"}, ensure_ascii=False)


# ============ 具体工具实现 ============

async def _get_coords_async():
    locator = wdg.Geolocator()
    pos = await locator.get_geoposition_async()
    coord = pos.coordinate
    return {
        "latitude": coord.latitude,
        "longitude": coord.longitude,
        "accuracy": coord.accuracy,  # 精度（米）
    }


def _baidu_reverse_geocode(lat: float, lon: float) -> dict:
    """调用百度地图逆地理编码，坐标转城市"""
    url = "https://api.map.baidu.com/reverse_geocoding/v3/"
    params = {
        "ak": BAIDU_MAP_AK,
        "output": "json",
        "coordtype": "wgs84ll",       # Windows API 返回的是 WGS84
        "location": f"{lat},{lon}",   # 百度要求 纬度,经度
    }
    resp = requests.get(url, params=params, timeout=10).json()

    if resp.get("status") != 0:
        return {"error": resp.get("message", "逆地理编码失败")}

    result = resp["result"]
    comp = result["addressComponent"]
    return {
        "city": comp.get("city") or comp.get("province"),
        "district": comp.get("district"),
        "province": comp.get("province"),
        "address": result.get("formatted_address"),
    }


@register_tool
def get_current_location() -> str:
    """获取当前电脑所在的城市和经纬度。当用户询问'我在哪''当前城市''我的位置'时调用。"""
    try:
        coords = asyncio.run(_get_coords_async())
    except PermissionError:
        return json.dumps(
            {"error": "定位权限被拒绝，请在 Windows 设置 > 隐私 > 位置 中开启"},
            ensure_ascii=False,
        )
    except Exception as e:
        return json.dumps({"error": f"获取定位失败: {e}"}, ensure_ascii=False)

    geo = _baidu_reverse_geocode(coords["latitude"], coords["longitude"])

    result = {
        "latitude": coords["latitude"],
        "longitude": coords["longitude"],
        "accuracy_meters": coords["accuracy"],
    }
    result.update(geo)
    return json.dumps(result, ensure_ascii=False)


# ============ 示例：以后加新工具就照这个模板 ============
# @register_tool
# def get_weather(city: str) -> str:
#     """查询指定城市的实时天气。当用户询问天气时调用。"""
#     ...
#     return json.dumps({...}, ensure_ascii=False)