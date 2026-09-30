"""Generate a standalone, offline HTML ranking report."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from local_aso_tracker.models import TrackingTarget
from local_aso_tracker.repositories.data import latest_pairs, successful_checks
from local_aso_tracker.services.analytics import RankingRow, opportunity_group


def generate_html_report(session: Session, targets: list[TrackingTarget], output: Path) -> int:
    """Write one self-contained HTML file with all ranking data embedded."""

    pairs = latest_pairs(session, targets)
    rows = [
        RankingRow(target, pair[0], pair[1])
        for target in targets
        if (pair := pairs.get(target.id)) is not None
    ]
    target_map = {target.id: target for target in targets}
    payload = {
        "generatedAt": datetime.now(UTC).isoformat(),
        "latest": [
            {
                "targetId": row.target.id,
                "app": row.target.app.name,
                "keyword": row.target.keyword.keyword,
                "country": row.target.storefront.country_code,
                "device": row.target.device,
                "rank": row.latest.rank,
                "found": row.latest.found,
                "limit": row.latest.result_limit,
                "previous": row.previous.rank if row.previous else None,
                "change": row.change,
                "checkedAt": row.latest.checked_at.isoformat(),
                "opportunity": opportunity_group(row.latest),
            }
            for row in rows
        ],
        "history": [
            {
                "targetId": check.tracking_target_id,
                "keyword": target_map[check.tracking_target_id].keyword.keyword,
                "country": target_map[check.tracking_target_id].storefront.country_code,
                "device": target_map[check.tracking_target_id].device,
                "rank": check.rank,
                "found": check.found,
                "checkedAt": check.checked_at.isoformat(),
            }
            for check in successful_checks(session, targets)
        ],
    }
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(_document(data), encoding="utf-8")
    return len(rows)


def _document(data: str) -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Local ASO Tracker Report</title>
<style>
:root{{--ink:#17221e;--muted:#68736e;--paper:#f4f2eb;--card:#fffdf8;--line:#dedbd1;--accent:#126b52;--good:#138a5b;--bad:#c44b3f;--shadow:0 16px 50px #283c3420}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:15px/1.5 Inter,ui-sans-serif,system-ui,-apple-system,sans-serif}}
main{{max-width:1200px;margin:auto;padding:48px 24px 72px}}header{{display:flex;justify-content:space-between;align-items:end;gap:24px;margin-bottom:30px}}
.eyebrow{{color:var(--accent);font-weight:750;text-transform:uppercase;letter-spacing:.12em;font-size:12px}}h1{{font-family:Georgia,serif;font-size:clamp(34px,5vw,58px);line-height:1;margin:8px 0 0;font-weight:500}}h2{{font:500 26px Georgia,serif;margin:0 0 18px}}
.stamp{{color:var(--muted);text-align:right}}.controls{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:22px}}select,input{{border:1px solid var(--line);background:var(--card);border-radius:10px;padding:11px 13px;color:var(--ink);font:inherit}}
input{{min-width:260px}}.metrics{{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:24px}}.metric,.panel{{background:var(--card);border:1px solid var(--line);border-radius:16px;box-shadow:var(--shadow)}}.metric{{padding:19px}}.metric strong{{display:block;font:500 32px Georgia,serif}}.metric span{{color:var(--muted);font-size:13px}}
.grid{{display:grid;grid-template-columns:1.4fr .6fr;gap:20px;margin-bottom:20px}}.panel{{padding:22px;overflow:hidden}}table{{width:100%;border-collapse:collapse}}th{{text-align:left;color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.08em}}td,th{{padding:11px 9px;border-bottom:1px solid var(--line)}}tbody tr:last-child td{{border-bottom:0}}.rank{{font-weight:800}}.positive{{color:var(--good);font-weight:700}}.negative{{color:var(--bad);font-weight:700}}.pill{{display:inline-block;padding:4px 9px;border-radius:99px;background:#e7f2ed;color:var(--accent);font-size:12px}}
#chart{{width:100%;height:290px;background:linear-gradient(#fffdf8,#faf8f2);border:1px solid var(--line);border-radius:12px}}.legend{{display:flex;gap:14px;flex-wrap:wrap;color:var(--muted);font-size:12px;margin-top:10px}}.dot{{width:9px;height:9px;border-radius:50%;display:inline-block;margin-right:4px}}.empty{{color:var(--muted);padding:26px 0}}footer{{color:var(--muted);font-size:13px;margin-top:26px;max-width:900px}}
@media(max-width:850px){{.metrics{{grid-template-columns:repeat(2,1fr)}}.grid{{grid-template-columns:1fr}}header{{display:block}}.stamp{{text-align:left;margin-top:14px}}}}@media(max-width:520px){{main{{padding:28px 14px}}.metrics{{grid-template-columns:1fr 1fr}}.panel{{padding:15px}}.table-wrap{{overflow-x:auto}}}}
</style></head><body><main>
<header><div><div class="eyebrow">Private · Local · Apple public data</div><h1>Search visibility</h1></div><div class="stamp" id="stamp"></div></header>
<div class="controls"><select id="country"><option value="">All storefronts</option></select><select id="device"><option value="">All devices</option></select><input id="filter" type="search" placeholder="Filter keywords…"></div>
<section class="metrics" id="metrics"></section>
<section class="grid"><div class="panel"><h2>Latest rankings</h2><div class="table-wrap"><table><thead><tr><th>Keyword</th><th>Store</th><th>Device</th><th>Rank</th><th>Movement</th><th>Checked</th></tr></thead><tbody id="rankings"></tbody></table></div><div class="empty" id="empty" hidden>No ranking checks match these filters.</div></div>
<aside class="panel"><h2>Opportunities</h2><div id="opportunities"></div></aside></section>
<section class="panel"><h2>Rank history <small style="color:var(--muted);font:13px system-ui">(higher on chart is better)</small></h2><svg id="chart" viewBox="0 0 900 290" preserveAspectRatio="none"></svg><div class="legend" id="legend"></div></section>
<footer><strong>Methodology.</strong> Rank is the one-based position in Apple's public iTunes result entity for the selected keyword, storefront, and device. iPhone uses <code>software</code>; iPad uses <code>iPadSoftware</code>. “&gt;200” means the app was absent from the retrieved results, not that its exact rank is 201. Ranking is not search popularity; this report contains no search-volume, download, or difficulty estimates.</footer>
</main><script>const DATA={data};
const $=s=>document.querySelector(s), colors=['#126b52','#d88738','#6859a5','#2f77a7','#b34b6d','#70823a'];
const country=$('#country'),device=$('#device'),filter=$('#filter');
[...new Set(DATA.latest.map(x=>x.country))].sort().forEach(c=>country.insertAdjacentHTML('beforeend',`<option>${{c}}</option>`));
[...new Set(DATA.latest.map(x=>x.device))].sort().forEach(d=>device.insertAdjacentHTML('beforeend',`<option value="${{d}}">${{d==='ipad'?'iPad':'iPhone'}}</option>`));
$('#stamp').textContent='Generated '+new Date(DATA.generatedAt).toLocaleString();
function visible(){{const q=filter.value.trim().toLowerCase();return DATA.latest.filter(x=>(!country.value||x.country===country.value)&&(!device.value||x.device===device.value)&&(!q||x.keyword.toLowerCase().includes(q)))}}
function render(){{const rows=visible(),found=rows.filter(x=>x.found),ranks=found.map(x=>x.rank);const metrics=[['Tracked',rows.length],['Top 10',ranks.filter(x=>x<=10).length],['Top 50',ranks.filter(x=>x<=50).length],['Not visible',rows.filter(x=>!x.found).length],['Average',ranks.length?(ranks.reduce((a,b)=>a+b,0)/ranks.length).toFixed(1):'—']];$('#metrics').innerHTML=metrics.map(([a,b])=>`<div class="metric"><strong>${{b}}</strong><span>${{a}}</span></div>`).join('');
$('#rankings').innerHTML=rows.sort((a,b)=>(a.rank??999)-(b.rank??999)).map(x=>`<tr><td>${{esc(x.keyword)}}</td><td>${{x.country.toUpperCase()}}</td><td>${{x.device==='ipad'?'iPad':'iPhone'}}</td><td class="rank">${{x.found?'#'+x.rank:'&gt;'+x.limit}}</td><td class="${{x.change.startsWith('+')||x.change==='NEW'?'positive':x.change.startsWith('-')||x.change==='LOST'?'negative':''}}">${{x.change}}</td><td>${{new Date(x.checkedAt).toLocaleDateString()}}</td></tr>`).join('');$('#empty').hidden=rows.length>0;
const groups=Object.groupBy?Object.groupBy(rows,x=>x.opportunity):rows.reduce((a,x)=>((a[x.opportunity]??=[]).push(x),a),{{}});$('#opportunities').innerHTML=Object.entries(groups).map(([g,x])=>`<p><span class="pill">${{x.length}}</span> <strong>${{esc(g)}}</strong></p>`).join('')||'<div class="empty">No data.</div>';renderChart(rows)}}
function esc(s){{return s.replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]))}}
function renderChart(rows){{const ids=new Set(rows.map(x=>x.targetId)),history=DATA.history.filter(x=>ids.has(x.targetId)&&x.found);const svg=$('#chart'),legend=$('#legend');if(history.length<2){{svg.innerHTML='<text x="450" y="150" text-anchor="middle" fill="#68736e">More history is needed to draw a trend.</text>';legend.innerHTML='';return}}const times=history.map(x=>+new Date(x.checkedAt)),minT=Math.min(...times),maxT=Math.max(...times),maxR=Math.max(10,...history.map(x=>x.rank));let out='';[1,.25,.5,.75,1].forEach((f,i)=>{{const rank=i?Math.round(maxR*f):1,y=20+(rank-1)/(maxR-1)*240;out+=`<line x1="45" y1="${{y}}" x2="880" y2="${{y}}" stroke="#dedbd1"/><text x="38" y="${{y+4}}" text-anchor="end" fill="#68736e" font-size="11">${{rank}}</text>`}});const by={{}};history.forEach(x=>(by[x.targetId]??=[]).push(x));legend.innerHTML='';Object.values(by).forEach((points,i)=>{{points.sort((a,b)=>a.checkedAt.localeCompare(b.checkedAt));const color=colors[i%colors.length],coords=points.map(p=>{{const x=maxT===minT?450:45+(+new Date(p.checkedAt)-minT)/(maxT-minT)*835,y=20+(p.rank-1)/(maxR-1)*240;return `${{x}},${{y}}`}}).join(' ');out+=`<polyline points="${{coords}}" fill="none" stroke="${{color}}" stroke-width="2.5" vector-effect="non-scaling-stroke"/>`;legend.insertAdjacentHTML('beforeend',`<span><i class="dot" style="background:${{color}}"></i>${{esc(points[0].keyword)}} · ${{points[0].country.toUpperCase()}} · ${{points[0].device==='ipad'?'iPad':'iPhone'}}</span>`)}});svg.innerHTML=out}}
country.addEventListener('change',render);device.addEventListener('change',render);filter.addEventListener('input',render);render();</script></body></html>"""
