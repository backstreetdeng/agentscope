/* Overview presentation: existing live fields and destinations remain authoritative. */
(() => {
  const init = () => {
    const view=document.querySelector('.view[data-view="intel"]');
    if(!view)return;
    view.classList.add('intel-overview');
    const find=s=>view.querySelector(s), value=id=>document.getElementById(id)?.textContent.trim()||'—';
    const hero=find('.hero'), title=find('#hero-title');
    title.textContent='市场情报速览';
    const heading=document.createElement('div');heading.className='overview-heading';title.before(heading);heading.append(title);
    const subtitle=document.createElement('p');subtitle.textContent='政策 · 权益 · 新车 · 口碑，辅助市场决策';heading.append(subtitle);
    const actions=find('.hero__cta');actions.prepend(find('#intelligence-refresh'));actions.append(find('.chip-btn--static'));
    find('.intel-ribbon').hidden=true;find('.intelligence > .section-head').hidden=true;
    const summary=document.createElement('section');summary.className='overview-summary';summary.setAttribute('aria-label','数据摘要');
    const label=document.createElement('strong');label.textContent='数据摘要';summary.append(label);
    const summaryText=document.createElement('p');summaryText.textContent='正在核对四组最新数据…';summary.append(summaryText);
    hero.after(summary);
    const hints={policy:'政策主题与地区覆盖',rights:'价格权益与监测记录',newcar:'最新上市款型',wom:'原始口碑与来源覆盖'};
    view.querySelectorAll('.data-card').forEach(card=>{
      const head=card.querySelector('.data-card__head');
      const hint=document.createElement('span');hint.className='overview-card-hint';hint.textContent=hints[card.dataset.domain];head.append(hint);
      const meta=document.createElement('div');meta.className='overview-card-meta';
      meta.append(card.querySelector('.data-card__status'),card.querySelector('.data-card__sub'));head.after(meta);
      card.querySelector('.data-card__btn').textContent='查看明细';
    });
    const newCard=find('.data-card--newcar'),newHero=newCard.querySelector('.newcar-stat--hero');
    const metric=document.createElement('div');metric.className='data-card__metric overview-primary';
    const num=newHero.querySelector('.newcar-stat__value');num.classList.add('data-card__metric-value');metric.append(num);
    const unit=document.createElement('span');unit.className='data-card__metric-unit';unit.textContent='款';metric.append(unit);
    newCard.querySelector('.newcar-stats').before(metric);newHero.remove();
    const wom=find('.data-card--wom'),womHero=wom.querySelector('.koubei-metric');
    const womMetric=document.createElement('div');womMetric.className='data-card__metric overview-primary';
    const reviews=womHero.querySelector('.koubei-metric__value');reviews.classList.add('data-card__metric-value');womMetric.append(reviews);
    const reviewUnit=unit.cloneNode(true);reviewUnit.textContent='条口碑';womMetric.append(reviewUnit);
    wom.querySelector('.koubei-metrics').before(womMetric);womHero.remove();
    const sourceList=document.createElement('div');sourceList.className='overview-source-list';wom.querySelector('#koubei-provenance').before(sourceList);
    const latest=document.createElement('section');latest.className='overview-new-list';latest.setAttribute('aria-label','最新月份上市车型');
    const latestTitle=document.createElement('h4');latestTitle.textContent='最新月份上市车型';latest.append(latestTitle);
    const list=document.createElement('div');list.textContent='正在读取车型…';latest.append(list);newCard.querySelector('.data-card__actions').before(latest);
    async function loadLatest(){
      list.textContent='正在读取车型…';
      try{
        const response=await fetch('/api/new-car/list',{cache:'no-store'});const data=await response.json();
        if(!response.ok||!data.success)throw new Error();
        const period=value('newcar-latest-date'),groups=new Map();
        data.rows.filter(r=>`${r.year}-${String(r.month).padStart(2,'0')}`===period).forEach(r=>{
          const key=r.brand+' '+r.model;const g=groups.get(key)||{model:r.model,count:0};g.count++;groups.set(key,g);
        });
        list.replaceChildren();
        [...groups.values()].slice(0,4).forEach(g=>{const row=document.createElement('div');row.className='overview-model-row';const name=document.createElement('span');name.textContent=g.model;const count=document.createElement('span');count.textContent=g.count+'款';row.append(name,count);list.append(row);});
        if(!groups.size)list.textContent='暂无可核验车型数据';
      }catch{list.textContent='车型查询失败，请刷新重试';}
    }
    let previousPeriod='';
    function update(){
      const p=value('policy-total'),r=value('rights-total'),n=value('newcar-pending-total'),month=value('newcar-latest-date'),w=value('koubei-total');
      summaryText.textContent=`政策库 ${p} 条；权益库 ${r} 条累计监测记录；${month==='—'?'最新月份':month}上市 ${n} 个款型；口碑库 ${w} 条原始记录。`;
      const sources=value('koubei-provenance');sourceList.replaceChildren();
      if(sources.includes('条'))sources.split(' · ').forEach(text=>{const item=document.createElement('span');item.textContent=text;sourceList.append(item);});
      if(month!=='—'&&month!==previousPeriod){previousPeriod=month;loadLatest();}
    }
    const observer=new MutationObserver(update);
    ['policy-total','rights-total','newcar-pending-total','newcar-latest-date','koubei-total','koubei-provenance'].forEach(id=>{const el=document.getElementById(id);if(el)observer.observe(el,{childList:true,characterData:true,subtree:true});});
    find('#intelligence-refresh').addEventListener('click',()=>{previousPeriod='';});
    update();
  };
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();
