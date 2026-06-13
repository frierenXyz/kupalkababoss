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
import re
from datetime import datetime

import requests
import js2py  # Changed from execjs to js2py
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

# ============ JS Context (using js2py) ============
js_context = None

def load_js_context():
    """Load JavaScript using js2py (pure Python, works on Vercel)"""
    global js_context
    
    if js_context is not None:
        return js_context
    
    # Try different paths
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
            logger.info(f"Loaded JS from: {path}")
            break
    
    if not js_code:
        logger.error("Could not find dun163.js")
        return None
    
    try:
        # Create JS context and execute
        context = js2py.EvalJs()
        context.execute(js_code)
        js_context = context
        logger.success("JavaScript loaded successfully with js2py")
        return js_context
    except Exception as e:
        logger.error(f"Failed to load JS: {e}")
        return None

def call_js_function(func_name, *args):
    """Safely call a JavaScript function from the context"""
    context = load_js_context()
    if not context:
        return None
    
    try:
        # Get the function from context
        func = getattr(context, func_name, None)
        if func and callable(func):
            return func(*args)
        else:
            logger.error(f"Function {func_name} not found in JS context")
            return None
    except Exception as e:
        logger.error(f"Error calling {func_name}: {e}")
        return None

# ============ Helper Functions ============
def random_jsonp():
    chars = string.ascii_lowercase + string.digits
    return f"__JSONP_{''.join(random.choices(chars, k=7))}_0"

def extract_jsonp(text):
    """Extract JSON from JSONP response"""
    match = re.search(r"\((.*)\)", text, re.S)
    if match:
        try:
            return json.loads(match.group(1))
        except:
            return {}
    return {}

def generate_mock_clicks():
    """Generate realistic mock click positions"""
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
        offset_x = random.randint(-5, 5)
        offset_y = random.randint(-5, 5)
        clicks.append({
            "x": max(10, min(x + offset_x, 310)),
            "y": max(10, min(y + offset_y, 190))
        })
    
    return clicks

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

# Initialize JS context on startup
@app.on_event("startup")
async def startup_event():
    logger.info("Starting suicideGF API...")
    ctx = load_js_context()
    if ctx:
        logger.success("Ready to solve captchas")
    else:
        logger.error("Failed to initialize JS context")

# ============ API Endpoints ============

@app.get("/")
async def root():
    return {
        "name": "suicideGF",
        "version": "1.0.0",
        "description": "CN31 Token Fetcher API",
        "status": "running",
        "endpoints": {
            "GET /health": "Health check",
            "POST /solve": "Get a token",
            "POST /batch": "Get multiple tokens",
            "GET /docs": "API documentation"
        }
    }

@app.get("/health")
async def health():
    ctx = load_js_context()
    return {
        "status": "healthy",
        "version": "1.0.0",
        "js_loaded": ctx is not None,
        "js_engine": "js2py"
    }

@app.post("/solve", response_model=SolveResponse)
async def solve(request: SolveRequest):
    start_time = time.time()
    
    ctx = load_js_context()
    if not ctx:
        return SolveResponse(
            success=False,
            error="JavaScript context not loaded",
            zone_id=request.zone_id,
            timestamp=datetime.now().isoformat(),
            processing_time=time.time() - start_time
        )
    
    try:
        # Generate fingerprint and callback using js2py
        fp = call_js_function('get_fp', request.fp_h, UserAgent().random)
        cb = call_js_function('get_cb')
        
        if not fp or not cb:
            return SolveResponse(
                success=False,
                error="Failed to generate fingerprint",
                zone_id=request.zone_id,
                timestamp=datetime.now().isoformat(),
                processing_time=time.time() - start_time
            )
        
        # Create session
        domain = random.choice(DUN163_DOMAINS)
        session = requests.Session()
        session.headers.update({
            "User-Agent": UserAgent().random,
            "Referer": request.referer,
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        })
        
        # Step 1: Get configuration
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
        
        logger.info(f"T-{request.zone_id} | Getting config from {domain}")
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
        
        if not all([dt, ac_token, bid]):
            return SolveResponse(
                success=False,
                error="Missing required configuration data",
                zone_id=request.zone_id,
                timestamp=datetime.now().isoformat(),
                processing_time=time.time() - start_time
            )
        
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
        
        # Add irToken if available
        ir_data = conf.get('ir', {})
        if ir_data.get('enable'):
            params["irToken"] = ir_data.get('token')
        
        resp = session.get(url, params=params, timeout=30)
        captcha_data = extract_jsonp(resp.text).get('data', {})
        
        token = captcha_data.get('token')
        captcha_type = captcha_data.get('type', 7)
        
        if not token:
            return SolveResponse(
                success=False,
                error="No token in captcha response",
                zone_id=request.zone_id,
                timestamp=datetime.now().isoformat(),
                processing_time=time.time() - start_time
            )
        
        logger.info(f"T-{request.zone_id} | Got token, type={captcha_type}")
        
        # Step 3: Generate click data and submit solution
        click_points = generate_mock_clicks()
        
        # Call get_click_check_data from JS
        check_data = call_js_function('get_click_check_data', click_points, token)
        
        if not check_data:
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
            "cb": call_js_function('get_cb') or cb,
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
            
            # Try to process through do_onVerify
            if validate_raw:
                try:
                    processed = call_js_function('do_onVerify', validate_raw, fp)
                    if processed and len(str(processed)) > 10:
                        final_token = processed
                except Exception as e:
                    logger.warning(f"do_onVerify failed: {e}")
            
            processing_time = time.time() - start_time
            
            logger.success(f"T-{request.zone_id} | Success! Token: {final_token[:50]}...")
            
            return SolveResponse(
                success=True,
                token=final_token,
                validate=validate_raw,
                zone_id=request.zone_id,
                timestamp=datetime.now().isoformat(),
                processing_time=processing_time
            )
        else:
            error_msg = result.get('error', 'Verification failed')
            logger.warning(f"T-{request.zone_id} | Failed: {error_msg}")
            
            return SolveResponse(
                success=False,
                error=error_msg,
                zone_id=request.zone_id,
                timestamp=datetime.now().isoformat(),
                processing_time=time.time() - start_time
            )
            
    except Exception as e:
        logger.error(f"T-{request.zone_id} | Error: {str(e)}")
        return SolveResponse(
            success=False,
            error=str(e),
            zone_id=request.zone_id,
            timestamp=datetime.now().isoformat(),
            processing_time=time.time() - start_time
        )

@app.post("/batch")
async def batch_solve(request: SolveRequest, count: int = 3):
    """Batch token generation (max 5 tokens)"""
    from concurrent.futures import ThreadPoolExecutor
    
    batch_count = min(count, 5)  # Limit to 5 for serverless
    
    def get_one():
        # Use asyncio to run the solve function
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(solve(request))
    
    with ThreadPoolExecutor(max_workers=batch_count) as executor:
        futures = [executor.submit(get_one) for _ in range(batch_count)]
        results = [f.result() for f in futures]
    
    tokens = [r.token for r in results if r.success]
    
    return {
        "success": len(tokens) > 0,
        "tokens": tokens,
        "count": len(tokens),
        "total_attempts": batch_count,
        "errors": [r.error for r in results if not r.success]
    }

@app.get("/stats")
async def get_stats():
    """Get solver statistics"""
    ctx = load_js_context()
    return {
        "status": "active",
        "js_engine": "js2py",
        "js_loaded": ctx is not None,
        "supported_zones": ["CN31", "CN30"],
        "default_referer": REFERER
    }