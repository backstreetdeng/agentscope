"""Loopback-only SSH channel supervisor. No public plaintext MCP endpoint."""
from pathlib import Path
import os
import socket
import subprocess
import threading
import time

ROOT=Path(__file__).resolve().parents[1]
_lock=threading.Lock()
_process=None

def ensure_tunnel(url):
    global _process
    from urllib.parse import urlsplit
    if urlsplit(url).netloc != '127.0.0.1:18812': return
    with _lock:
        try:
            with socket.create_connection(('127.0.0.1',18812),timeout=.3): return
        except OSError: pass
        if _process is None or _process.poll() is not None:
            python=ROOT/'runtime'/'rights-ssh-env'/'Scripts'/'python.exe'
            if not python.is_file():
                raise RuntimeError('缺少项目独立 SSH 通道环境，请按权益运维手册安装')
            log=ROOT/'runtime'/'rights-tunnel.log'; log.parent.mkdir(exist_ok=True)
            with log.open('ab') as out:
                _process=subprocess.Popen([str(python),str(ROOT/'ops'/'rights_ssh_tunnel.py')],
                    cwd=ROOT,stdout=out,stderr=out,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        for _ in range(60):
            try:
                with socket.create_connection(('127.0.0.1',18812),timeout=.2): return
            except OSError: time.sleep(.1)
        raise ConnectionError('权益 SSH 加密通道尚未就绪')
