import {buildResult} from "./result-engine.js";

const API_URL="https://joxyzphsqjwuyobkboqe.supabase.co/functions/v1/analyze-shop";
const CSV_BASE="https://raw.githubusercontent.com/ctaleez51-art/sales-analysis/feature/csv-input/data";
const CSV_FILES=["sales_2026_06.csv","sales_2026_07.csv","sales_2026_08.csv","sales_2026_09.csv"];

function parseCSV(text){
  const lines=text.replace(/^\uFEFF/,"").trim().split(/\r?\n/);
  const headers=lines[0].split(",").map(x=>x.trim());
  return lines.slice(1).filter(Boolean).map(line=>{
    const values=line.split(",");
    return Object.fromEntries(headers.map((key,i)=>[key,values[i]?.trim()??""]));
  });
}
async function loadTeamCSV(){
  const texts=await Promise.all(CSV_FILES.map(async file=>{
    const res=await fetch(`${CSV_BASE}/${file}`);
    if(!res.ok) throw new Error(`${file} 불러오기 실패 (${res.status})`);
    return res.text();
  }));
  return texts.flatMap(parseCSV);
}
const won=n=>n==null?"-":Math.round(n).toLocaleString("ko-KR")+"원";
const pct=n=>n==null?"-":(n*100).toFixed(2)+"%";
const multiple=n=>n==null?"-":n.toFixed(2)+"배";
const delta=n=>n==null?"-":(n>=0?"+":"")+n.toFixed(2)+"%";
const esc=s=>String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[c]));

export async function callAnalyzeShop(result, accessToken, question="2026년 9월 매출 하락의 핵심 구간과 데이터로 확인 가능한 원인 후보, 다음 액션을 분석해줘."){
  if(!accessToken) throw new Error("로그인이 필요합니다. Supabase access token이 없습니다.");
  const res=await fetch(API_URL,{
    method:"POST",
    headers:{
      "Content-Type":"application/json",
      "Authorization":`Bearer ${accessToken}`
    },
    body:JSON.stringify({result,question})
  });
  const data=await res.json();
  if(!res.ok) throw new Error(data?.detail?.error?.message||data?.error||"AI 분석 요청 실패");
  return data;
}

async function render(){
  const btn=document.querySelector("#run");
  btn.disabled=true; btn.textContent="3번 CSV 읽는 중...";
  document.querySelector("#analysis").innerHTML="<h3>분석 진행</h3><p>3번 담당자의 6~9월 CSV를 불러오고 있습니다.</p>";
  try{
    const rows=await loadTeamCSV();
    const r=buildResult(rows),m=r.current;
    document.querySelector("#period").textContent=`${r.previousPeriod} → ${r.currentPeriod} · CSV ${rows.length.toLocaleString()}행`;
    const cards=[
      ["매출",won(m.revenue),delta(r.changes.revenue)],
      ["광고비",won(m.ad_spend),delta(r.changes.ad_spend)],
      ["ROAS",multiple(m.roas),delta(r.changes.roas)],
      ["CVR",pct(m.cvr),delta(r.changes.cvr)],
      ["CPA",won(m.cpa),delta(r.changes.cpa)],
      ["AOV",won(m.aov),delta(r.changes.aov)]
    ];
    document.querySelector("#cards").innerHTML=cards.map(x=>`<article><small>${x[0]}</small><strong>${x[1]}</strong><span>${x[2]} 전월 대비</span></article>`).join("");
    document.querySelector("#json").textContent=JSON.stringify(r,null,2);
    document.querySelector("#analysis").innerHTML="<h3>OpenAI 분석 결과</h3><p>1,200행 KPI 계산 완료. OpenAI가 결과를 해석하고 있습니다...</p>";
    btn.textContent="AI 분석 중...";
    // 2번 로그인 모듈이 window.supabaseClient 또는 getAccessToken()을 제공하면 연결됩니다.
    let accessToken=null;
    if(typeof window.getAccessToken==="function") accessToken=await window.getAccessToken();
    else if(window.supabaseClient){
      const {data:{session}}=await window.supabaseClient.auth.getSession();
      accessToken=session?.access_token||null;
    }
    const data=await callAnalyzeShop(r,accessToken);
    document.querySelector("#analysis").innerHTML=`<h3>OpenAI 분석 결과</h3><pre class="ai">${esc(data.analysis||"응답이 비어 있습니다.")}</pre>`;
  }catch(e){
    document.querySelector("#analysis").innerHTML=`<h3>분석 오류</h3><p>${esc(e.message)}</p>`;
  }finally{
    btn.disabled=false;btn.textContent="3번 CSV로 분석 실행";
  }
}
document.querySelector("#run").textContent="3번 CSV로 분석 실행";
document.querySelector("#run").addEventListener("click",render);
