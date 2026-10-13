const SAMPLE=`date,product,category,channel,ad_spend,visits,add_to_cart,purchases,revenue
2026-08-01,원피스A,여성의류,Instagram,900000,3500,420,126,7560000
2026-08-01,티셔츠B,여성의류,Naver,700000,2800,392,118,5900000
2026-08-01,가방C,잡화,Google,900000,3700,388,116,8740000
2026-09-01,원피스A,여성의류,Instagram,1000000,4000,400,80,6400000
2026-09-01,티셔츠B,여성의류,Naver,800000,3000,420,126,6300000
2026-09-01,가방C,잡화,Google,1200000,5000,300,60,5400000`;
const required=["date","product","channel","ad_spend","visits","purchases","revenue"];
const num=["ad_spend","visits","add_to_cart","purchases","revenue"];
let current=null;
function parseCSV(text){const lines=text.trim().split(/\r?\n/).filter(Boolean);if(lines.length<2)throw Error("데이터 행이 없습니다.");const h=lines[0].split(",").map(x=>x.trim());const missing=required.filter(x=>!h.includes(x));if(missing.length)throw Error("필수 컬럼 누락: "+missing.join(", "));return lines.slice(1).map((l,i)=>{const v=l.split(",");const o={};h.forEach((k,j)=>o[k]=v[j]?.trim()??"");num.forEach(k=>{if(o[k]!==undefined){o[k]=Number(o[k]);if(!Number.isFinite(o[k])||o[k]<0)throw Error((i+2)+"행 "+k+" 값이 올바르지 않습니다.");}});return o;});}
function sum(a,k){return a.reduce((s,r)=>s+(Number(r[k])||0),0)}
function metrics(a){const spend=sum(a,"ad_spend"),visits=sum(a,"visits"),cart=sum(a,"add_to_cart"),purchases=sum(a,"purchases"),revenue=sum(a,"revenue");return{spend,visits,cart,purchases,revenue,roas:spend?revenue/spend:null,cvr:visits?purchases/visits:null}}
function group(rows,key){return rows.reduce((o,r)=>((o[r[key]]??=[]).push(r),o),{})}
function pct(a,b){return b?((a-b)/b)*100:null}
function won(n){return new Intl.NumberFormat("ko-KR",{notation:"compact",maximumFractionDigits:1}).format(n)+"원"}
function rate(n){return n==null?"계산 불가":(n*100).toFixed(1)+"%"}
function change(el,a,b){const v=pct(a,b);el.textContent=v==null?"비교 불가":(v>=0?"+":"")+v.toFixed(1)+"% 전월 대비";el.className=v>=0?"positive":"negative"}
function bars(el,items,label,value,format){const max=Math.max(...items.map(value),1);el.innerHTML=items.map(x=>`<div class="barrow"><b>${label(x)}</b><div class="track"><div class="bar" style="width:${Math.max(2,value(x)/max*100)}%"></div></div><span>${format(value(x))}</span></div>`).join("")}
function render(rows){current=rows;const months=Object.entries(group(rows,"date")).reduce((o,[d,a])=>{const k=d.slice(0,7);(o[k]??=[]).push(...a);return o},{});const keys=Object.keys(months).sort();const latest=metrics(months[keys.at(-1)]),prev=keys.length>1?metrics(months[keys.at(-2)]):latest;
revenue.textContent=won(latest.revenue);spend.textContent=won(latest.spend);roas.textContent=rate(latest.roas);cvr.textContent=rate(latest.cvr);
change(revenueChange,latest.revenue,prev.revenue);change(spendChange,latest.spend,prev.spend);change(roasChange,latest.roas,prev.roas);change(cvrChange,latest.cvr,prev.cvr);
bars(document.querySelector("#months"),keys.map(k=>({k,m:metrics(months[k])})),x=>x.k,x=>x.m.revenue,won);
const steps=[["방문",latest.visits],["장바구니",latest.cart],["구매",latest.purchases]];funnel.innerHTML=steps.map((x,i)=>`<div class="funnel-step" style="width:${100-i*18}%"><b>${x[0]}</b> ${x[1].toLocaleString()}건</div>`).join("");
const cs=Object.entries(group(months[keys.at(-1)],"channel")).map(([k,a])=>({k,m:metrics(a)}));bars(channels,cs,x=>x.k,x=>x.m.roas??0,rate);
const rc=pct(latest.revenue,prev.revenue),sc=pct(latest.spend,prev.spend),vc=pct(latest.visits,prev.visits),pc=pct(latest.purchases,prev.purchases);
insight.textContent=`광고비 ${sc.toFixed(1)}%, 방문 ${vc.toFixed(1)}% 변화에 비해 구매 ${pc.toFixed(1)}%, 매출 ${rc.toFixed(1)}% 변화가 확인됩니다.`;
app.hidden=false;status.textContent=`${rows.length}개 행 분석 완료`;answer.innerHTML="";
}
function analyze(){if(!current)return;const m=group(current,"date"),k=Object.keys(m).sort();if(k.length<2){answer.textContent="전월 비교를 위해 최소 2개 기간 데이터가 필요합니다.";return}const a=metrics(m[k.at(-1)]),b=metrics(m[k.at(-2)]);const sc=pct(a.spend,b.spend),vc=pct(a.visits,b.visits),pc=pct(a.purchases,b.purchases),rc=pct(a.revenue,b.revenue),cc=pct(a.cvr,b.cvr);
answer.innerHTML=`<p><b>확인된 사실</b><br>광고비 ${sc.toFixed(1)}%, 방문 ${vc.toFixed(1)}%, 구매 ${pc.toFixed(1)}%, 매출 ${rc.toFixed(1)}% 변화했습니다. 구매전환율은 ${rate(b.cvr)} → ${rate(a.cvr)}로 ${cc.toFixed(1)}% 변했습니다.</p><p><b>원인 후보</b><br>현재 데이터에서는 유입 감소보다 방문 이후 구매 전환 과정의 악화가 매출 감소와 함께 관찰됩니다. 인과관계는 이 데이터만으로 확정할 수 없습니다.</p><p><b>다음 분석</b><br>상품별 전환율과 채널별 구매전환율을 분해해 어느 구간에서 하락폭이 큰지 확인하세요.</p>`;}
sample.addEventListener("click",()=>{try{render(parseCSV(SAMPLE))}catch(e){status.textContent=e.message}});
file.addEventListener("change",async e=>{try{render(parseCSV(await e.target.files[0].text()))}catch(err){status.textContent=err.message;app.hidden=true}});
ask.addEventListener("click",()=>answerByQuestion(question.value));
function answerByQuestion(q){if(!current)return;const months=group(current,"date"),keys=Object.keys(months).sort();if(keys.length<2){answer.textContent="비교 분석을 위해 최소 2개 기간 데이터가 필요합니다.";return}const nowRows=months[keys.at(-1)],prevRows=months[keys.at(-2)],a=metrics(nowRows),b=metrics(prevRows);const sc=pct(a.spend,b.spend),vc=pct(a.visits,b.visits),pc=pct(a.purchases,b.purchases),rc=pct(a.revenue,b.revenue),cc=pct(a.cvr,b.cvr);const fact=`광고비 ${sc.toFixed(1)}%, 방문 ${vc.toFixed(1)}%, 구매 ${pc.toFixed(1)}%, 매출 ${rc.toFixed(1)}% 변화했고 구매전환율은 ${rate(b.cvr)} → ${rate(a.cvr)}입니다.`;if(q.includes("채널")){const prev=group(prevRows,"channel"),now=group(nowRows,"channel");const changes=Object.keys(now).map(k=>({k,v:pct(metrics(now[k]).roas,prev[k]?metrics(prev[k]).roas:null)})).filter(x=>x.v!=null).sort((x,y)=>x.v-y.v);const x=changes[0];answer.innerHTML=`<p><b>확인된 사실</b><br>${fact}</p><p><b>채널 분석</b><br>${x?x.k+"의 ROAS 변화율이 "+x.v.toFixed(1)+"%로 가장 크게 하락했습니다.":"비교 가능한 채널 데이터가 부족합니다."}</p><p><b>다음 분석</b><br>해당 채널을 상품별로 분해해 확인하세요.</p>`;return}if(q.includes("상품")){const prev=group(prevRows,"product"),now=group(nowRows,"product");const changes=Object.keys(now).map(k=>({k,v:pct(metrics(now[k]).revenue,prev[k]?metrics(prev[k]).revenue:null)})).filter(x=>x.v!=null).sort((x,y)=>x.v-y.v);const x=changes[0];answer.innerHTML=`<p><b>확인된 사실</b><br>${fact}</p><p><b>상품 분석</b><br>${x?x.k+"의 매출 변화율이 "+x.v.toFixed(1)+"%로 가장 크게 하락했습니다.":"비교 가능한 상품 데이터가 부족합니다."}</p><p><b>다음 분석</b><br>해당 상품의 채널별 방문→구매 전환율을 확인하세요.</p>`;return}if(q.includes("지표")||q.includes("먼저")){answer.innerHTML=`<p><b>우선 확인 지표</b><br>구매전환율을 먼저 확인할 근거가 있습니다. ${rate(b.cvr)} → ${rate(a.cvr)}로 변했습니다.</p><p><b>근거</b><br>${fact}</p><p><b>한계</b><br>이 데이터만으로 인과관계를 확정할 수 없습니다.</p>`;return}answer.innerHTML=`<p><b>확인된 사실</b><br>${fact}</p><p><b>원인 후보</b><br>현재 데이터에서는 유입 감소보다 방문 이후 구매 전환 과정의 악화가 매출 감소와 함께 관찰됩니다. 인과관계는 이 데이터만으로 확정할 수 없습니다.</p><p><b>다음 분석</b><br>상품별 전환율과 채널별 구매전환율을 분해해 확인하세요.</p>`;}
document.querySelector(".faq").addEventListener("click",(e)=>{const btn=e.target.closest(".faq-btn");if(!btn)return;const q=document.getElementById("question");q.value=btn.textContent.trim();answerByQuestion(q.value);});
question.addEventListener("keydown",e=>{if(e.key==="Enter")answerByQuestion(question.value)});
