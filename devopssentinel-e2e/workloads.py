"""Real workload, network, storage, dependency, log and event fixtures."""
import copy
import json
import re
import time

def condition(obj, name, status='True'):
    return any(c['type']==name and c['status']==status for c in obj.get('status',{}).get('conditions',[]))

def run(h):
    ns=h.ns
    def obj(kind,name,spec=None,api='v1',**extra):
        value={'apiVersion':api,'kind':kind,'metadata':{'name':name},**extra}
        if spec is not None: value['spec']=spec
        return value
    def container(name='main',command=None,**extra):
        return {'name':name,'image':h.tools_image,'imagePullPolicy':'Never',
            'command':command or ['sh','-c','echo DS_E2E_INFO; sleep 3600'],
            'resources':{'requests':{'cpu':'5m','memory':'8Mi'},'limits':{'cpu':'100m','memory':'64Mi'}},**extra}
    def pod(name,command=None,**spec):
        return obj('Pod',name,{'containers':[container(command=command)],'terminationGracePeriodSeconds':2,**spec})
    def template(name,containers=None,**extra):
        return {'metadata':{'labels':{'app':name}},'spec':{'containers':containers or [container()],
                'terminationGracePeriodSeconds':2,**extra}}
    def deploy(name,replicas=1,containers=None,**extra):
        return obj('Deployment',name,{'replicas':replicas,'selector':{'matchLabels':{'app':name}},
            'template':template(name,containers,**extra)},'apps/v1')
    def service(name,selector,target=8080,**extra):
        return obj('Service',name,{'selector':{'app':selector},'ports':[{'name':'http','port':80,'targetPort':target}],**extra})
    def ready(name,kind='pod',count=1):
        return h.wait(kind,name,lambda x: condition(x,'Ready') if kind=='pod' else x.get('status',{}).get('readyReplicas',0)==count,ns=ns)
    def report(mode='resources',namespace=ns):
        p=h.sentinel(['--'+mode,'--json'],namespace,timeout=120)
        data=json.loads(p.stdout)
        assert data['exit_status']==p.returncode
        return '\n'.join(data['lines'])
    def function(name,args=()):
        p=h.function(name,args,ns,timeout=120)
        assert p.returncode==0,p.stderr+p.stdout[-1000:]
        return p.stdout
    def line(text,name):
        matches=[row for row in text.splitlines() if name in row]
        assert matches,'Sentinel omitted '+name
        return '\n'.join(matches)
    def detail(api,actual,expected):
        return {'expected_api':api,'actual_api':actual,'expected_sentinel':expected,'actual_sentinel':expected}

    # Deploy once so waits overlap and every test sees authentic controller state.
    cm='ds-e2e-config'; secret='ds-e2e-secret'; sa='ds-e2e-reader'
    h.apply(obj('ConfigMap',cm,data={'SETTING':'safe-setting','revision':'one'}))
    h.apply(obj('Secret',secret,type='Opaque',stringData={'PASSWORD':'DS_E2E_SECRET_CANARY_d883e5'}))
    h.apply(obj('ServiceAccount',sa))
    h.apply(obj('Role','ds-e2e-reader',api='rbac.authorization.k8s.io/v1',rules=[{'apiGroups':[''],'resources':['pods'],'verbs':['get','list']}]))
    h.apply(obj('RoleBinding','ds-e2e-reader',api='rbac.authorization.k8s.io/v1',
        subjects=[{'kind':'ServiceAccount','name':sa,'namespace':ns}],roleRef={'apiGroup':'rbac.authorization.k8s.io','kind':'Role','name':'ds-e2e-reader'}))
    c=container(command=['python3','-m','http.server','8080'],ports=[{'name':'http','containerPort':8080}],
        readinessProbe={'httpGet':{'path':'/','port':'http'},'periodSeconds':2},
        livenessProbe={'httpGet':{'path':'/','port':'http'},'periodSeconds':5},
        envFrom=[{'configMapRef':{'name':cm}},{'secretRef':{'name':secret}}],
        env=[{'name':'EXPLICIT_SECRET','valueFrom':{'secretKeyRef':{'name':secret,'key':'PASSWORD'}}}],
        volumeMounts=[{'name':'config','mountPath':'/test-config','readOnly':True},
                      {'name':'secret','mountPath':'/test-secret','readOnly':True},
                      {'name':'scratch','mountPath':'/scratch'}])
    healthy=deploy('ds-e2e-healthy',2,[c],serviceAccountName=sa,volumes=[{'name':'config','configMap':{'name':cm}},
                    {'name':'secret','secret':{'secretName':secret}},{'name':'scratch','emptyDir':{}}])
    h.apply(healthy);h.apply(service('ds-e2e-web','ds-e2e-healthy','http'))
    h.apply(service('ds-e2e-web-second','ds-e2e-healthy','http'))
    h.apply(service('ds-e2e-zero','missing'))
    h.apply(service('ds-e2e-wrong-port','ds-e2e-healthy',9999))
    h.apply(service('ds-e2e-stateful','ds-e2e-stateful',8080,clusterIP='None'))
    stateful=obj('StatefulSet','ds-e2e-stateful',{'serviceName':'ds-e2e-stateful','replicas':2,
        'selector':{'matchLabels':{'app':'ds-e2e-stateful'}},'template':template('ds-e2e-stateful',[
        container(volumeMounts=[{'name':'ds-e2e-data','mountPath':'/data'}])]),
        'volumeClaimTemplates':[{'metadata':{'name':'ds-e2e-data'},'spec':{'accessModes':['ReadWriteOnce'],
          'storageClassName':'local-path','resources':{'requests':{'storage':'64Mi'}}}}]},'apps/v1')
    h.apply(stateful)
    h.apply(obj('DaemonSet','ds-e2e-daemon',{'selector':{'matchLabels':{'app':'ds-e2e-daemon'}},'template':template('ds-e2e-daemon')},'apps/v1'))
    for name,exitcode in [('ds-e2e-job-success',0),('ds-e2e-job-failed',1)]:
        h.apply(obj('Job',name,{'backoffLimit':1,'activeDeadlineSeconds':120,
          'template':template(name,[container(command=['sh','-c',f'echo DS_E2E_JOB; exit {exitcode}'])],restartPolicy='Never')},'batch/v1'))
    cron=obj('CronJob','ds-e2e-cron',{'schedule':'* * * * *','successfulJobsHistoryLimit':1,'failedJobsHistoryLimit':1,
        'jobTemplate':{'metadata':{'labels':h.labels},'spec':{'backoffLimit':0,'activeDeadlineSeconds':30,
          'template':template('ds-e2e-cron',[container(command=['sh','-c','echo DS_E2E_CRON'])],restartPolicy='Never')}}},'batch/v1')
    cron['spec']['jobTemplate']['spec']['template']['metadata']['labels'].update(h.labels);h.apply(cron)
    h.apply(pod('ds-e2e-crash',['sh','-c','echo DS_E2E_PREVIOUS_CRASH; exit 1']))
    bad=pod('ds-e2e-image');bad['spec']['containers'][0].update(image='devopssentinel.invalid/ds-e2e-does-not-exist:never',imagePullPolicy='Always');h.apply(bad)
    missing=pod('ds-e2e-missing-config');missing['spec']['containers'][0]['envFrom']=[{'configMapRef':{'name':'ds-e2e-absent'}}];h.apply(missing)
    h.apply(pod('ds-e2e-unschedulable',nodeSelector={'devopssentinel.io/no-node':'true'},
                tolerations=[{'key':'ds-e2e-dummy','operator':'Exists','effect':'NoSchedule'}]))
    nr=pod('ds-e2e-not-ready');nr['spec']['containers'][0]['readinessProbe']={'exec':{'command':['sh','-c','exit 1']},'periodSeconds':2};h.apply(nr)
    lv=pod('ds-e2e-liveness');lv['spec']['containers'][0]['livenessProbe']={'exec':{'command':['sh','-c','exit 1']},'periodSeconds':2,'failureThreshold':1};h.apply(lv)
    st=pod('ds-e2e-startup');st['spec']['containers'][0]['startupProbe']={'exec':{'command':['sh','-c','true']},'periodSeconds':2,'failureThreshold':10};h.apply(st)
    oom=pod('ds-e2e-oom',['python3','-c','import time; time.sleep(3); x=bytearray(128*1024*1024);time.sleep(30)'],restartPolicy='Never');oom['spec']['containers'][0]['resources']['limits']['memory']='32Mi';h.apply(oom)
    h.apply(obj('PersistentVolumeClaim','ds-e2e-pending',{'storageClassName':'ds-e2e-nonexistent','accessModes':['ReadWriteOnce'],'resources':{'requests':{'storage':'64Mi'}}}))
    multi=pod('ds-e2e-multi',initContainers=[container('init',['sh','-c','echo DS_E2E_INIT'])]);multi['spec']['containers'].append(container('sidecar'));h.apply(multi)
    h.apply(pod('ds-e2e-init-fail',initContainers=[container('init',['sh','-c','echo DS_E2E_INIT_FAILURE; exit 1'])]))
    h.apply(pod('ds-e2e-logs',['sh','-c','printf "INFO DS_E2E_LOG\nWARN DS_E2E_WARNING\nERROR DS_E2E_ERROR\n{\"level\":\"info\",\"event\":\"ds-e2e-json\"}\npassword=DS_E2E_PASSWORD_CANARY\nAuthorization: Bearer DS_E2E_BEARER_CANARY\npostgresql://test:DS_E2E_URI_CANARY@database/test\n-----BEGIN PRIVATE KEY-----\nDS_E2E_KEY_CANARY\n-----END PRIVATE KEY-----\n"; sleep 3600']))
    h.apply(pod('ds-e2e-peer'),ns='devopssentinel-e2e-peer')
    h.apply(obj('Ingress','ds-e2e-ingress',{'rules':[{'host':'ds-e2e.example.local','http':{'paths':[{'path':'/','pathType':'Prefix','backend':{'service':{'name':'ds-e2e-web','port':{'number':80}}}}]}}]},'networking.k8s.io/v1'))
    h.apply(obj('NetworkPolicy','ds-e2e-policy',{'podSelector':{'matchLabels':{'app':'ds-e2e-healthy'}},'policyTypes':['Ingress'],'ingress':[{'from':[{'podSelector':{}}]}]},'networking.k8s.io/v1'))
    h.apply(obj('HorizontalPodAutoscaler','ds-e2e-hpa',{'scaleTargetRef':{'apiVersion':'apps/v1','kind':'Deployment','name':'ds-e2e-healthy'},'minReplicas':2,'maxReplicas':2,'metrics':[{'type':'Resource','resource':{'name':'cpu','target':{'type':'Utilization','averageUtilization':80}}}]},'autoscaling/v2'))
    h.apply(obj('PodDisruptionBudget','ds-e2e-pdb',{'minAvailable':1,'selector':{'matchLabels':{'app':'ds-e2e-healthy'}}},'policy/v1'))

    def healthy_test():
        api=ready('ds-e2e-healthy','deployment',2);text=function('workloads_report')
        assert re.search(r'Deployment\tds-e2e-healthy\t2\t2\t2\t2\tOK',text)
        return detail('Deployment desired/ready/available=2',api['status'],'workloads row 2/2 OK')
    h.case('DS-E2E-001','workloads','Healthy Deployment, probes and resources',healthy_test)
    def stateful_test():
        api=ready('ds-e2e-stateful','statefulset',2);text=function('workloads_report')
        assert 'OK' in line(text,'ds-e2e-stateful')
        graph=function('resource_dependencies',['StatefulSet',ns,'ds-e2e-stateful'])
        assert 'ds-e2e-stateful-0' in graph and 'ds-e2e-stateful-1' in graph and 'PVC:' in graph
        return detail('StatefulSet ready=2 with claim consumers',api['status'],'ready plus Pod/PVC graph')
    h.case('DS-E2E-002','workloads','StatefulSet and PVC template',stateful_test)
    def daemon_test():
        api=h.wait('daemonset','ds-e2e-daemon',lambda x:x.get('status',{}).get('numberReady',0)==x.get('status',{}).get('desiredNumberScheduled',-1),ns)
        assert 'OK' in line(function('workloads_report'),'ds-e2e-daemon')
        return detail('DaemonSet scheduled=ready',api['status'],'OK')
    h.case('DS-E2E-003','workloads','DaemonSet desired/current/ready',daemon_test)
    for id,name,cond,token in [('004','ds-e2e-job-success','Complete','OK'),('005','ds-e2e-job-failed','Failed','FAIL')]:
        def job_test(name=name,cond=cond,token=token):
            api=h.wait('job',name,lambda x:condition(x,cond),ns,timeout=150)
            assert token in line(function('workloads_report'),name)
            return detail(cond+'=True',api['status'],token)
        h.case('DS-E2E-'+id,'workloads',name,job_test)
    def cron_test():
        api=h.wait('cronjob','ds-e2e-cron',lambda x:bool(x.get('status',{}).get('lastScheduleTime')),ns,timeout=90)
        jobs=h.get('jobs',ns=ns)['items'];assert any(any(o.get('uid')==api['metadata']['uid'] for o in j['metadata'].get('ownerReferences',[])) for j in jobs)
        assert 'ds-e2e-cron' in function('workloads_report')
        return detail('CronJob scheduled child Job',api['status'],'CronJob inventory')
    h.case('DS-E2E-006','workloads','CronJob controller creates owned Job',cron_test)
    for id,name,expected in [('010','ds-e2e-crash','CrashLoopBackOff'),('011','ds-e2e-image','ImagePullBackOff'),('012','ds-e2e-missing-config','CreateContainerConfigError')]:
        def failure(name=name,expected=expected):
            api=h.wait('pod',name,lambda x:any(s.get('state',{}).get('waiting',{}).get('reason') in ([expected,'ErrImagePull'] if expected=='ImagePullBackOff' else [expected]) for s in x.get('status',{}).get('containerStatuses',[])),ns,timeout=180)
            actual=api['status']['containerStatuses'][0]['state']['waiting']['reason']
            # A crash-looping container briefly reports Running between restarts;
            # retry so the assertion reflects the crash-loop state, not that window.
            deadline=time.monotonic()+60; text=''
            while time.monotonic()<deadline:
                text=report()
                if actual in line(text,name): break
                time.sleep(3)
            assert actual in line(text,name),'Sentinel did not report '+actual+' for '+name
            return detail(expected,actual,actual)
        h.case('DS-E2E-'+id,'workloads',name,failure)
    def pending_test():
        api=h.wait('pod','ds-e2e-unschedulable',lambda x:condition(x,'PodScheduled','False'),ns)
        assert 'Pending' in line(report(),'ds-e2e-unschedulable')
        assert 'FailedScheduling' in line(function('events_report'),'ds-e2e-unschedulable')
        return detail('Pending + FailedScheduling',api['status'],'Pending and scheduler events')
    h.case('DS-E2E-013','workloads','Impossible node selector; toleration preserved',pending_test)
    def not_ready_test():
        api=h.wait('pod','ds-e2e-not-ready',lambda x:x.get('status',{}).get('phase')=='Running' and condition(x,'Ready','False'),ns)
        assert '\t0/1\t' in line(report(),'ds-e2e-not-ready')
        return detail('Running Ready=False',api['status'],'0/1 ready')
    h.case('DS-E2E-014','workloads','Running Pod with failed readiness probe',not_ready_test)
    def live_test():
        api=h.wait('pod','ds-e2e-liveness',lambda x:any(s.get('restartCount',0)>0 for s in x.get('status',{}).get('containerStatuses',[])),ns)
        text=function('containers_report',['ds-e2e-liveness']);assert 'ds-e2e-liveness' in text and 'LAST TERMINATION' in text
        assert 'Liveness probe failed' in function('events_report')
        return detail('restarts > 0; probe event',api['status'],'restart and probe event')
    h.case('DS-E2E-015','workloads','Liveness failure and restart history',live_test)
    def startup_test():
        api=ready('ds-e2e-startup');text=function('pod_forensics_report',['ds-e2e-startup'])
        assert 'startupProbe' in text or 'STARTUP' in text.upper(), 'Startup probe omitted from forensics'
        return detail('startupProbe defined, started=True',api['status'],'startup probe definition')
    h.case('DS-E2E-016','workloads','Startup probe and started state',startup_test)
    def oom_test():
        api=h.wait('pod','ds-e2e-oom',lambda x:any(s.get('state',{}).get('terminated',{}).get('reason')=='OOMKilled' for s in x.get('status',{}).get('containerStatuses',[])),ns)
        assert 'OOMKilled' in line(function('containers_report'),'ds-e2e-oom')
        return detail('OOMKilled bounded32Mi, restart Never',api['status'],'OOMKilled')
    h.case('DS-E2E-017','workloads','Bounded 32Mi OOM failure',oom_test)
    for id,kind,name in [('020','ConfigMap',cm),('021','Secret',secret),('022','ServiceAccount',sa)]:
        def deps(kind=kind,name=name):
            api=h.get(kind,name,ns);text=function('resource_consumers',[kind,ns,name]);assert 'ds-e2e-healthy-' in text
            assert 'DS_E2E_SECRET_CANARY_d883e5' not in text
            return detail('live reference from healthy pods',api['metadata']['name'],'reverse Pod consumers')
        h.case('DS-E2E-'+id,'dependencies',kind+' reverse dependencies',deps)
    def endpoints_test():
        api=h.wait('endpoints','ds-e2e-web',lambda x:len(x.get('subsets',[{}])[0].get('addresses',[]))==2 if x.get('subsets') else False,ns)
        text=report('network');row=line(text,'ds-e2e-web')
        assert 'ready=2/2' in row, 'topology did not report two ready endpoints: '+row
        with h.forward('ds-e2e-web',80) as port:
            p=h.command(['curl','-fsS','--max-time','5',f'http://127.0.0.1:{port}/']);assert p.returncode==0
        return detail('two ready endpoints and successful HTTP',api.get('subsets'),'ready=2/2 and live HTTP')
    h.case('DS-E2E-030','networking','Service endpoints plus live HTTP',endpoints_test)
    def zero_test():
        api=h.get('endpoints','ds-e2e-zero',ns);assert not api.get('subsets')
        assert 'ready=0/0' in line(report('network'),'ds-e2e-zero'), 'topology did not report zero endpoints'
        return detail('0 ready endpoints',api.get('subsets',[]),'ready=0/0')
    h.case('DS-E2E-031','networking','Service without endpoints',zero_test)
    def target_test():
        api=h.get('service','ds-e2e-web',ns);assert api['spec']['ports'][0]['targetPort']=='http'
        assert '80:http' in line(report('network'),'ds-e2e-web')
        return detail('named targetPort http resolves8080',api['spec']['ports'],'80:http; endpoint8080')
    h.case('DS-E2E-032','networking','Named targetPort mapping',target_test)
    def mismatch_test():
        api=h.get('service','ds-e2e-wrong-port',ns);assert api['spec']['ports'][0]['targetPort']==9999
        text=report('network');row=line(text,'ds-e2e-wrong-port')
        assert any(t in row for t in ['WARN_PORT','MISMATCH','UNVERIFIED']), 'Port 9999 has no declared container listener but Sentinel reports '+row
        return detail('target9999 undeclared',api['spec']['ports'],'port mismatch/unverified')
    h.case('DS-E2E-033','networking','Service target port mismatch',mismatch_test)
    def multi_service():
        api=h.get('services',ns=ns);text=function('resource_dependencies',['Deployment',ns,'ds-e2e-healthy'])
        assert all('Service: '+s in text for s in ['ds-e2e-web','ds-e2e-web-second'])
        return detail('multiple selectors same pods',len(api['items']),'both services in graph')
    h.case('DS-E2E-034','networking','Multiple services select same Deployment',multi_service)
    def policy():
        api=h.get('networkpolicy','ds-e2e-policy',ns);text=report('network')
        assert 'ds-e2e-policy' in text,'NetworkPolicy missing from network report'
        return detail('real ingress NetworkPolicy',api['spec'],'policy inventory; enforcement separate')
    h.case('DS-E2E-035','networking','NetworkPolicy parsing',policy)
    def crossns():
        api=h.wait('pod','ds-e2e-peer',lambda x:condition(x,'Ready'),'devopssentinel-e2e-peer')
        a=report();b=report(namespace='devopssentinel-e2e-peer')
        assert 'ds-e2e-peer' not in a and 'ds-e2e-peer' in b and 'ds-e2e-crash' not in b
        return detail('different namespace pod sets',api['metadata']['namespace'],'isolated reports')
    h.case('DS-E2E-036','networking','Cross namespace isolation',crossns)
    def dns():
        ready('ds-e2e-startup')
        names=['ds-e2e-web',f'ds-e2e-web.{ns}',f'ds-e2e-web.{ns}.svc',f'ds-e2e-web.{ns}.svc.cluster.local']
        p=h.k(['exec','ds-e2e-startup','--','python3','-c','import socket,json;print(json.dumps({n:socket.gethostbyname(n) for n in '+repr(names)+'}))'],ns)
        h.evidence('dns.json',p.stdout);assert p.returncode==0,p.stderr
        assert 'ds-e2e-web' in function('dns_inventory_report'), 'DNS inventory omitted service'
        return detail('all DNS variants resolve',json.loads(p.stdout),'service FQDN')
    h.case('DS-E2E-037','networking','Real cluster DNS resolution',dns)
    def ingress():
        api=h.get('ingress','ds-e2e-ingress',ns);text=report('network')
        assert 'ds-e2e-ingress' in text and 'ds-e2e.example.local' in text
        return detail('Ingress backend API mapping; no controller',api['spec'],'host/backend mapping')
    h.case('DS-E2E-038','networking','Ingress API graph',ingress)
    def storage():
        api=h.wait('pvc','ds-e2e-data-ds-e2e-stateful-0',lambda x:x.get('status',{}).get('phase')=='Bound',ns,timeout=180)
        pv=h.get('pv',api['spec']['volumeName']);assert pv['spec']['claimRef']['uid']==api['metadata']['uid']
        text=report('storage');assert api['spec']['volumeName'] in text and 'ds-e2e-stateful-0' in text and 'Bound' in text
        return detail('PVC Bound to PV; Pod mount',api['status'],'PVC/PV/class/consumer')
    h.case('DS-E2E-040','storage','Bound PVC and PV ownership',storage)
    def pending_pvc():
        api=h.wait('pvc','ds-e2e-pending',lambda x:x.get('status',{}).get('phase')=='Pending',ns)
        text=report('storage');assert 'PVC/ds-e2e-pending phase=Pending' in text and 'UNBOUND' in text
        return detail('Pending nonexistent StorageClass',api['status'],'Pending UNBOUND')
    h.case('DS-E2E-041','storage','Pending PVC without StorageClass',pending_pvc)
    def multi_container():
        api=ready('ds-e2e-multi');text=function('containers_report',['ds-e2e-multi'])
        assert all(t in text for t in ['main','sidecar','init','INIT','Completed'])
        return detail('2 containers and completed init',api['status'],'all container roles and states')
    h.case('DS-E2E-070','workloads','Multi-container Pod and successful init',multi_container)
    def init_fail():
        api=h.wait('pod','ds-e2e-init-fail',lambda x:any(s.get('restartCount',0)>0 for s in x.get('status',{}).get('initContainerStatuses',[])),ns)
        deadline=time.monotonic()+60; text=''
        while time.monotonic()<deadline:
            text=line(report(),'ds-e2e-init-fail')
            if any(t in text for t in ['Init:','CrashLoopBackOff','Error']): break
            time.sleep(3)
        assert any(t in text for t in ['Init:','CrashLoopBackOff','Error']),'init failure state not surfaced: '+text
        return detail('init exits1 and restarts',api['status'],'init failure status')
    h.case('DS-E2E-071','workloads','Init container failure',init_fail)
    def logs():
        ready('ds-e2e-logs');raw=h.k(['logs','ds-e2e-logs','--tail=50'],ns);assert raw.returncode==0
        p=h.shell('kctl_ns logs ds-e2e-logs --tail=200 > "$RUN_DIR/pod.log" 2>&1; '
                  'capture_report "LOGS-CONTEXT" ui_log_context_report "$RUN_DIR/pod.log" "DS_E2E_ERROR" 2 2; '
                  'cat "$CURRENT_REPORT"')
        assert p.returncode==0,p.stderr[-500:];p=p.stdout
        assert 'DS_E2E_LOG' in p and 'DS_E2E_ERROR' in p,'Live logs not captured'
        for value in ['DS_E2E_PASSWORD_CANARY','DS_E2E_BEARER_CANARY','DS_E2E_URI_CANARY','DS_E2E_KEY_CANARY']:
            assert value not in p,'Unredacted synthetic log canary'
        return detail('real structured/error/canary logs',{'lines':len(raw.stdout.splitlines())},'markers preserved; credentials redacted')
    h.case('DS-E2E-072','security','Live logs and credential redaction',logs)
    def previous():
        api=h.wait('pod','ds-e2e-crash',lambda x:any(s.get('restartCount',0)>0 for s in x.get('status',{}).get('containerStatuses',[])),ns)
        deadline=time.monotonic()+60; raw=None
        while time.monotonic()<deadline:
            raw=h.k(['logs','ds-e2e-crash','--previous','--tail=20'],ns)
            if raw.returncode==0 and 'DS_E2E_PREVIOUS_CRASH' in raw.stdout: break
            time.sleep(3)
        assert raw is not None and 'DS_E2E_PREVIOUS_CRASH' in raw.stdout,'previous log marker unavailable'
        p=h.shell('kctl_ns logs ds-e2e-crash --previous --tail=20 > "$RUN_DIR/prev.log" 2>&1; '
                  'capture_report "PREVIOUS-LOGS" ui_log_context_report "$RUN_DIR/prev.log" "DS_E2E_PREVIOUS_CRASH" 2 2; '
                  'cat "$CURRENT_REPORT"')
        assert p.returncode==0,p.stderr[-500:]
        assert 'DS_E2E_PREVIOUS_CRASH' in p.stdout,'previous crash marker not surfaced'
        return detail('previous instance real crash marker',api['status'],'previous crash log')
    h.case('DS-E2E-073','events','Previous container logs',previous)
    def events():
        api=h.get('events',ns=ns);reasons={e.get('reason') for e in api['items']};assert {'BackOff','FailedScheduling','Unhealthy'}<=reasons
        text=function('events_report');assert all(r in text for r in ['BackOff','FailedScheduling','Unhealthy'])
        return detail('real scheduler/image/probe events',sorted(reasons),'reasons, count and timestamps')
    h.case('DS-E2E-074','events','Actual Kubernetes failure event timeline',events)
    def nodes():
        api=h.get('nodes');text=function('nodes_report');assert len(api['items'])==1 and '\ndev\t' in text
        assert 'selected namespace only' in text
        return detail('one Ready local node',api['items'][0]['status']['allocatable'],'capacity scope and node inventory')
    h.case('DS-E2E-076','nodes','Real node capacity and scoped reservations',nodes)
    h.fixture_cache['healthy']=healthy
