"""SSH forward: Windows loopback18812 -> cloud loopback8812; no secrets in logs."""
import sys
from pathlib import Path
import re
import select
import socketserver
import time
import threading
import os

import paramiko
transport=None
PID_PATH = Path(__file__).resolve().parents[1] / 'runtime' / 'rights-tunnel.pid'


def acquire_instance() -> bool:
    """Ensure only one local tunnel owner can run across web-service restarts."""
    PID_PATH.parent.mkdir(exist_ok=True)
    for _ in range(2):
        try:
            fd = os.open(PID_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                existing_pid = int(PID_PATH.read_text(encoding='ascii').strip())
                os.kill(existing_pid, 0)
            except (ValueError, OSError):
                try:
                    PID_PATH.unlink()
                except FileNotFoundError:
                    pass
                continue
            return False
        else:
            with os.fdopen(fd, 'w', encoding='ascii') as handle:
                handle.write(str(os.getpid()))
            return True
    return False


def release_instance() -> None:
    try:
        if PID_PATH.read_text(encoding='ascii').strip() == str(os.getpid()):
            PID_PATH.unlink()
    except FileNotFoundError:
        pass

def connect():
    text=Path(os.getenv('RIGHTS_SSH_CREDENTIALS_PATH',str(Path.home()/'.codex/skills/tencent-cloud-price-monitor-ssh/.env'))).read_text(encoding='utf-8-sig')
    lines=text.splitlines(); password=None
    for index,line in enumerate(lines):
        m=re.match(r'^\s*(?:[-*]\s*)?(?:\*\*)?(?:密码|登录密码|服务器密码|SSH_PASSWORD|PASSWORD)(?:\*\*)?\s*[:：=]\s*(.*?)\s*$',line,re.I)
        if m:
            password=m.group(1).strip().strip('`').strip('"').strip("'") or lines[index+1].strip().strip('`'); break
    if not password: raise RuntimeError('credential_format_invalid')
    client=paramiko.SSHClient();client.load_host_keys(str(Path.home()/'.ssh/known_hosts'))
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    client.connect('82.157.138.187',username='ubuntu',password=password,allow_agent=False,look_for_keys=False,timeout=15,auth_timeout=15)
    client.get_transport().set_keepalive(20)
    return client

class Forward(socketserver.BaseRequestHandler):
    def handle(self):
        channel=None
        try:
            if not transport or not transport.is_active(): return
            channel=transport.open_channel('direct-tcpip',('127.0.0.1',8812),self.request.getpeername(),timeout=10)
            while True:
                ready,_,_=select.select([self.request,channel],[],[],30)
                for source in ready:
                    data=source.recv(65536)
                    if not data: return
                    (channel if source is self.request else self.request).sendall(data)
        except Exception: pass
        finally:
            if channel: channel.close()

class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address=True
    daemon_threads=True

if __name__=='__main__':
    if not acquire_instance():
        print('rights_tunnel_already_running', flush=True)
        sys.exit(0)
    try:
        client=connect();transport=client.get_transport()
        server=Server(('127.0.0.1',18812),Forward)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        print('rights_tunnel_ready',flush=True)
        while True:
            time.sleep(5)
            if not transport.is_active():
                client.close()
                try: client=connect();transport=client.get_transport(); print('rights_tunnel_reconnected',flush=True)
                except paramiko.AuthenticationException: print('authentication_failed_no_retry',flush=True);break
                except Exception: time.sleep(20)
        server.shutdown()
    except Exception as exc:
        print('rights_tunnel_failed:',type(exc).__name__,flush=True)
        sys.exit(1)
    finally:
        release_instance()
