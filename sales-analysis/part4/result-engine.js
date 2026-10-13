/**
 * Part 4 Result Engine
 * Contract: docs/part3_to_part4_metric_spec.md
 * Deterministic arithmetic only. LLM receives calculated results.
 */
const SUM_FIELDS=["ad_spend","impressions","clicks","visits","add_to_cart","purchases","units","revenue","refund"];
const CHANGE_FIELDS=["revenue","ad_spend","visits","purchases","roas","cvr","cpa","aov"];
const n=v=>{const x=Number(v);return Number.isFinite(x)?x:0};
export const safeDivide=(a,b)=>b>0?a/b:null;
export const percentChange=(a,b)=>(b!=null&&b>0&&a!=null)?((a-b)/b)*100:null;
export function calculateKPIs(rows){
 const x=Object.fromEntries(SUM_FIELDS.map(k=>[k,rows.reduce((s,r)=>s+n(r[k]),0)]));
 return {...x,
  ctr:safeDivide(x.clicks,x.impressions),cvr:safeDivide(x.purchases,x.visits),
  cart_rate:safeDivide(x.add_to_cart,x.visits),cart_to_purchase_rate:safeDivide(x.purchases,x.add_to_cart),
  roas:safeDivide(x.revenue,x.ad_spend),cpc:safeDivide(x.ad_spend,x.clicks),
  cpa:safeDivide(x.ad_spend,x.purchases),aov:safeDivide(x.revenue,x.purchases),
  revenue_per_visit:safeDivide(x.revenue,x.visits)
 };
}
const group=(rows,keyFn)=>rows.reduce((o,r)=>{const k=keyFn(r);(o[k]??=[]).push(r);return o},{});
export function buildResult(rows){
 const byMonth=group(rows,r=>String(r.date||"").slice(0,7));
 const periods=Object.keys(byMonth).filter(Boolean).sort();
 const monthly_kpis=Object.fromEntries(periods.map(p=>[p,calculateKPIs(byMonth[p])]));
 const currentPeriod=periods.at(-1)||null;
 const candidatePrevious=periods.at(-2)||null;
 const isPreviousMonth=(prev,curr)=>{
   if(!prev||!curr)return false;
   const [py,pm]=prev.split("-").map(Number),[cy,cm]=curr.split("-").map(Number);
   return cy*12+cm-(py*12+pm)===1;
 };
 const previousPeriod=isPreviousMonth(candidatePrevious,currentPeriod)?candidatePrevious:null;
 const current=currentPeriod?monthly_kpis[currentPeriod]:null,previous=previousPeriod?monthly_kpis[previousPeriod]:null;
 const changes={};
 if(current&&previous) for(const k of CHANGE_FIELDS) changes[k]=percentChange(current[k],previous[k]);
 const channels=[...new Set(rows.map(r=>r.channel).filter(Boolean))];
 const channel_kpis={};
 for(const ch of channels){
   channel_kpis[ch]={};
   const cr=rows.filter(r=>r.channel===ch), cm=group(cr,r=>String(r.date||"").slice(0,7));
   for(const p of Object.keys(cm).sort()) channel_kpis[ch][p]=calculateKPIs(cm[p]);
 }
 const currentRows=currentPeriod?byMonth[currentPeriod]:[];
 const coupangRows=currentRows.filter(r=>r.channel==="쿠팡");
 const undercutRows=coupangRows.filter(r=>{
   const unit=n(r.unit_price), competitor=n(r.competitor_min_price);
   return unit>0 && competitor>0 && competitor<unit;
 });
 const undercutProducts=[...new Set(undercutRows.map(r=>r.product).filter(Boolean))].sort();
 const diagnostics={
   coupang_undercut_product_count:undercutProducts.length,
   coupang_undercut_products:undercutProducts,
   evidence_rule:"channel=쿠팡 AND competitor_min_price < unit_price",
   causality_note:"가격 열세와 전환율 하락이 함께 관찰되지만 이 데이터만으로 인과관계를 확정하지 않는다."
 };
 return {schema_version:"1.1",currentPeriod,previousPeriod,current,previous,changes,monthly_kpis,channel_kpis,diagnostics};
}
