#!/usr/bin/env python3
"""
CN31 Token Fetcher API Server
FastAPI-based service for NetEase Captcha solving
"""

import os
import json
import asyncio
import random
import string
import time
from datetime import datetime
from typing import Optional, List, Dict, Any
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import requests
import execjs
from fake_useragent import UserAgent
from loguru import logger
import uvicorn

# ============ Configuration ============
REFERER = "https://mtacc.mobilelegends.com/"
ID = "fef5c67c39074e9d845f4bf579cc07af"
FP_H = "mtacc.mobilelegends.com"
MAX_WORKERS = 5
TOKEN_CACHE_TTL = 300  # 5 minutes cache

DUN163_DOMAINS = [
    "https://c.dun.163.com",
    "https://c.dun.163yun.com"
]

# ============ Models ============
class SolveRequest(BaseModel):
    """Request model for solving captcha"""
    zone_id: str = Field(default="CN31", description="Zone ID (CN31, CN30, etc.)")
    referer: Optional[str] = Field(default=REFERER, description="Referer URL")
    id: Optional[str] = Field(default=ID, description="Captcha ID")
    fp_h: Optional[str] = Field(default=FP_H, description="Fingerprint host")
    timeout: int = Field(default=30, description="Timeout in seconds")
    count: int = Field(default=1, description="Number of tokens to generate (1-10)")


class TokenResponse(BaseModel):
    """Response model for token"""
    success: bool
    token: Optional[str] = None
    validate: Optional[str] = None
    zone_id: str
    timestamp: str
    processing_time: float
    error: Optional[str] = None


class BatchTokenResponse(BaseModel):
    """Batch response model"""
    success: bool
    tokens: List[str]
    count: int
    total_time: float
    errors: List[str]


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    version: str
    workers_available: int
    cache_size: int
    uptime: float

# ============ Token Cache ============
class TokenCache:
    """Simple in-memory cache for tokens"""
    def __init__(self, ttl=300):
        self.cache = {}
        self.ttl = ttl
    
    def get(self, zone_id):
        """Get token from cache"""
        if zone_id in self.cache:
            token, timestamp = self.cache[zone_id]
            if time.time() - timestamp < self.ttl:
                return token
            else:
                del self.cache[zone_id]
        return None
    
    def set(self, zone_id, token):
        """Set token in cache"""
        self.cache[zone_id] = (token, time.time())
    
    def size(self):
        return len(self.cache)
    
    def clear(self):
        self.cache.clear()

