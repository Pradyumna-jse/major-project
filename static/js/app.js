const $=(s,r=document)=>r.querySelector(s), $$=(s,r=document)=>[...r.querySelectorAll(s)];
function toast(msg,kind='ok'){let t=$('.toast');if(!t){t=document.createElement('div');t.className='toast';document.body.appendChild(t)}
  const d=document.createElement('div');d.className=kind;d.textContent=msg;t.appendChild(d);setTimeout(()=>d.remove(),4200)}
function ring(score,level){const p=Math.max(0,Math.min(100,Math.round(score*100)));
  const c=level==='strong'?'#16a34a':level==='possible'?'#f59e0b':'#94a3b8';
  return `<div class="ring" style="--p:${p};--c:${c}"><i>${p}%</i></div>`}
function pill(l){return `<span class="pill ${l}">${l==='rejected'?'below threshold':l}</span>`}
function dropzone(zone,input,onfiles){
  zone.addEventListener('click',()=>input.click());
  ['dragenter','dragover'].forEach(e=>zone.addEventListener(e,ev=>{ev.preventDefault();zone.classList.add('over')}));
  ['dragleave','drop'].forEach(e=>zone.addEventListener(e,ev=>{ev.preventDefault();zone.classList.remove('over')}));
  zone.addEventListener('drop',ev=>{input.files=ev.dataTransfer.files;onfiles([...ev.dataTransfer.files])});
  input.addEventListener('change',()=>onfiles([...input.files]));
}
function tabs(root){const bs=$$('.tabs button',root);bs.forEach(b=>b.onclick=()=>{bs.forEach(x=>x.classList.remove('on'));b.classList.add('on');
  $$('[data-pane]',root).forEach(p=>p.hidden=p.dataset.pane!==b.dataset.tab)})}
async function post(url,fd){const r=await fetch(url,{method:'POST',body:fd});const j=await r.json().catch(()=>({error:'Server error'}));if(!r.ok)throw j;return j}
function geo(btn,latEl,lngEl){btn.onclick=()=>navigator.geolocation?navigator.geolocation.getCurrentPosition(p=>{latEl.value=p.coords.latitude.toFixed(5);lngEl.value=p.coords.longitude.toFixed(5);toast('Location set')},()=>toast('Location permission denied','bad')):0}
