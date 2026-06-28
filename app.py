import sys
import os
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import json, time, random, string, re
from datetime import datetime

import requests
from py_mini_racer import MiniRacer
from fake_useragent import UserAgent
from loguru import logger

REFERER = "https://mtacc.mobilelegends.com/"
ID = "fef5c67c39074e9d845f4bf579cc07af"
FP_H = "mtacc.mobilelegends.com"
DUN163_DOMAINS = ["https://c.dun.163.com", "https://c.dun.163yun.com"]

class SolveRequest(BaseModel):
    zone_id: str = "CN31"
    referer: str = REFERER
    id: str = ID
    fp_h: str = FP_H

class SolveResponse(BaseModel):
    success: bool
    token: Optional[str] = None
    validate: Optional[str] = None
    zone_id: str
    timestamp: str
    processing_time: float
    error: Optional[str] = None

js_context = None

def load_js_context():
    global js_context
    if js_context is not None:
        return js_context

    js_paths = [
        os.path.join(os.path.dirname(__file__), '..', 'dun163.js'),
        os.path.join(os.path.dirname(__file__), 'dun163.js'),
        'dun163.js'
    ]

    js_code = None
    for path in js_paths:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                js_code = f.read()
            logger.info(f"Loaded JS ({len(js_code)} bytes) from: {path}")
            break

    if not js_code:
        logger.error("dun163.js not found")
        return None

    try:
        ctx = MiniRacer()
        ctx.eval("var global = globalThis;\n" + js_code)
        js_context = ctx
        logger.success("JavaScript loaded successfully with V8")
        return js_context
    except Exception as e:
        logger.error(f"V8 eval failed: {type(e).__name__}: {e}")
        return None

def call_js_function(func_name, *args):
    context = load_js_context()
    if not context:
        return None
    try:
        result = context.call(func_name, *args)
        return result
    except Exception as e:
        logger.error(f"Error calling {func_name}: {e}")
        return None

def random_jsonp():
    chars = string.ascii_lowercase + string.digits
    return f"__JSONP_{''.join(random.choices(chars, k=7))}_0"

def extract_jsonp(text):
    match = re.search(r"\((.*)\)", text, re.S)
    if match:
        try:
            return json.loads(match.group(1))
        except:
            return {}
    return {}

def generate_mock_clicks():
    patterns = [
        [(80, 70), (160, 120), (240, 90)],
        [(70, 100), (160, 95), (250, 105)],
        [(160, 60), (110, 130), (210, 140)],
        [(90, 80), (170, 130), (230, 85)],
        [(100, 110), (150, 70), (200, 130)],
    ]
    pattern = random.choice(patterns)
    clicks = []
    for x, y in pattern:
        clicks.append({
            "x": max(10, min(x + random.randint(-5, 5), 310)),
            "y": max(10, min(y + random.randint(-5, 5), 190))
        })
    return clicks