# ============ Captcha Solver ============
class CN31Solver:
    """Single captcha solver instance"""
    
    def __init__(self, thread_id: int, zone_id: str, referer: str, 
                 captcha_id: str, fp_h: str):
        self.thread_id = thread_id
        self.zone_id = zone_id
        self.referer = referer
        self.captcha_id = captcha_id
        self.fp_h = fp_h
        self.ua = UserAgent().random
        self.domain = random.choice(DUN163_DOMAINS)
        self.session = self._create_session()
        self.ctx = self._load_js()
        
        if not self.ctx:
            raise RuntimeError("Failed to load JavaScript engine")
        
        self.fp = None
    
    def _create_session(self):
        """Create HTTP session"""
        session = requests.Session()
        domain_host = self.domain.replace('https://', '').replace('http://', '')
        
        session.headers.update({
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Pragma": "no-cache",
            "Referer": self.referer,
            "User-Agent": self.ua,
            "Host": domain_host,
        })
        
        session.timeout = (10, 30)
        return session
    
    def _load_js(self):
        """Load JavaScript from file"""
        js_path = os.path.join(os.path.dirname(__file__), 'dun163.js')
        
        if not os.path.exists(js_path):
            logger.error(f"JS file not found: {js_path}")
            return None
        
        try:
            with open(js_path, 'r', encoding='utf-8') as f:
                js_code = f.read()
            return execjs.compile(js_code)
        except Exception as e:
            logger.error(f"Failed to compile JS: {e}")
            return None
    
    @staticmethod
    def random_jsonp():
        """Generate random JSONP callback"""
        chars = string.ascii_lowercase + string.digits
        return f"__JSONP_{''.join(random.choices(chars, k=7))}_0"
    
    @staticmethod
    def extract_jsonp(text):
        """Extract JSON from JSONP"""
        import re, json
        match = re.search(r"\((.*)\)", text, re.S)
        if match:
            try:
                return json.loads(match.group(1))
            except:
                return {}
        return {}
    
    def generate_mock_clicks(self):
        """Generate mock click positions"""
        patterns = [
            [(80, 70), (160, 120), (240, 90)],
            [(70, 100), (160, 95), (250, 105)],
            [(160, 60), (110, 130), (210, 140)],
        ]
        
        pattern = random.choice(patterns)
        clicks = []
        
        for x, y in pattern:
            offset_x = random.randint(-3, 3)
            offset_y = random.randint(-3, 3)
            clicks.append({
                "x": max(10, min(x + offset_x, 310)),
                "y": max(10, min(y + offset_y, 190))
            })
        
        return clicks
    
    def solve(self, timeout=30) -> Dict[str, Any]:
        """Solve captcha and return token"""
        start_time = time.time()
        
        try:
            # Step 1: Get configuration
            url = f"{self.domain}/api/v2/getconf"
            params = {
                "referer": self.referer,
                "zoneId": self.zone_id,
                "dt": "",
                "id": self.captcha_id,
                "ipv6": "false",
                "runEnv": "10",
                "iv": "5",
                "loadVersion": "2.5.3",
                "lang": "en-US",
                "callback": self.random_jsonp()
            }
            
            resp = self.session.get(url, params=params, timeout=timeout)
            conf = self.extract_jsonp(resp.text).get('data', {})
            
            if not conf:
                return {"success": False, "error": "Failed to get configuration"}
            
            dt = conf.get('dt')
            ac_data = conf.get('ac', {})
            ac_token = ac_data.get('token')
            bid = ac_data.get('bid')
            
            if not all([dt, ac_token, bid]):
                return {"success": False, "error": "Missing required data"}
            
            # Step 2: Get captcha
            self.fp = self.ctx.call('get_fp', self.fp_h, self.ua)
            cb = self.ctx.call('get_cb')
            
            url = f"{self.domain}/api/v3/get"
            params = {
                "referer": self.referer,
                "zoneId": self.zone_id,
                "dt": dt,
                "id": bid,
                "fp": self.fp,
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
                "callback": self.random_jsonp()
            }
            
            ir_data = conf.get('ir', {})
            if ir_data.get('enable'):
                params["irToken"] = ir_data.get('token')
            
            resp = self.session.get(url, params=params, timeout=timeout)
            captcha_data = self.extract_jsonp(resp.text).get('data', {})
            
            token = captcha_data.get('token')
            captcha_type = captcha_data.get('type', 7)
            
            if not token:
                return {"success": False, "error": "No token in response"}
            
            # Step 3: Submit solution
            if captcha_type == 7:
                click_points = self.generate_mock_clicks()
                check_data = self.ctx.call('get_click_check_data', click_points, token)
            else:
                check_data = '{"d":"","m":"","p":"","ext":""}'
            
            url = f"{self.domain}/api/v3/check"
            params = {
                "referer": self.referer,
                "zoneId": self.zone_id,
                "dt": dt,
                "id": bid,
                "token": token,
                "data": check_data,
                "width": "320",
                "type": str(captcha_type),
                "version": "2.28.5",
                "cb": self.ctx.call('get_cb'),
                "user": "",
                "extraData": "",
                "bf": "0",
                "runEnv": "10",
                "sdkVersion": "",
                "loadVersion": "2.5.3",
                "iv": "4",
                "callback": self.random_jsonp()
            }
            
            resp = self.session.get(url, params=params, timeout=timeout)
            result = self.extract_jsonp(resp.text).get('data', {})
            
            if result.get('result') == True:
                validate_raw = result.get('validate', '')
                
                if validate_raw and self.ctx:
                    try:
                        final_token = self.ctx.call('do_onVerify', validate_raw, self.fp)
                    except:
                        final_token = validate_raw
                else:
                    final_token = validate_raw
                
                processing_time = time.time() - start_time
                
                return {
                    "success": True,
                    "token": final_token,
                    "validate": validate_raw,
                    "processing_time": processing_time,
                    "zone_id": self.zone_id
                }
            else:
                return {
                    "success": False,
                    "error": "Verification failed",
                    "processing_time": time.time() - start_time
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "processing_time": time.time() - start_time
            }


