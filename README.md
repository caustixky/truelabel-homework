# Adaptive load shape

Install (creates a venv and installs deps):
```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run the mock server (port 8000):
```
python server.py
```

In another terminal, run the load test:
```
locust -f locustfile.py --host=http://localhost:8000 --headless
```

The test stops on its own when p95 regresses by ≥20% between steps and
prints `Threshold passed at N users`.

### Troubleshooting

**`OSError: [Errno 24] Too many open files`** on macOS — default FD limit
is ~256, each TCP connection eats one. Raise it in both shells (server
and locust) before running:
```
ulimit -n 10000
```
