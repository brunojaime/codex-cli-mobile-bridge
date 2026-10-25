"""Summarize completed experiments without pooling unrelated datasets."""
import json
from pathlib import Path
import argparse


def read_run(root,name):
    p=root/name
    return {'meta':json.loads((p/'run.json').read_text()),
            'metrics':json.loads((p/'metrics.json').read_text()),
            'rows':[json.loads(x) for x in (p/'predictions.jsonl').read_text().splitlines()]}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,required=True)
    args=parser.parse_args();root=args.root
    names=['openrouter-01','challenge-openrouter-01','catalog-openrouter-01']
    runs={n:read_run(root,n) for n in names}
    if any(r['meta']['status']!='completed' for r in runs.values()):
        raise SystemExit('Se requieren corridas completas para este resumen.')
    main_run=runs['openrouter-01']
    originals=[r for r in main_run['rows'] if r['variant']=='original' and r['repeat']==0]
    all_rows=[r for run in runs.values() for r in run['rows']]
    base=read_run(root,'baseline');laya=read_run(root,'laya')
    if len({r['meta']['dataset_sha256'] for r in [main_run,base,laya]})!=1:
        raise SystemExit('La comparación principal requiere el mismo corpus.')
    paired={}
    for name,ref in [('baseline',base),('laya',laya)]:
        lookup={r['id']:r for r in ref['rows'] if r['variant']=='original' and r['repeat']==0}
        pairs=[(r,lookup[r['id']]) for r in originals]
        paired[name]={'jev_correct_ref_wrong':sum(a['correct'] and not b['correct'] for a,b in pairs),
                      'jev_wrong_ref_correct':sum(not a['correct'] and b['correct'] for a,b in pairs),
                      'both_correct':sum(a['correct'] and b['correct'] for a,b in pairs),
                      'both_wrong':sum(not a['correct'] and not b['correct'] for a,b in pairs)}
    critical=[r for r in all_rows if r.get('critical_accept_label')]
    unknown=[r for r in originals if r['expected'] in ('unknown','unclear')]
    result={'total_api_requests':len(all_rows),'total_reported_cost_usd':sum(r['usage']['cost'] for r in all_rows),
            'cost_source':'Sum of usage.cost in these three runs; excludes previous smoke calls and top-up fees.',
            'resolved_models':sorted({r['resolved_model'] for r in all_rows}),
            'main_original_cases':len(originals),'main_original_correct':sum(r['correct'] for r in originals),
            'paired_comparison_main':paired,
            'main_uncertain_cases':len(unknown),'main_uncertain_correct':sum(r['correct'] for r in unknown),
            'observed_false_accepts_all_variants':sum(r['predicted']==r['critical_accept_label'] and not r['correct'] for r in critical),
            'main_errors':[{'id':r['id'],'expected':r['expected'],'predicted':r['predicted'],'probability_of_selected_label':r.get('top_probability')} for r in originals if not r['correct']],
            'subexperiments':{name:{'requests':r['metrics']['attempts'],'cost_usd':r['metrics']['reported_cost_usd'],'dataset_sha256':r['meta']['dataset_sha256']} for name,r in runs.items()},
            'limitations':['Authored exploratory labels, not independent human review.','Adaptive challenge is not a held-out confirmation set.',
                          'Two long challenge inputs are derived from other challenge cases.','Catalog queries are authored; catalog identifiers are real local audit data.',
                          'No human time-saving measurement. Zero observed false acceptance does not establish a zero failure rate.',
                          'Repeated calls can share provider caching; these are end-to-end observed responses.']}
    (root/'analisis-comparativo.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
