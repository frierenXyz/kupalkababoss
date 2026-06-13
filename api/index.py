# api/index.py
import sys
import os
from pathlib import Path

# Add parent directory to path so we can import from app.py
sys.path.append(str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import json
import time
import random
import string
from datetime import datetime

# Import from your app.py
import requests
import execjs
from fake_useragent import UserAgent
from loguru import logger

# ============ Configuration ============
REFERER = "https://mtacc.mobilelegends.com/"
ID = "fef5c67c39074e9d845f4bf579cc07af"
FP_H = "mtacc.mobilelegends.com"

DUN163_DOMAINS = [
    "https://c.dun.163.com",
    "https://c.dun.163yun.com"
]

# ============ Models ============
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

# ============ Helper Functions ============
def load_js_context():
    """Load JavaScript from file - works on Vercel"""
    js_path = os.path.join(os.path.dirname(__file__), '..', 'dun163.js')
    
    if not os.path.exists(js_path):
        # Fallback: look in current directory
        js_path = os.path.join(os.path.dirname(__file__), 'dun163.js')
    
    with open(js_path, 'r', encoding='utf-8') as f:
        js_code = f.read()
    
    return execjs.compile(js_code)

def random_jsonp():
    chars = string.ascii_lowercase + string.digits
    return f"__JSONP_{''.join(random.choices(chars, k=7))}_0"

def extract_jsonp(text):
    import re
    match = re.search(r"\((.*)\)", text, re.S)
    if match:
        try:
            return json.loads(match.group(1))
        except:
            return {}
    return {}

# ============ FastAPI App ============
app = FastAPI(
    title="suicideGF - CN31 Token Fetcher",
    description="NetEase Captcha (Dun163) Token Generator",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load JS context at startup
js_ctx = None

@app.on_event("startup")
async def startup_event():
    global js_ctx
    try:
        js_ctx = load_js_context()
        logger.success("JavaScript loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load JS: {e}")

# ============ API Endpoints ============

@app.get("/")
async def root():
    return {
        "name": "suicideGF",
        "version": "1.0.0",
        "description": "CN31 Token Fetcher API",
        "endpoints": {
            "GET /health": "Health check",
            "POST /solve": "Get a token",
            "POST /batch": "Get multiple tokens",
            "GET /docs": "API documentation"
        }
    }

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "version": "1.0.0",
        "js_loaded": js_ctx is not None
    }

@app.post("/solve", response_model=SolveResponse)
async def solve(request: SolveRequest):
    start_time = time.time()
    
    if not js_ctx:
        return SolveResponse(
            success=False,
            error="JavaScript context not loaded",
            zone_id=request.zone_id,
            timestamp=datetime.now().isoformat(),
            processing_time=time.time() - start_time
        )
    
    try:
        # Generate fingerprint
        fp = js_ctx.call('get_fp', request.fp_h, UserAgent().random)
        cb = js_ctx.call('get_cb')
        
        # Get configuration
        domain = random.choice(DUN163_DOMAINS)
        session = requests.Session()
        session.headers.update({
            "User-Agent": UserAgent().random,
            "Referer": request.referer,
        })
        
        # Step 1: Get config
        url = f"{domain}/api/v2/getconf"
        params = {
            "referer": request.referer,
            "zoneId": request.zone_id,
            "dt": "",
            "id": request.id,
            "ipv6": "false",
            "runEnv": "10",
            "iv": "5",
            "loadVersion": "2.5.3",
            "lang": "en-US",
            "callback": random_jsonp()
        }
        
        resp = session.get(url, params=params, timeout=30)
        conf = extract_jsonp(resp.text).get('data', {})
        
        if not conf:
            return SolveResponse(
                success=False,
                error="Failed to get configuration",
                zone_id=request.zone_id,
                timestamp=datetime.now().isoformat(),
                processing_time=time.time() - start_time
            )
        
        dt = conf.get('dt')
        ac_data = conf.get('ac', {})
        ac_token = ac_data.get('token')
        bid = ac_data.get('bid')
        
        # Step 2: Get captcha
        url = f"{domain}/api/v3/get"
        params = {
            "referer": request.referer,
            "zoneId": request.zone_id,
            "dt": dt,
            "id": bid,
            "fp": fp,
            "https": "true",
            "type": "",
            "version": "2.28.5",
            "dpr": "1",
            "dev": "1",
            "cb": cb,
            "ipv6": "false",
            "runEnv": "10",
            "group": "",
            "scene": "",
            "lang": "en-US",
            "sdkVersion": "",
            "loadVersion": "2.5.3",
            "iv": "4",
            "user": "",
            "width": "320",
            "audio": "false",
            "sizeType": "10",
            "smsVersion": "v3",
            "token": "",
            "callback": random_jsonp()
        }
        
        resp = session.get(url, params=params, timeout=30)
        captcha_data = extract_jsonp(resp.text).get('data', {})
        
        token = captcha_data.get('token')
        captcha_type = captcha_data.get('type', 7)
        
        if not token:
            return SolveResponse(
                success=False,
                error="No token in response",
                zone_id=request.zone_id,
                timestamp=datetime.now().isoformat(),
                processing_time=time.time() - start_time
            )
        
        # Step 3: Submit solution (using mock clicks for demo)
        # For production, you'd want to integrate the ML model
        # But Vercel has a 500MB limit, so use simplified approach
        click_points = [
            {"x": 80, "y": 70},
            {"x": 160, "y": 120},
            {"x": 240, "y": 90}
        ]
        
        if captcha_type == 7:
            check_data = js_ctx.call('get_click_check_data', click_points, token)
        else:
            check_data = '{"d":"","m":"","p":"","ext":""}'
        
        url = f"{domain}/api/v3/check"
        params = {
            "referer": request.referer,
            "zoneId": request.zone_id,
            "dt": dt,
            "id": bid,
            "token": token,
            "data": check_data,
            "width": "320",
            "type": str(captcha_type),
            "version": "2.28.5",
            "cb": js_ctx.call('get_cb'),
            "user": "",
            "extraData": "",
            "bf": "0",
            "runEnv": "10",
            "sdkVersion": "",
            "loadVersion": "2.5.3",
            "iv": "4",
            "callback": random_jsonp()
        }
        
        resp = session.get(url, params=params, timeout=30)
        result = extract_jsonp(resp.text).get('data', {})
        
        if result.get('result') == True:
            validate_raw = result.get('validate', '')
            final_token = validate_raw
            
            if validate_raw and js_ctx:
                try:
                    final_token = js_ctx.call('do_onVerify', validate_raw, fp)
                except:
                    pass
            
            return SolveResponse(
                success=True,
                token=final_token,
                validate=validate_raw,
                zone_id=request.zone_id,
                timestamp=datetime.now().isoformat(),
                processing_time=time.time() - start_time
            )
        else:
            return SolveResponse(
                success=False,
                error="Verification failed",
                zone_id=request.zone_id,
                timestamp=datetime.now().isoformat(),
                processing_time=time.time() - start_time
            )
            
    except Exception as e:
        return SolveResponse(
            success=False,
            error=str(e),
            zone_id=request.zone_id,
            timestamp=datetime.now().isoformat(),
            processing_time=time.time() - start_time
        )

@app.post("/batch")
async def batch_solve(request: SolveRequest, count: int = 3):
    """Batch token generation (simplified for Vercel)"""
    from concurrent.futures import ThreadPoolExecutor
    
    def get_one():
        # Simplified single solver
        return solve(request)
    
    with ThreadPoolExecutor(max_workers=min(count, 3)) as executor:
        futures = [executor.submit(get_one) for _ in range(min(count, 5))]
        results = [f.result() for f in futures]
    
    tokens = [r.token for r in results if r.success]
    
    return {
        "success": len(tokens) > 0,
        "tokens": tokens,
        "count": len(tokens),
        "errors": [r.error for r in results if not r.success]
    }