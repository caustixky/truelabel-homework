import asyncio
import random
import time

from fastapi import FastAPI, Response
import uvicorn

DEGRADATION_THRESHOLD = random.randint(500, 2000)
print(f"Degradation threshold: {DEGRADATION_THRESHOLD} RPS")

app = FastAPI()

_current_second = 0
_requests_this_second = 0


@app.get("/api/v1/test")
async def endpoint():
    global _current_second, _requests_this_second

    now = int(time.time())
    if now == _current_second:
        _requests_this_second += 1
    else:
        _current_second = now
        _requests_this_second = 1

    delay = 5 if _requests_this_second > DEGRADATION_THRESHOLD else 0.05
    await asyncio.sleep(delay)
    return Response(status_code=200)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")
