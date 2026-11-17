"""Real loopback sockets and owned subprocesses; never uses the review server."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import urlopen

import pytest
from conftest import create_valid_snapshot


LAUNCHER = '''
import asyncio, logging, os
from pathlib import Path
from contextlib import asynccontextmanager
from uuid import UUID
import uvicorn
from sistema_incendios_forestales.api.app import app, lifespan
from sistema_incendios_forestales.api.contracts import AnalysisRequest
from sistema_incendios_forestales.analysis import build_deterministic_result
from sistema_incendios_forestales.llm import MockLLM
from sistema_incendios_forestales.operational_logging import configure_logging

class ObservedMock(MockLLM):
    def complete(self, *args, **kwargs):
        Path(os.environ['CALLS']).write_text('unexpected call')
        raise AssertionError('Provider must not be called')

@asynccontextmanager
async def isolated(application):
    async with lifespan(application):
        application.state.llm_provider = ObservedMock({})
        store = application.state.audit_store
        snapshot = application.state.snapshot
        if os.environ['SEED'] == '1':
            i = UUID(os.environ['RUN_ID'])
            request = AnalysisRequest(weather_id=snapshot.coverage['features'][0]['properties']['weather_id'], date='2021-01-01')
            store.create_queued(i, request)
            store._mark_started(i)
            if os.environ['CORE'] == '1':
                store._persist_core_result(i, build_deterministic_result(snapshot, request, i, application.state.settings.snapshot_manifest_sha256))
        yield
    try:
        store.connection.execute('SELECT 1')
    except Exception:
        Path(os.environ['CLOSED']).write_text('audit closed')
    try:
        snapshot.connection.execute('SELECT 1')
    except Exception:
        Path(os.environ['CLOSED'] + '.snapshot').write_text('snapshot closed')

app.router.lifespan_context = isolated
@app.get('/test/owner')
async def owner():
    return {'pid': os.getpid()}
app.router.routes.insert(0, app.router.routes.pop())
handler = configure_logging(os.environ)
async def main():
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=int(os.environ['PORT']), workers=1, log_config=None))
    async def stop():
        while not Path(os.environ['STOP']).exists():
            await asyncio.sleep(.05)
        server.should_exit = True
    task = asyncio.create_task(stop())
    try:
        await server.serve()
    finally:
        task.cancel()
        handler.close()
asyncio.run(main())
'''

PYTHON = getattr(sys, '_base_executable', sys.executable)


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def wait_ready(process, base):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError('Owned backend exited before readiness')
        try:
            with urlopen(base + '/api/health/ready', timeout=.5) as response:
                assert json.load(response)['status'] == 'ready'
                return
        except OSError:
            time.sleep(.05)
    raise AssertionError('Readiness timeout')


@pytest.mark.parametrize('core', [False, True])
def test_real_socket_disconnect_process_restart_and_shutdown(tmp_path, core):
    digest = create_valid_snapshot(tmp_path / 'snapshot')
    launcher = tmp_path / 'launch.py'
    launcher.write_text(LAUNCHER, encoding='utf-8')
    port = free_port()
    base = f'http://127.0.0.1:{port}'
    run_id = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
    env = {k: v for k, v in os.environ.items() if not k.startswith('FIREWATCH_') and k != 'OPENAI_API_KEY'}
    env.update(FIREWATCH_SNAPSHOT_DIR=str(tmp_path / 'snapshot'), FIREWATCH_SNAPSHOT_VERSION='1.0.0',
               FIREWATCH_SNAPSHOT_MANIFEST_SHA256=digest, FIREWATCH_AUDIT_DB=str(tmp_path / 'audit.sqlite'),
               FIREWATCH_LLM_PROVIDER='mock', FIREWATCH_LOG_PATH=str(tmp_path / 'server.log'),
               PORT=str(port), RUN_ID=run_id, SEED='1', CORE=str(int(core)),
               CALLS=str(tmp_path / 'calls'), CLOSED=str(tmp_path / 'closed'), STOP=str(tmp_path / 'stop'))
    env['PYTHONPATH'] = os.pathsep.join(sys.path)
    process = None
    try:
        process = subprocess.Popen([PYTHON, str(launcher)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        wait_ready(process, base)
        with urlopen(base + '/test/owner') as response:
            assert json.load(response)['pid'] == process.pid
        stream = socket.create_connection(('127.0.0.1', port), timeout=3)
        stream.sendall(f'GET /api/analyses/{run_id}/trace/events HTTP/1.1\r\nHost: 127.0.0.1\r\nLast-Event-ID: 0\r\n\r\n'.encode())
        received = b''
        cursor = 3 if core else 2
        while f'id: {cursor}\n'.encode() not in received:
            received += stream.recv(8192)
        stream.close()  # Real client socket disconnect while run remains running.
        with urlopen(base + f'/api/analyses/{run_id}') as response:
            assert json.load(response)['state'] == 'running'
        process.kill()  # Only the Popen child owned by this test.
        process.wait(timeout=10)
        env['SEED'] = '0'
        process = subprocess.Popen([PYTHON, str(launcher)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        wait_ready(process, base)
        from urllib.request import Request
        with urlopen(Request(base + f'/api/analyses/{run_id}/trace/events', headers={'Last-Event-ID': str(cursor)}), timeout=5) as response:
            replay = response.read().decode()
        assert [int(line[4:]) for line in replay.splitlines() if line.startswith('id: ')] == [cursor+1, cursor+2]
        assert 'event: run_interrupted' in replay
        assert f"event: run_{'partial' if core else 'failed'}" in replay
        with urlopen(base + f'/api/analyses/{run_id}') as response:
            recovered = json.load(response)
        assert recovered['state'] == ('partial' if core else 'failed')
        assert (recovered['result'] is not None) == core
        assert not recovered.get('explanation')
        assert not (tmp_path / 'calls').exists()
        (tmp_path / 'stop').touch()
        assert process.wait(timeout=10) == 0
        assert (tmp_path / 'closed').read_text() == 'audit closed'
        assert (tmp_path / 'closed.snapshot').read_text() == 'snapshot closed'
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', port))
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait(timeout=10)


def test_invalid_configuration_and_occupied_port(tmp_path):
    launcher = tmp_path / 'launch.py'
    launcher.write_text(LAUNCHER, encoding='utf-8')
    env = {k:v for k,v in os.environ.items() if not k.startswith('FIREWATCH_') and k != 'OPENAI_API_KEY'}
    env.update(PORT=str(free_port()), STOP=str(tmp_path/'stop'), FIREWATCH_LOG_PATH=str(tmp_path/'log'))
    env['PYTHONPATH'] = os.pathsep.join(sys.path)
    result = subprocess.run([PYTHON, str(launcher)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
    assert result.returncode != 0
    digest = create_valid_snapshot(tmp_path/'snapshot')
    env.update(FIREWATCH_SNAPSHOT_DIR=str(tmp_path/'snapshot'), FIREWATCH_SNAPSHOT_VERSION='1.0.0',
               FIREWATCH_SNAPSHOT_MANIFEST_SHA256=digest, FIREWATCH_AUDIT_DB=str(tmp_path/'audit.sqlite'),
               FIREWATCH_LLM_PROVIDER='mock', SEED='0', CLOSED=str(tmp_path/'closed'))
    with socket.socket() as occupied:
        occupied.bind(('127.0.0.1',0))
        occupied.listen()
        env['PORT'] = str(occupied.getsockname()[1])
        result = subprocess.run([PYTHON, str(launcher)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        assert result.returncode != 0
