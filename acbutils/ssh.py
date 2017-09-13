import StringIO
import multiprocessing.dummy
import os
import subprocess
import textwrap
import zipfile
import sys
import functools

from .proc_utils import communicate_stream

def build_remote_script(script, vars={}, remotelib=None):
    buf = StringIO.StringIO()

    zf = zipfile.ZipFile(buf, "a", zipfile.ZIP_DEFLATED, False)
    zf.writestr("__main__.py", script)

    if remotelib:
        for root, dir, files in os.walk(remotelib):
            for f in files:
                zf.writestr(f, open(os.path.join(root, f)).read())
    zf.close()

    data = repr(buf.getvalue().encode('base64'))

    return textwrap.dedent('''
        import tempfile
        import runpy
        
        vars = %s
        data = %s
        
        with tempfile.NamedTemporaryFile(suffix='.zip') as f:
            f.write(data.decode('base64'))
            f.flush()
            runpy.run_path(f.name, init_globals=vars)
    ''' % (repr(vars), data))


def run_script_over_ssh(script, host, sudo=False):
    sudo_cmd = ['sudo'] if sudo else []
    cmd = ['ssh', host] + sudo_cmd + ['python', '-']
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = p.communicate(input=script)[0]
    return p.returncode, out.decode()

def run_scripts_over_ssh_parallel(scripts, hosts, sudo=False, max_conn=4):
    assert len(scripts) == len(hosts)
    def helper(args):
        script, host = args
        return run_script_over_ssh(script, host, sudo=sudo)
    p = multiprocessing.dummy.Pool(max_conn)
    return p.map(helper, zip(scripts, hosts))

def stream_script_over_ssh(script, host, stream_callback, sudo=False):
    sudo_cmd = ['sudo'] if sudo else []
    cmd = ['ssh', host] + sudo_cmd + ['python', '-u', '-']
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.STDOUT)
    for linetype, line in communicate_stream(p, script):
        stream_callback(linetype, line)
    return p.poll()

def stream_scripts_over_ssh_parallel(scripts, hosts, stream_callback, sudo=False, max_conn=4):
    assert len(scripts) == len(hosts)
    def helper(args):
        script, host = args
        return stream_script_over_ssh(script, host, functools.partial(stream_callback, host), sudo=sudo)
    p = multiprocessing.dummy.Pool(max_conn)
    return p.map(helper, zip(scripts, hosts))