app = FastAPI(title="suicideGF - CN31 Token Fetcher", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
async def startup_event():
    logger.info("Starting API...")
    ctx = load_js_context()
    if ctx:
        logger.success("JS context ready")
    else:
        logger.error("Failed to initialize JS context")

@app.get("/")
async def root():
    return {"status": "running", "endpoints": ["GET /health", "POST /solve", "POST /batch", "GET /docs"]}

@app.get("/health")
async def health():
    ctx = load_js_context()
    return {"status": "healthy", "js_loaded": ctx is not None}

@app.post("/solve", response_model=SolveResponse)
async def solve(request: SolveRequest):
    start_time = time.time()
    ctx = load_js_context()
    if not ctx:
        return SolveResponse(success=False, error="JS context not loaded", zone_id=request.zone_id, timestamp=datetime.now().isoformat(), processing_time=time.time() - start_time)

    try:
        fp = call_js_function('get_fp', request.fp_h, UserAgent().random)
        cb = call_js_function('get_cb')
        if not fp or not cb:
            return SolveResponse(success=False, error="Failed to generate fingerprint/callback", zone_id=request.zone_id, timestamp=datetime.now().isoformat(), processing_time=time.time() - start_time)

        domain = random.choice(DUN163_DOMAINS)
        session = requests.Session()
        session.headers.update({
            "User-Agent": UserAgent().random,
            "Referer": request.referer,
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
        })

        url = f"{domain}/api/v2/getconf"
        params = {
            "referer": request.referer, "zoneId": request.zone_id, "dt": "",
            "id": request.id, "ipv6": "false", "runEnv": "10", "iv": "5",
            "loadVersion": "2.5.3", "lang": "en-US", "callback": random_jsonp()
        }
        resp = session.get(url, params=params, timeout=30)
        conf = extract_jsonp(resp.text).get('data', {})
        if not conf:
            return SolveResponse(success=False, error="Failed to get config", zone_id=request.zone_id, timestamp=datetime.now().isoformat(), processing_time=time.time() - start_time)

        dt = conf.get('dt')
        ac_data = conf.get('ac', {})
        ac_token = ac_data.get('token')
        bid = ac_data.get('bid')
        if not all([dt, ac_token, bid]):
            return SolveResponse(success=False, error="Missing config data", zone_id=request.zone_id, timestamp=datetime.now().isoformat(), processing_time=time.time() - start_time)

        url = f"{domain}/api/v3/get"
        params = {
            "referer": request.referer, "zoneId": request.zone_id, "dt": dt,
            "id": bid, "fp": fp, "https": "true", "type": "", "version": "2.28.5",
            "dpr": "1", "dev": "1", "cb": cb, "ipv6": "false", "runEnv": "10",
            "group": "", "scene": "", "lang": "en-US", "sdkVersion": "",
            "loadVersion": "2.5.3", "iv": "4", "user": "", "width": "320",
            "audio": "false", "sizeType": "10", "smsVersion": "v3", "token": "",
            "callback": random_jsonp()
        }
        ir_data = conf.get('ir', {})
        if ir_data.get('enable'):
            params["irToken"] = ir_data.get('token')

        resp = session.get(url, params=params, timeout=30)
        captcha_data = extract_jsonp(resp.text).get('data', {})
        token = captcha_data.get('token')
        captcha_type = captcha_data.get('type', 7)
        if not token:
            return SolveResponse(success=False, error="No token in response", zone_id=request.zone_id, timestamp=datetime.now().isoformat(), processing_time=time.time() - start_time)

        logger.info(f"T-{request.zone_id} | Got token, type={captcha_type}")

        click_points = generate_mock_clicks()
        check_data = call_js_function('get_click_check_data', click_points, token)
        if not check_data:
            check_data = '{"d":"","m":"","p":"","ext":""}'

        url = f"{domain}/api/v3/check"
        params = {
            "referer": request.referer, "zoneId": request.zone_id, "dt": dt,
            "id": bid, "token": token, "data": check_data, "width": "320",
            "type": str(captcha_type), "version": "2.28.5",
            "cb": call_js_function('get_cb') or cb, "user": "", "extraData": "",
            "bf": "0", "runEnv": "10", "sdkVersion": "", "loadVersion": "2.5.3",
            "iv": "4", "callback": random_jsonp()
        }
        resp = session.get(url, params=params, timeout=30)
        result = extract_jsonp(resp.text).get('data', {})

        if result.get('result') == True:
            validate_raw = result.get('validate', '')
            final_token = validate_raw
            if validate_raw:
                try:
                    processed = call_js_function('do_onVerify', validate_raw, fp)
                    if processed and len(str(processed)) > 10:
                        final_token = processed
                except Exception as e:
                    logger.warning(f"do_onVerify failed: {e}")

            logger.success(f"T-{request.zone_id} | Success!")
            return SolveResponse(success=True, token=final_token, validate=validate_raw, zone_id=request.zone_id, timestamp=datetime.now().isoformat(), processing_time=time.time() - start_time)
        else:
            return SolveResponse(success=False, error=result.get('error', 'Verification failed'), zone_id=request.zone_id, timestamp=datetime.now().isoformat(), processing_time=time.time() - start_time)

    except Exception as e:
        logger.error(f"T-{request.zone_id} | Error: {str(e)}")
        return SolveResponse(success=False, error=str(e), zone_id=request.zone_id, timestamp=datetime.now().isoformat(), processing_time=time.time() - start_time)

@app.post("/batch")
async def batch_solve(request: SolveRequest, count: int = 3):
    from concurrent.futures import ThreadPoolExecutor
    batch_count = min(count, 5)
    def get_one():
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(solve(request))
    with ThreadPoolExecutor(max_workers=batch_count) as executor:
        futures = [executor.submit(get_one) for _ in range(batch_count)]
        results = [f.result() for f in futures]
    tokens = [r.token for r in results if r.success]
    return {"success": len(tokens) > 0, "tokens": tokens, "count": len(tokens)}

@app.get("/stats")
async def get_stats():
    return {"status": "active", "js_engine": "v8 (mini-racer)", "js_loaded": js_context is not None}
