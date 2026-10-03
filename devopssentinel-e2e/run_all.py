#!/usr/bin/env python3
"""Isolated, bounded, real-API validation. Never writes a remote Git repository."""
import argparse
import contextlib
import copy
import csv
import datetime as dt
import hashlib
import importlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import socket
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
NAMESPACES = ['devopssentinel-e2e', 'devopssentinel-e2e-peer',
              'devopssentinel-e2e-gitops', 'devopssentinel-e2e-pki']
LABELS = {'devopssentinel.io/test-suite': 'true',
          'app.kubernetes.io/part-of': 'devopssentinel-e2e'}

class Blocked(Exception): pass
class NotApplicable(Exception): pass

def sanitized(value):
    if isinstance(value, dict):
        value = copy.deepcopy(value)
        if value.get('kind') == 'Secret':
            for field in ('data', 'stringData'):
                if field in value:
                    value[field] = {key: '[REDACTED]' for key in value[field]}
        for key in ('managedFields',): value.pop(key, None)
        if 'annotations' in value:
            value['annotations'].pop('kubectl.kubernetes.io/last-applied-configuration', None)
        return {k: sanitized(v) for k,v in value.items()}
    if isinstance(value, list): return [sanitized(v) for v in value]
    return value

class Harness:
    def __init__(self, args):
        self.args, self.root, self.ns, self.labels = args, ROOT, NAMESPACES[0], LABELS
        self.tools_image = 'ds-e2e-tools:local'
        self.context = args.context or self.command(['kubectl','config','current-context']).stdout.strip()
        self.stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        self.out = Path.home() / '.devopssentinel' / 'real-e2e' / self.stamp
        self.out.mkdir(parents=True, mode=0o700)
        self.results, self.current, self.calls, self.created = [], 'setup', [], []
        self.fixture_cache = {}
        self.selected = set(args.test or [])
        if args.failed:
            last = ROOT/'devopssentinel-e2e/reports/DEVOPSSENTINEL_E2E_RESULTS.json'
            self.selected.update(r['id'] for r in json.loads(last.read_text())['results']
                                 if r['status'] in ('FAIL','BLOCKED'))

    def command(self, argv, timeout=60, input=None, env=None, **kwargs):
        start = time.monotonic()
        result = subprocess.run([str(a) for a in argv], input=input, text=True,
                                capture_output=True, timeout=timeout, env=env, **kwargs)
        if hasattr(self,'calls'):
            self.calls.append({'program':str(argv[0]), 'duration':round(time.monotonic()-start,3),
                               'returncode':result.returncode, 'case':self.current})
        return result

    def k(self, args, ns=None, timeout=60, input=None):
        argv=['kubectl','--context',self.context,'--request-timeout=15s']
        if ns: argv += ['-n',ns]
        return self.command(argv+list(args),timeout=timeout,input=input)

    def evidence(self,name,data):
        path=self.out/self.current/name
        path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        if isinstance(data,(dict,list)): data=json.dumps(sanitized(data),indent=2)+'\n'
        path.write_text(str(data)); path.chmod(0o600)
        return path

    def get(self,resource,name=None,ns=None):
        args=['get',resource]+([name] if name else [])+['-o','json']
        proc=self.k(args,ns=ns)
        if proc.returncode: raise RuntimeError(proc.stderr.strip())
        obj=json.loads(proc.stdout)
        self.evidence('api-'+resource.replace('/','_')+'-'+(name or 'list')+'.json',obj)
        return obj

    def shell(self,code,ns=None,timeout=180,env=None):
        # Source the real Sentinel and run a read-only bash snippet. $0 must not
        # be the script path or the Sentinel's main guard would parse our args.
        prefix=('source "$1"; shift; SENTINEL_CONTEXT=$1 SENTINEL_NAMESPACE=$2 OUTPUT_DIR=$3; '
                'shift 3; NO_COLOR_FLAG=1; API_TIMEOUT=8; dependency_detect; color_init; terminal_size; '
                'init_runtime || exit; advanced_runtime_init || exit; bootstrap_scope || exit; ')
        return self.command(['bash','-c',prefix+code,'sentinel-shell',
                             str(ROOT/'DevOps_K8s_Sentinel_FINAL_GP.sh'),self.context,ns or self.ns,
                             str(self.out/'runtime')],timeout=timeout,env=env)

    def wait(self,resource,name,predicate,ns=None,timeout=120):
        deadline=time.monotonic()+timeout; last={}
        while time.monotonic()<deadline:
            proc=self.k(['get',resource,name,'-o','json'],ns=ns)
            if proc.returncode==0:
                last=json.loads(proc.stdout)
                if predicate(last):
                    self.evidence('api-'+resource.replace('/','_')+'-'+name+'.json',last)
                    return last
            time.sleep(2)
        self.evidence('timeout-'+name+'.json',last)
        raise AssertionError(f'Kubernetes state deadline {timeout}s: {resource}/{name}')

    def apply(self,obj,ns=None):
        obj=copy.deepcopy(obj); kind=obj['kind']; meta=obj.setdefault('metadata',{})
        name=meta.get('name','')
        if kind=='Namespace':
            assert name in NAMESPACES
        else:
            ns=ns or meta.get('namespace') or self.ns
            assert ns in NAMESPACES and name.startswith('ds-e2e-'), (kind,ns,name)
            meta['namespace']=ns
        meta.setdefault('labels',{}).update(LABELS)
        if 'template' in obj.get('spec',{}):
            obj['spec']['template'].setdefault('metadata',{}).setdefault('labels',{}).update(LABELS)
        for claim in obj.get('spec',{}).get('volumeClaimTemplates',[]):
            claim.setdefault('metadata',{}).setdefault('labels',{}).update(LABELS)
        # Do not adopt or overwrite an existing unowned object.
        old=self.k(['get',kind,name,'-o','json'],ns=None if kind=='Namespace' else ns)
        if old.returncode==0:
            old=json.loads(old.stdout)
            assert all(old['metadata'].get('labels',{}).get(k)==v for k,v in LABELS.items()), f'Unowned collision: {kind}/{name}'
        self.evidence('manifest-'+kind+'-'+name+'.json',obj)
        proc=self.k(['apply','--server-side','--field-manager=devopssentinel-e2e','-f','-'],
                    input=json.dumps(obj),ns=None if kind=='Namespace' else ns)
        if proc.returncode: raise RuntimeError(proc.stderr)
        self.created.append((kind,ns,name))
        return obj

    def sentinel(self,args,ns=None,timeout=90,env=None):
        proc=self.command(['bash',ROOT/'DevOps_K8s_Sentinel_FINAL_GP.sh',
            '--context',self.context,'--namespace',ns or self.ns,'--no-color',
            '--output',self.out/'runtime','--api-timeout','8',*args],timeout=timeout,env=env)
        index=sum(p.name.startswith('sentinel-') and p.suffix=='.stdout' for p in (self.out/self.current).glob('*')) if (self.out/self.current).exists() else 0
        self.evidence(f'sentinel-{index}.stdout',proc.stdout)
        self.evidence(f'sentinel-{index}.stderr',proc.stderr)
        self.evidence(f'sentinel-{index}.command.json',{'args':args,'namespace':ns or self.ns,'exit':proc.returncode})
        assert not re.search(r'jq: error|command not found|unbound variable|syntax error',proc.stdout+proc.stderr), 'Runtime diagnostic in Sentinel output'
        return proc

    def function(self,name,args=(),ns=None,timeout=90,env=None):
        assert re.fullmatch('[A-Za-z_][A-Za-z0-9_]*',name)
        code='source "$1"; shift; SENTINEL_CONTEXT=$1 SENTINEL_NAMESPACE=$2 OUTPUT_DIR=$3; shift 3; NO_COLOR_FLAG=1; API_TIMEOUT=8; dependency_detect; color_init; terminal_size; init_runtime || exit; advanced_runtime_init || exit; bootstrap_scope || exit; "$@"'
        proc=self.command(['bash','-c',code,'sentinel-function',ROOT/'DevOps_K8s_Sentinel_FINAL_GP.sh',
                           self.context,ns or self.ns,self.out/'runtime',name,*args],timeout=timeout,env=env)
        self.evidence(name+'.stdout',proc.stdout); self.evidence(name+'.stderr',proc.stderr)
        return proc

    @contextlib.contextmanager
    def forward(self,service,remoteport,ns=None):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
        resource=service if '/' in service else 'service/'+service
        proc=subprocess.Popen(['kubectl','--context',self.context,'-n',ns or self.ns,
                               'port-forward',resource,f'{port}:{remoteport}','--address=127.0.0.1'],
                              stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
        try:
            deadline=time.monotonic()+20
            while time.monotonic()<deadline:
                if proc.poll() is not None: raise RuntimeError('Port-forward failed: '+proc.stderr.read())
                try:
                    with socket.create_connection(('127.0.0.1',port),timeout=.5): break
                except OSError: time.sleep(.2)
            else: raise AssertionError('Port-forward startup deadline')
            yield port
        finally:
            proc.terminate()
            try: proc.wait(timeout=5)
            except subprocess.TimeoutExpired: proc.kill();proc.wait(timeout=5)
            proc.stderr.close()

    def block(self,reason): raise Blocked(reason)
    def na(self,reason): raise NotApplicable(reason)

    def case(self,id,domain,title,fn):
        if self.selected and id not in self.selected: return
        previous=self.current; self.current=id
        start=time.monotonic(); status='PASS'; detail={}; reason=''
        print(f'[{id}] {title}',flush=True)
        try:
            detail=fn() or {}
            if not isinstance(detail,dict): detail={'observations':str(detail)}
        except Blocked as exc: status,reason='BLOCKED',str(exc)
        except NotApplicable as exc: status,reason='NOT_APPLICABLE',str(exc)
        except Exception as exc:
            status,reason='FAIL',str(exc)
            self.evidence('exception.txt',traceback.format_exc())
        row={'id':id,'domain':domain,'title':title,'status':status,'reason':reason,
             'duration_seconds':round(time.monotonic()-start,3),'evidence_path':str(self.out/id),**detail}
        self.results.append(row); self.evidence('result.json',row)
        self.current=previous
        print(f'  {status} {reason}',flush=True)
        self.report()

    def safety(self):
        assert 'microsoft' in platform.release().lower(), 'SAFETY BLOCK: WSL required'
        cfg=json.loads(self.command(['kubectl','config','view','--minify','-o','json']).stdout)
        assert cfg['current-context']==self.context, 'SAFETY BLOCK: selected and active context differ'
        server=cfg['clusters'][0]['cluster']['server']
        assert re.match(r'https://(localhost|127\.0\.0\.1|\[::1\])[:/]',server), 'SAFETY BLOCK: API not loopback'
        containers=self.command(['docker','ps','--format','{{.Names}}']).stdout.splitlines()
        assert self.context=='vcluster-docker_dev' and 'vcluster.cp.dev' in containers, 'SAFETY BLOCK: unverified local implementation'
        nodes=self.get('nodes')
        assert len(nodes['items'])==1 and nodes['items'][0]['metadata']['name']=='dev', 'Unexpected local node identity'
        self.evidence('safety.json',{'wsl':platform.release(),'context':self.context,'server':server,
            'implementation':'vcluster in local WSL Docker','container':'vcluster.cp.dev','verified':True})

    def snapshot(self,name):
        data={}
        for resource in ['nodes','namespaces','storageclasses','customresourcedefinitions','ingressclasses']:
            p=self.k(['get',resource,'-o','json']); data[resource]=json.loads(p.stdout) if p.returncode==0 else {'unavailable':p.stderr}
        for resource in ['deployments','statefulsets','daemonsets','pods','gitrepositories.source.toolkit.fluxcd.io','kustomizations.kustomize.toolkit.fluxcd.io']:
            p=self.k(['get',resource,'-A','-o','json']); data[resource]=json.loads(p.stdout) if p.returncode==0 else {'unavailable':p.stderr}
        self.evidence(name+'.json',data)
        return data

    def install_prerequisites(self):
        """Install a pinned cert-manager only on this verified disposable local cluster."""
        crd=self.k(['get','crd','certificates.cert-manager.io','-o','name'])
        if crd.returncode==0:
            self.evidence('prereq-cert-manager.json',{'state':'present'}); return
        if not self.args.install_prereqs:
            self.evidence('prereq-cert-manager.json',{'state':'absent','installed':False,
                'hint':'pass --install-prereqs to install pinned cert-manager v1.15.3 on this disposable local cluster'})
            return
        url='https://github.com/cert-manager/cert-manager/releases/download/v1.15.3/cert-manager.yaml'
        applied=self.command(['kubectl','--context',self.context,'apply','-f',url],timeout=240)
        self.evidence('prereq-cert-manager-install.txt',applied.stdout+applied.stderr)
        assert applied.returncode==0,'cert-manager install failed'
        for name in ('cert-manager','cert-manager-cainjector','cert-manager-webhook'):
            self.wait('deployments',name,lambda r: r.get('status',{}).get('availableReplicas',0)>=1,
                      ns='cert-manager',timeout=300)
        self.wait('crd','certificates.cert-manager.io',
                  lambda r: any(c.get('type')=='Established' and c.get('status')=='True' for c in r.get('status',{}).get('conditions',[])),
                  timeout=180)
        self.evidence('prereq-cert-manager.json',{'state':'installed','version':'v1.15.3','url':url})

    def setup(self):
        self.safety(); self.baseline=self.snapshot('baseline-before')
        self.install_prerequisites()
        for ns in NAMESPACES: self.apply({'apiVersion':'v1','kind':'Namespace','metadata':{'name':ns}})
        build=self.command(['docker','build','-t',self.tools_image,'-f',ROOT/'devopssentinel-e2e/Dockerfile',ROOT],timeout=300)
        self.evidence('tools-image-build.txt',build.stdout+build.stderr)
        assert build.returncode==0, 'E2E tools image build failed'
        # Explicit local container import; never publish an image.
        pipe=self.command(['bash','-c','set -o pipefail; docker save ds-e2e-tools:local | docker exec -i vcluster.cp.dev ctr -n k8s.io images import -'],timeout=180)
        self.evidence('tools-image-import.txt',pipe.stdout+pipe.stderr)
        assert pipe.returncode==0, 'E2E tools image import failed'

    def cleanup(self):
        self.current='cleanup'; self.safety()
        for ns in NAMESPACES:
            obj=self.k(['get','namespace',ns,'-o','json'])
            if obj.returncode: continue
            meta=json.loads(obj.stdout)['metadata']
            assert all(meta.get('labels',{}).get(k)==v for k,v in LABELS.items()), 'Refuse cleanup of unowned namespace '+ns
            # Namespace deletion cascades: refuse if any namespaced objects were added without ownership.
            resources=self.k(['api-resources','--verbs=list','--namespaced=true','-o','name']).stdout.splitlines()
            unowned=[]
            for resource in resources:
                if resource in ('events','events.events.k8s.io'): continue
                items=self.k(['get',resource,'-o','json'],ns=ns)
                if items.returncode: continue
                for item in json.loads(items.stdout).get('items',[]):
                    m=item['metadata']; n=m['name']
                    if (resource=='serviceaccounts' and n=='default') or (resource=='configmaps' and n=='kube-root-ca.crt'): continue
                    if not all(m.get('labels',{}).get(k)==v for k,v in LABELS.items()) and not m.get('ownerReferences'):
                        # Controller generated Helm storage Secrets have trusted Helm ownership labels.
                        if resource=='secrets' and m.get('labels',{}).get('owner')=='helm' and n.startswith('sh.helm.release.v1.ds-e2e-'): continue
                        # Flux derives a HelmChart (<namespace>-<release>) from an owned
                        # HelmRelease; it carries no ownerReference and is a test artifact.
                        if resource=='helmcharts.source.toolkit.fluxcd.io' and n.startswith(ns+'-ds-e2e-'): continue
                        unowned.append(resource+'/'+n)
            assert not unowned, f'Refuse namespace deletion with unowned objects: {ns}: {unowned}'
            print('CLEANUP namespace/'+ns+' (owned E2E objects only)',flush=True)
            result=self.k(['delete','namespace',ns,'--wait=true','--timeout=120s'],timeout=135)
            self.evidence(ns+'.txt',result.stdout+result.stderr)
            assert result.returncode==0, 'Namespace cleanup failed '+ns

    def report(self):
        directory=ROOT/'devopssentinel-e2e/reports'; directory.mkdir(exist_ok=True)
        summary={'mode':self.args.mode,'timestamp':self.stamp,'context':self.context,
                 'source_sha256':hashlib.sha256((ROOT/'DevOps_K8s_Sentinel_FINAL_GP.sh').read_bytes()).hexdigest(),
                 'evidence_root':str(self.out),'counts':{s:sum(r['status']==s for r in self.results)
                  for s in ['PASS','FAIL','BLOCKED','NOT_APPLICABLE']},'results':self.results}
        (directory/'DEVOPSSENTINEL_E2E_RESULTS.json').write_text(json.dumps(summary,indent=2)+'\n')
        cols=['id','domain','title','status','reason','duration_seconds','evidence_path']
        with (directory/'DEVOPSSENTINEL_E2E_RESULTS.csv').open('w',newline='') as f:
            writer=csv.DictWriter(f,cols,extrasaction='ignore');writer.writeheader();writer.writerows(self.results)
        lines=['# DevOpsSentinel real WSL E2E validation', '',f'Run: {self.stamp}; mode: {self.args.mode}; context: `{self.context}`.',
               '',f'Source SHA-256: `{summary["source_sha256"]}`.', '',f'Private evidence: `{self.out}`.',
               '', '**Release gate: NOT APPROVED.** Review failures, blocked coverage and requirement traceability before deployment.',
               '', 'Counts: '+', '.join(f'{k}={v}' for k,v in summary['counts'].items()),'',
               '| ID | Domain | Test | Status | Detail |','|---|---|---|---|---|']
        lines += [f'| {r["id"]} | {r["domain"]} | {r["title"]} | {r["status"]} | {r["reason"].replace(chr(10)," ").replace("|","/")} |' for r in self.results]
        (directory/'DEVOPSSENTINEL_E2E_REPORT.md').write_text('\n'.join(lines)+'\n')
        (directory/'performance.json').write_text(json.dumps(self.calls,indent=2)+'\n')

def main():
    os.umask(0o077)
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--context'); p.add_argument('--mode',choices=['QUICK','STANDARD','FULL'],default='FULL')
    p.add_argument('--test',action='append');p.add_argument('--domain',action='append');p.add_argument('--failed',action='store_true')
    p.add_argument('--cleanup-only',action='store_true');p.add_argument('--keep',action='store_true')
    p.add_argument('--install-prereqs',action='store_true')
    args=p.parse_args(); h=Harness(args)
    if args.cleanup_only: h.cleanup(); return 0
    try:
        h.setup()
        for module in ['workloads','pki','gitops','database','experience']:
            if args.domain and module not in args.domain and not (module=='pki' and 'certificates' in args.domain) and not (module=='workloads' and any(d in args.domain for d in ['networking','storage','dependencies'])): continue
            try: importlib.import_module(module).run(h)
            except Exception as exc:
                h.case('SETUP-'+module,module,'Module setup',lambda exc=exc: h.block(str(exc)))
    except Exception as exc:
        h.case('SAFETY-SETUP','harness','Safety gate / prerequisites',lambda exc=exc: h.block(str(exc)))
    finally:
        h.current='final'; h.snapshot('baseline-after-tests')
        failed=any(r['status'] in ('FAIL','BLOCKED') for r in h.results)
        if not args.keep and not (os.environ.get('KEEP_ON_FAILURE')=='1' and failed):
            try: h.cleanup()
            except Exception as exc: h.case('CLEANUP','harness','Owned fixture cleanup',lambda exc=exc: h.block(str(exc)))
        h.current='final'; h.snapshot('baseline-after-cleanup');h.report()
        print('REPORT '+str(ROOT/'devopssentinel-e2e/reports/DEVOPSSENTINEL_E2E_REPORT.md'),flush=True)
    return int(any(r['status'] in ('FAIL','BLOCKED') for r in h.results))

if __name__=='__main__': sys.exit(main())
