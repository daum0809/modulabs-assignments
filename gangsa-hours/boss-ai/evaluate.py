"""Explicit --live opt-in: 18 paid calls. No fabricated metrics."""
import argparse, csv, json, random
from pathlib import Path
from datetime import datetime, timezone
from server import diagnose, MODEL, VERSION
p=argparse.ArgumentParser();p.add_argument('--live',action='store_true');args=p.parse_args()
if not args.live: p.exit(message='미실행. 실제 API 비교는 --live가 필요합니다. 18회 호출 비용이 발생합니다.\n')
cases=json.loads(Path(__file__).with_name('cases.json').read_text())
out=Path(__file__).parent/'results'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out.mkdir(parents=True)
records=[];blind=[];mapping={}
for case in cases:
    for condition in ('questions','report','baseline'):
        problem=case['problem'] if condition=='questions' else case['problem']+'\n동일 추가 정보: '+case['followup']
        row={'case_id':case['id'],'condition':condition,'problem':problem,'model':MODEL,'prompt_version':VERSION}
        try: row.update(diagnose({'stage':condition,'problem':problem,'answers':[]}));row['success']=True
        except Exception as e: row.update(success=False,error=str(e))
        records.append(row)
        # Checkpoint after every call, preserve errors as failures.
        (out/'raw.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))
        if condition!='questions' and row['success']: blind.append(row)
random.Random(42).shuffle(blind)
for i,row in enumerate(blind,1):
    label=f'R{i:02}';mapping[label]={'case_id':row['case_id'],'condition':row['condition']}
    (out/(label+'.json')).write_text(json.dumps({'case_id':row['case_id'],'problem':row['problem'],'result':row['result']},ensure_ascii=False,indent=2))
with (out/'review.csv').open('w',newline='',encoding='utf-8-sig') as f:
    writer=csv.writer(f);writer.writerow(['blind_id','rater','facts_0to2','uncertainty_0to2','hypotheses_0to2','action_0to2','constraints_0to2','unsupported_numbers','notes'])
    for label in mapping: writer.writerow([label]+['']*8)
(out/'mapping.json').write_text(json.dumps(mapping,ensure_ascii=False,indent=2))
(out/'summary.json').write_text(json.dumps({'model':MODEL,'prompt_version':VERSION,'calls':len(records),'successes':sum(x['success'] for x in records),'quality':'unrated','usage_note':'raw.json contains token usage; latency measures API round trip, not human completion time.'},indent=2))
print('완료:',out,'— 품질은 review.csv에서 별도 평가하세요.')