class SolverPool:
    """Pool of solvers for concurrent requests"""
    
    def __init__(self, max_workers=5):
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.cache = TokenCache()
    
    async def solve_token(self, zone_id: str, referer: str, 
                          captcha_id: str, fp_h: str) -> Dict:
        """Solve token asynchronously"""
        
        # Check cache first
        cached = self.cache.get(zone_id)
        if cached:
            return {
                "success": True,
                "token": cached,
                "cached": True,
                "zone_id": zone_id
            }
        
        # Run solver in thread pool
        loop = asyncio.get_event_loop()
        
        def _solve():
            solver = CN31Solver(
                thread_id=random.randint(1, 1000),
                zone_id=zone_id,
                referer=referer,
                captcha_id=captcha_id,
                fp_h=fp_h
            )
            return solver.solve()
        
        result = await loop.run_in_executor(self.executor, _solve)
        
        if result.get("success") and result.get("token"):
            self.cache.set(zone_id, result["token"])
        
        return result
    
    async def batch_solve(self, zone_id: str, count: int, 
                          referer: str, captcha_id: str, fp_h: str) -> Dict:
        """Generate multiple tokens"""
        start_time = time.time()
        tokens = []
        errors = []
        
        tasks = []
        for i in range(count):
            task = self.solve_token(zone_id, referer, captcha_id, fp_h)
            tasks.append(task)
        
        results = await asyncio.gather(*tasks)
        
        for result in results:
            if result.get("success") and result.get("token"):
                tokens.append(result["token"])
            else:
                errors.append(result.get("error", "Unknown error"))
        
        return {
            "success": len(tokens) > 0,
            "tokens": tokens,
            "count": len(tokens),
            "total_time": time.time() - start_time,
            "errors": errors
        }
    
    def get_stats(self):
        return {
            "workers": self.max_workers,
            "cache_size": self.cache.size()
        }


# ============ FastAPI Application ============
start_time = datetime.now()
solver_pool = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global solver_pool
    logger.info("Starting CN31 Token Fetcher API...")
    solver_pool = SolverPool(max_workers=MAX_WORKERS)
    yield
    logger.info("Shutting down...")
    if solver_pool and solver_pool.executor:
        solver_pool.executor.shutdown(wait=True)


