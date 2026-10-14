(async () => {
  const form=document.querySelector('[data-detail-form="rights"]');
  const note=document.querySelector('[data-result-note="rights"]');
  const ready=async()=>{for(let i=0;i<200;i++){if(!note.textContent.includes('查询中') && form.elements.brand.options.length>1)return;await new Promise(r=>setTimeout(r,100));}throw Error('query timeout');};
  await ready();
  form.elements.brand.value='蔚来';
  form.querySelector('input[value="金融政策"]').checked=true;
  form.requestSubmit();await ready();
  const rows=()=>Array.from(document.querySelectorAll('[data-detail-table="rights"] tbody tr'));
  const first=rows().map(r=>r.cells[0].textContent);
  if(!first.length || rows().some(r=>r.cells[2].textContent!=='蔚来'))throw Error('brand filter mismatch');
  const total=document.querySelector('[data-overview="rights"] [data-metric="total"]').textContent;
  document.querySelector('[data-pagination="rights"] [data-page-action="next"]').click();await ready();
  const second=rows().map(r=>r.cells[0].textContent);
  if(second.some(id=>first.includes(id)))throw Error('pagination repeats');
  return JSON.stringify({brand:'蔚来',type:'金融政策',total,firstPage:first.length,secondPage:second.length,page:document.querySelector('[data-pagination="rights"]').textContent.trim(),noRepeatedIds:true});
})()
