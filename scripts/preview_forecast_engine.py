"""Local-only UI preview; never restarts 7860 or recovers existing report jobs.

Serves only the new forecast APIs, static UI and metadata on 127.0.0.1:8860.
Project archive writes are redirected to the preview's own runtime directory.
"""
import argparse
from pathlib import Path
import sys
from urllib.parse import urlparse

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))


def main(port=8860):
    import app
    preview=PROJECT/('runtime/forecast-engine-preview' if port == 8860 else f'runtime/forecast-engine-preview-{port}')
    preview.mkdir(parents=True,exist_ok=True)
    (preview/'README.md').write_text(f'Local-only forecast UI preview on 127.0.0.1:{port}. No recovery of existing report jobs; original service remains untouched. Preview project archives are isolated here.\n',encoding='utf-8')
    app.PROJECT_RUNS_FILE=preview/'project-runs.json'
    class Handler(app.AgentDemoHandler):
        def do_GET(self):
            path=urlparse(self.path).path
            if path.startswith('/api/') and not (path.startswith('/api/forecast-engine/') or path in {'/api/health','/api/models'}):
                self._send_json({'error':'此端口仅预览新版市场预测；其他功能请使用原服务。'},status=503);return
            super().do_GET()
        def do_POST(self):
            if urlparse(self.path).path not in {'/api/forecast-engine/jobs','/api/forecast-engine/chronos-jobs','/api/forecast-engine/local-insights','/api/forecast-engine/deepseek-insights','/api/chat'}:
                self._send_json({'error':'预览不执行其他业务任务。'},status=403);return
            super().do_POST()
        def do_DELETE(self):
            self._send_json({'error':'预览不删除业务数据。'},status=403)
    server=app.ThreadingHTTPServer(('127.0.0.1',port),Handler)
    app.AGENT_LOOP_RUNNER.start()
    print(f'Forecast UI preview: http://127.0.0.1:{port}/#forecast-engine',flush=True)
    try:server.serve_forever()
    finally:server.server_close();app.AGENT_LOOP_RUNNER.stop()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8860,choices=range(1024,65536),metavar='PORT')
    main(parser.parse_args().port)
