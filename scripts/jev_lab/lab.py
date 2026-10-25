#!/usr/bin/env python3
"""Isolated Jev evaluation client. Python stdlib; never mutates project state.

Network requests only happen with `run --provider openrouter|cloudflare|typesafe`.
Credentials are only read from the environment or an explicitly selected file.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import statistics
import sys
import time
from datetime import datetime, timezone
import urllib.error
import urllib.request

HERE = Path(__file__).resolve().parent
DEFAULT_ENV = Path.home()/'.config/nienfos-jev/credentials.env'
MODELS = {'openrouter': 'typesafe/jev-1.13', 'cloudflare': 'typesafe/jev', 'typesafe': 'jev-1.13.0'}
KEYS = {'openrouter': ['OPENROUTER_API_KEY'], 'cloudflare': ['CLOUDFLARE_API_TOKEN', 'CLOUDFLARE_ACCOUNT_ID'], 'typesafe': ['TYPESAFE_API_KEY']}
VARIANTS = ('original', 'reversed', 'distractor')
PRICE_PER_M = 0.042  # Published price observed 2026-09-27; estimate, not an invoice.


def dumps(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n')


def load_env(path):
    if not path.is_file():
        return
    if path.stat().st_mode & 0o077:
        raise ValueError('El archivo de credenciales requiere permisos 600.')
    allowed = {key for keys in KEYS.values() for key in keys} | {'CLOUDFLARE_AI_GATEWAY_ID'}
    for line in path.read_text().splitlines():
        line = line.strip().removeprefix('export ')
        if not line or line.startswith('#'):
            continue
        key, sep, value = line.partition('=')
        if sep and key.strip() in allowed:
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            os.environ.setdefault(key.strip(), value)


def load_cases(path):
    dataset = json.loads(path.read_text())
    cases = dataset['cases']
    ids = set()
    for case in cases:
        if case['id'] in ids:
            raise ValueError('IDs duplicados en el corpus.')
        ids.add(case['id'])
        q = case['question']
        if q['type'] == 'choice' and case['expected'] not in q['criteria']:
            raise ValueError('Etiqueta esperada fuera de las opciones.')
        if q['type'] not in ('choice', 'noul', 'score'):
            raise ValueError('Primitiva desconocida.')
    return dataset


def variant(case, name):
    c = copy.deepcopy(case)
    if name == 'reversed' and c['question']['type'] == 'choice':
        c['question']['criteria'] = dict(reversed(list(c['question']['criteria'].items())))
    elif name == 'distractor':
        c['state'] = {'datos_relevantes': c['state'], 'nota_ajena_al_caso': 'En otro proyecto se cambió el color del logo. No pertenece a este pedido ni a sus evidencias.'}
    return c


def payload(case):
    # Expected labels and reviewer metadata must never enter the request.
    return {'state': case['state'], 'questions': {'decision': case['question']}}


def request_spec(provider, model, data):
    missing = [k for k in KEYS[provider] if not os.environ.get(k)]
    if missing:
        raise ValueError('Falta configurar: '+', '.join(missing))
    headers = {'Content-Type': 'application/json', 'User-Agent': 'Nienfos-Jev-Lab/1'}
    if provider == 'cloudflare':
        account = os.environ['CLOUDFLARE_ACCOUNT_ID']
        if not re.fullmatch(r'[a-fA-F0-9]{32}', account):
            raise ValueError('CLOUDFLARE_ACCOUNT_ID debe ser el ID de cuenta de 32 caracteres hexadecimales.')
        url = 'https://api.cloudflare.com/client/v4/accounts/'+account+'/ai/run'
        headers.update({'Authorization': 'Bearer '+os.environ['CLOUDFLARE_API_TOKEN'],
                        'cf-aig-skip-cache': 'true', 'cf-aig-collect-log': 'false', 'cf-aig-max-attempts': '1'})
        if os.environ.get('CLOUDFLARE_AI_GATEWAY_ID'):
            headers['cf-aig-gateway-id'] = os.environ['CLOUDFLARE_AI_GATEWAY_ID']
        body = {'model': model, 'input': data}
    else:
        url = 'https://openrouter.ai/api/v1/systemone' if provider == 'openrouter' else 'https://api.typesafe.ai/v1/systemone'
        headers['Authorization'] = 'Bearer '+os.environ[KEYS[provider][0]]
        body = {'model': model, **data}
    return url, headers, body


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class RemoteFailure(Exception):
    def __init__(self, status=None, codes=None, reason='provider_error'):
        self.record = {'http_status': status, 'error_codes': codes or [], 'reason': reason}


def remote_call(provider, model, data, timeout):
    url, headers, body = request_spec(provider, model, data)
    req = urllib.request.Request(url, data=dumps(body).encode(), headers=headers, method='POST')
    opener = urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(req, timeout=timeout) as response:
            raw = json.loads(response.read(2_000_000))
    except urllib.error.HTTPError as exc:
        try:
            error = json.loads(exc.read(100_000))
            codes = [e.get('code') for e in error.get('errors', []) if isinstance(e, dict)]
        except (ValueError, AttributeError):
            codes = []
        # Never persist response text; providers can echo credentials or request bodies.
        raise RemoteFailure(exc.code, codes) from None
    except (OSError, ValueError, urllib.error.URLError):
        raise RemoteFailure(reason='transport_or_json_error') from None
    if not isinstance(raw, dict) or raw.get('success') is False:
        raise RemoteFailure(reason='unsuccessful_envelope')
    result = raw.get('result', raw)
    if not isinstance(result, dict):
        raise RemoteFailure(reason='invalid_envelope')
    return result


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def normalize(result, question):
    try:
        a = result['answers']['decision']
        if a.get('type') != question['type']:
            raise ValueError('type')
        typ = question['type']
        if typ == 'choice':
            p = a['probabilities']
            if set(p) != set(question['criteria']) or any(not number(v) or not 0 <= v <= 1 for v in p.values()) or abs(sum(p.values())-1)>0.02:
                raise ValueError('probabilities')
            if a['choice'] not in p:
                raise ValueError('choice')
            confidence = a.get('confidence')
            if confidence is not None and (not number(confidence) or not 0 <= confidence <= 1):
                raise ValueError('confidence')
            return {'predicted': a['choice'], 'probabilities': p, 'confidence': confidence, 'top_probability': p[a['choice']]}
        if typ == 'noul':
            p = a['noul']
            if not number(p) or not 0 <= p <= 1:
                raise ValueError('noul')
            return {'predicted': p >= 0.5, 'noul': p, 'top_probability': max(p, 1-p)}
        score = a['score']
        if not number(score) or not 0 <= score <= len(question['criteria'])-1:
            raise ValueError('score')
        return {'predicted': score, 'score': score}
    except (KeyError, TypeError, ValueError, AttributeError):
        raise RemoteFailure(reason='invalid_answer_schema') from None


def baseline(case):
    q, family = case['question'], case['family']
    if q['type'] == 'noul':
        return {'answers': {'decision': {'type': 'noul', 'noul': 0.5}}}
    if q['type'] == 'score':
        return {'answers': {'decision': {'type': 'score', 'score': 1.0}}}
    defaults = {'closure':'missing', 'scope':'unclear', 'coherence':'unknown', 'feedback':'unclear', 'regression':'unknown'}
    if family == 'retrieval':
        terms = set(re.findall(r'\w+', dumps(case['state']).lower()))
        # Ties use label sort so reordering criteria cannot change this baseline.
        prediction = max(sorted(q['criteria']), key=lambda k: len(terms & set(re.findall(r'\w+', q['criteria'][k].lower()))))
    else:
        prediction = defaults[family]
    return {'answers': {'decision': {'type':'choice','choice':prediction,
            'probabilities': {k: float(k==prediction) for k in q['criteria']}}}}


def percentile(values, p):
    return sorted(values)[max(0, math.ceil(p*len(values))-1)] if values else None


def wilson(correct, n):
    if not n:
        return None
    z=1.96; rate=correct/n; d=1+z*z/n
    mid=(rate+z*z/(2*n))/d; radius=z*math.sqrt(rate*(1-rate)/n+z*z/(4*n*n))/d
    return [round(mid-radius,4), round(mid+radius,4)]


def summarize(rows):
    valid = [r for r in rows if 'predicted' in r]
    # Only original, first-repeat rows are counted as distinct cases.
    primary = [r for r in valid if r['variant']=='original' and r['repeat']==0]
    families = {}
    for family in sorted({r['family'] for r in primary}):
        rs=[r for r in primary if r['family']==family]; n=len(rs)
        entry={'cases':n, 'correct':sum(r['correct'] for r in rs)}
        if family=='score':
            entry['mae']=statistics.mean(abs(r['predicted']-r['expected']) for r in rs)
            entry['correct_definition']='Absolute score error <= 0.5 (exploratory tolerance).'
        entry['accuracy']=entry['correct']/n
        entry['wilson_95']=wilson(entry['correct'],n)
        if family!='score':
            confusion={}
            for r in rs:
                actual=str(r['expected']); predicted=str(r['predicted'])
                confusion.setdefault(actual,{})[predicted]=confusion.get(actual,{}).get(predicted,0)+1
            entry['confusion']=confusion
        critical=[r for r in rs if r.get('critical_accept_label') is not None]
        entry['false_accepts']=sum(r['predicted']==r['critical_accept_label'] and not r['correct'] for r in critical)
        probability=[r for r in rs if r.get('top_probability') is not None]
        if probability:
            entry['threshold_exploration']={}
            for t in (0.8,0.9,0.95):
                selected=[r for r in probability if r['top_probability']>=t]
                entry['threshold_exploration'][str(t)]={'coverage':len(selected)/n,'selected':len(selected),'errors':sum(not r['correct'] for r in selected)}
        briers=[]
        for r in rs:
            if 'probabilities' in r:
                briers.append(sum((p-float(k==r['expected']))**2 for k,p in r['probabilities'].items()))
            elif 'noul' in r:
                briers.append((r['noul']-float(r['expected']))**2)
        if briers:
            entry['brier_score']=statistics.mean(briers)
        families[family]=entry
    by_key={(r['id'],r['variant'],r['repeat']):r for r in valid}
    robustness={}
    for v in ('reversed','distractor','repeat'):
        pairs=[]
        for base in primary:
            key=(base['id'],'original',1) if v=='repeat' else (base['id'],v,0)
            other=by_key.get(key)
            if other:
                pairs.append((base,other))
        robustness[v]={'paired_cases':len(pairs),'changed':sum(a['predicted']!=b['predicted'] for a,b in pairs),
                       'accuracy_losses':sum(a['correct'] and not b['correct'] for a,b in pairs)}
    times=[r['latency_ms'] for r in valid]
    billed=[r['usage']['cost'] for r in rows if number(r.get('usage',{}).get('cost'))]
    estimated=[r['estimated_cost_usd'] for r in rows if number(r.get('estimated_cost_usd'))]
    return dict(attempts=len(rows),valid_responses=len(valid),errors=len(rows)-len(valid),families=families,
                robustness=robustness,latency_p50_ms=statistics.median(times) if times else None,
                latency_p95_ms=percentile(times,.95),reported_cost_usd=sum(billed) if billed else None,
                responses_with_reported_cost=len(billed),estimated_success_cost_usd=sum(estimated) if estimated else None,
                limitations=['Synthetic labels authored without independent review.','Variants are correlated and not additional independent cases.',
                            'Probability thresholds are exploratory, not calibrated production gates.',
                            'No measured human time savings. Unknown-cost errors are not counted as free.'])


def execute(args, dataset):
    if args.out.exists():
        raise ValueError('El directorio de salida ya existe; elegí uno nuevo para preservar resultados.')
    selected=[c for c in dataset['cases'] if not args.family or c['family'] in args.family]
    jobs=[(variant(c,v),v,r) for r in range(args.repeats) for c in selected for v in args.variants
          if v!='reversed' or c['question']['type']=='choice']
    jobs=jobs[:args.max_requests]
    model=args.model or MODELS.get(args.provider,args.provider)
    if args.provider in KEYS:
        request_spec(args.provider,model,payload(jobs[0][0]))
    router=None; load_seconds=None
    if args.provider=='laya':
        if args.laya_site:
            sys.path.insert(0,str(args.laya_site))
        if not args.laya_snapshot or not args.laya_snapshot.is_dir():
            raise ValueError('Laya requiere --laya-snapshot con los pesos locales fijados.')
        os.environ['HF_HUB_OFFLINE']='1'; os.environ['TRANSFORMERS_OFFLINE']='1'
        import torch
        from laya import Router
        torch.set_num_threads(2); torch.set_num_interop_threads(1)
        t=time.perf_counter()
        router=Router(device='cpu',max_loaded=1,default='multilingual',models={'multilingual':(str(args.laya_snapshot),'multilingual')})
        router.preload(['multilingual']); load_seconds=time.perf_counter()-t
    args.out.mkdir(parents=True)
    run={'created_at':datetime.now(timezone.utc).isoformat(),'provider':args.provider,'requested_model':model,
         'dataset_sha256':hashlib.sha256(args.cases.read_bytes()).hexdigest(),'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
         'planned_requests':len(jobs),'budget_estimate_usd':args.budget_usd,'price_per_million_assumption':PRICE_PER_M,
         'load_seconds':load_seconds,'model_revision':args.laya_snapshot.name if args.laya_snapshot else None,
         'status':'running','label_review':dataset['label_review']}
    save(args.out/'run.json',run)
    rows=[]; spent=0.0
    try:
        for case,v,r in jobs:
            data=payload(case)
            # Conservative byte-count planning allowance, not a provider-enforced billing cap.
            allowance=(len(dumps(data).encode())+2048)*PRICE_PER_M/1_000_000
            if args.provider in KEYS and spent+allowance>args.budget_usd:
                run['status']='budget_estimate_stop'; break
            t=time.perf_counter()
            row={k:case[k] for k in ('id','family','expected')}
            row.update(variant=v,repeat=r,critical_accept_label=case.get('critical_accept_label'),
                       request_sha256=hashlib.sha256(dumps(data).encode()).hexdigest())
            try:
                if args.provider=='baseline':
                    result=baseline(case)
                elif router:
                    result=router.predict(data['state'],data['questions'],model='multilingual')
                else:
                    result=remote_call(args.provider,model,data,args.timeout)
                row.update(normalize(result,case['question']))
                row['correct']=abs(row['predicted']-case['expected'])<=.5 if case['question']['type']=='score' else row['predicted']==case['expected']
                # Allowlist response metadata; never persist arbitrary response text.
                row['resolved_model']=result.get('model',model)
                usage=result.get('usage') or {}
                row['usage']={k:usage[k] for k in ('input_tokens','output_tokens','cost') if number(usage.get(k)) and usage[k]>=0}
                tokens=row['usage'].get('input_tokens')
                row['estimated_cost_usd']=tokens*PRICE_PER_M/1_000_000 if tokens is not None and args.provider in KEYS else None
                spent+=max(allowance,row['usage'].get('cost',0),row['estimated_cost_usd'] or 0)
            except RemoteFailure as exc:
                row['error']=exc.record
                spent+=allowance
            row['latency_ms']=round((time.perf_counter()-t)*1000,3)
            rows.append(row)
            with (args.out/'predictions.jsonl').open('a') as f:
                f.write(dumps(row)+'\n')
            print(f"{len(rows)}/{len(jobs)} {case['id']} {v}: "+str(row.get('predicted',row.get('error'))),flush=True)
            if 'error' in row:
                # Fail fast; no repeated authentication charges or invisible retries.
                run['status']='stopped_on_error'; break
        else:
            run['status']='completed'
    except KeyboardInterrupt:
        run['status']='interrupted'
    finally:
        if run['status']=='running':
            run['status']='aborted'
        run['finished_at']=datetime.now(timezone.utc).isoformat()
        save(args.out/'run.json',run)
        save(args.out/'metrics.json',summarize(rows))
    return 0 if run['status']=='completed' else 2


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['doctor','plan','run'])
    p.add_argument('--provider',choices=[*KEYS,'baseline','laya'],default='openrouter')
    p.add_argument('--cases',type=Path,default=HERE/'cases.json')
    p.add_argument('--env-file',type=Path,default=DEFAULT_ENV)
    p.add_argument('--model')
    p.add_argument('--family',action='append')
    p.add_argument('--variants',nargs='+',choices=VARIANTS,default=['original','reversed','distractor'])
    p.add_argument('--repeats',type=int,default=1)
    p.add_argument('--max-requests',type=int,default=250)
    p.add_argument('--budget-usd',type=float,default=.25)
    p.add_argument('--timeout',type=float,default=30)
    p.add_argument('--out',type=Path)
    p.add_argument('--laya-site',type=Path)
    p.add_argument('--laya-snapshot',type=Path)
    args=p.parse_args()
    if args.repeats<1 or args.max_requests<1 or not math.isfinite(args.budget_usd) or args.budget_usd<=0 or not 0<args.timeout<=60:
        p.error('Límites positivos; timeout máximo 60 segundos.')
    try:
        load_env(args.env_file)
        dataset=load_cases(args.cases)
        if args.family and set(args.family)-{c['family'] for c in dataset['cases']}:
            p.error('Familia desconocida.')
        if args.command=='doctor':
            print(dumps({'python':sys.version.split()[0],'cases':len(dataset['cases']),
                         'credentials':{provider:{k:bool(os.environ.get(k)) for k in keys} for provider,keys in KEYS.items()},
                         'note':'Presence only; does not verify authorization or billing.'}))
            return 0
        if args.command=='plan':
            cases=[c for c in dataset['cases'] if not args.family or c['family'] in args.family]
            jobs=[variant(c,v) for _ in range(args.repeats) for c in cases for v in args.variants if v!='reversed' or c['question']['type']=='choice'][:args.max_requests]
            print(dumps({'unique_cases':len(cases),'requests':len(jobs),'families':{f:sum(c['family']==f for c in cases) for f in sorted({c['family'] for c in cases})},
                         'planning_allowance_usd':sum((len(dumps(payload(c)).encode())+2048)*PRICE_PER_M/1_000_000 for c in jobs),
                         'note':'Estimated byte-count allowance; not measured consumption or a guaranteed billing limit.'}))
            return 0
        if not args.out:
            p.error('run requiere --out con un directorio nuevo.')
        return execute(args,dataset)
    except ValueError as exc:
        print(str(exc),file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
