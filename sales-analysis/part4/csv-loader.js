// Part 4 CSV loader with strict validation.
const FILES=["sales_2026_06.csv","sales_2026_07.csv","sales_2026_08.csv","sales_2026_09.csv"];
const REQUIRED=["date","product","channel","ad_spend","visits","purchases","revenue"];
const NUMERIC_FIELDS=["ad_spend","impressions","clicks","visits","add_to_cart","purchases","units","revenue","refund","unit_price","discount_rate","competitor_min_price","holidays","stockout_days","days"];

function parseLine(line){
  const out=[]; let value=""; let quoted=false;
  for(let i=0;i<line.length;i++){
    const ch=line[i];
    if(ch==='"'){
      if(quoted && line[i+1]==='"'){ value+='"'; i++; }
      else quoted=!quoted;
    } else if(ch==="," && !quoted){ out.push(value); value=""; }
    else value+=ch;
  }
  if(quoted) throw new Error("닫히지 않은 따옴표가 있는 CSV입니다.");
  out.push(value);
  return out;
}

export function parseCSV(text){
  const lines=text.replace(/^\uFEFF/,"").split(/\r?\n/).filter(x=>x.trim()!=="");
  if(lines.length<2) throw new Error("CSV 데이터 행이 없습니다.");
  const headers=parseLine(lines[0]).map(v=>v.trim());
  const missing=REQUIRED.filter(k=>!headers.includes(k));
  if(missing.length) throw new Error("필수 컬럼 누락: "+missing.join(", "));

  return lines.slice(1).map((line,index)=>{
    const values=parseLine(line);
    if(values.length!==headers.length) throw new Error(`${index+2}행의 열 개수가 헤더와 다릅니다.`);
    const row=Object.fromEntries(headers.map((key,i)=>[key,values[i]?.trim()??""]));
    if(!/^\d{4}-\d{2}-\d{2}$/.test(row.date)) throw new Error(`${index+2}행 date는 YYYY-MM-DD 형식이어야 합니다: ${row.date}`);
    for(const key of NUMERIC_FIELDS){
      if(!(key in row) || row[key]==="") continue;
      const value=Number(row[key]);
      if(!Number.isFinite(value)) throw new Error(`${index+2}행 ${key} 값은 숫자여야 합니다: ${row[key]}`);
      if(value<0) throw new Error(`${index+2}행 ${key} 값은 0 이상이어야 합니다: ${row[key]}`);
    }
    return row;
  });
}

export async function loadPart3CSV(basePath="../data"){
  const chunks=await Promise.all(FILES.map(async file=>{
    const response=await fetch(`${basePath}/${file}`);
    if(!response.ok) throw new Error(`CSV load failed: ${file}`);
    return parseCSV(await response.text());
  }));
  return chunks.flat();
}
