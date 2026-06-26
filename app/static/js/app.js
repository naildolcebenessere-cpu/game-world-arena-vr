function updateCountdowns(){
  document.querySelectorAll('.countdown').forEach(el=>{
    const end = new Date(el.dataset.end);
    const diff = end - new Date();
    if(isNaN(end)) return;
    if(diff<=0){ el.textContent='SCADUTO'; el.classList.add('expired'); return; }
    const m=Math.floor(diff/60000), s=Math.floor((diff%60000)/1000);
    el.textContent=String(m).padStart(2,'0')+':'+String(s).padStart(2,'0');
  });
}
setInterval(updateCountdowns,1000); updateCountdowns();
