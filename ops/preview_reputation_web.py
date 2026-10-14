"""Isolated updated handler preview; does not recover jobs or restart port 7860."""
import os
from pathlib import Path
import sys
from http.server import ThreadingHTTPServer
from dotenv import load_dotenv
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
load_dotenv(ROOT/'.env',override=True)
import app
if __name__=='__main__':
    print('Reputation preview http://127.0.0.1:7861',flush=True)
    ThreadingHTTPServer(('127.0.0.1',7861),app.AgentDemoHandler).serve_forever()