app = FastAPI(
    title="CN31 Token Fetcher API",
    description="NetEase Captcha (Dun163) Token Generator",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============ API Endpoints ============

@app.get("/", response_class=HTMLResponse)
async def root():
    """API documentation page"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>CN31 Token Fetcher API</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; }
            h1 { color: #333; }
            .endpoint { background: #f4f4f4; padding: 10px; margin: 10px 0; border-radius: 5px; }
            code { background: #e0e0e0; padding: 2px 5px; border-radius: 3px; }
            pre { background: #333; color: #fff; padding: 10px; border-radius: 5px; overflow-x: auto; }
        </style>
    </head>
    <body>
        <h1>🔐 CN31 Token Fetcher API</h1>
        <p>NetEase Captcha (Dun163) Token Generator Service</p>
        
        <h2>Endpoints:</h2>
        
        <div class="endpoint">
            <strong>GET /health</strong><br>
            Health check endpoint
        </div>
        
        <div class="endpoint">
            <strong>POST /solve</strong><br>
            Generate a single token<br>
            <code>curl -X POST http://localhost:8000/solve -H "Content-Type: application/json" -d '{"zone_id": "CN31"}'</code>
        </div>
        
        <div class="endpoint">
            <strong>POST /batch</strong><br>
            Generate multiple tokens<br>
            <code>curl -X POST http://localhost:8000/batch -H "Content-Type: application/json" -d '{"zone_id": "CN31", "count": 5}'</code>
        </div>
        
        <div class="endpoint">
            <strong>GET /stats</strong><br>
            Get solver statistics
        </div>
        
        <div class="endpoint">
            <strong>DELETE /cache</strong><br>
            Clear token cache
        </div>
        
        <h2>Example Response:</h2>
        <pre>
{
    "success": true,
    "token": "CN31_xxx_v_i_1",
    "zone_id": "CN31",
    "timestamp": "2024-01-15T10:30:00",
    "processing_time": 2.45
}
        </pre>
        
        <h2>Interactive Docs:</h2>
        <p><a href="/docs">/docs</a> - Swagger UI</p>
        <p><a href="/redoc">/redoc</a> - ReDoc</p>
    </body>
    </html>
    """


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    stats = solver_pool.get_stats() if solver_pool else {}
    uptime = (datetime.now() - start_time).total_seconds()
    
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        workers_available=stats.get("workers", 0),
        cache_size=stats.get("cache_size", 0),
        uptime=uptime
    )


@app.post("/solve", response_model=TokenResponse)
async def solve_captcha(request: SolveRequest):
    """Solve captcha and return token"""
    if not solver_pool:
        raise HTTPException(status_code=503, detail="Solver pool not initialized")
    
    if request.count > 1:
        # Use batch endpoint for multiple tokens
        raise HTTPException(status_code=400, detail="Use /batch for multiple tokens")
    
    result = await solver_pool.solve_token(
        zone_id=request.zone_id,
        referer=request.referer,
        captcha_id=request.id,
        fp_h=request.fp_h
    )
    
    return TokenResponse(
        success=result.get("success", False),
        token=result.get("token"),
        validate=result.get("validate"),
        zone_id=request.zone_id,
        timestamp=datetime.now().isoformat(),
        processing_time=result.get("processing_time", 0),
        error=result.get("error")
    )


@app.post("/batch", response_model=BatchTokenResponse)
async def batch_solve(request: SolveRequest):
    """Generate multiple tokens"""
    if not solver_pool:
        raise HTTPException(status_code=503, detail="Solver pool not initialized")
    
    count = min(request.count, 10)  # Limit to 10 per request
    
    result = await solver_pool.batch_solve(
        zone_id=request.zone_id,
        count=count,
        referer=request.referer,
        captcha_id=request.id,
        fp_h=request.fp_h
    )
    
    return BatchTokenResponse(**result)


@app.get("/stats")
async def get_stats():
    """Get solver statistics"""
    if not solver_pool:
        return {"error": "Solver pool not initialized"}
    
    return solver_pool.get_stats()


@app.delete("/cache")
async def clear_cache():
    """Clear token cache"""
    if solver_pool:
        solver_pool.cache.clear()
        return {"status": "success", "message": "Cache cleared"}
    return {"status": "error", "message": "Solver pool not initialized"}

# ============ Main Entry ============
def main():
    """Run the API server"""
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    
    logger.info(f"Starting CN31 Token Fetcher API on {host}:{port}")
    logger.info(f"Workers: {MAX_WORKERS}")
    logger.info(f"Cache TTL: {TOKEN_CACHE_TTL}s")
    
    uvicorn.run(
        "app:app",
        host=host,
        port=port,
        reload=False,
        log_level="info"
    )


if __name__ == "__main__":
    main()