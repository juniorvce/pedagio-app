let files=[];
const dz=document.getElementById('dropZone'),fi=document.getElementById('fileInput');
dz.addEventListener('click',()=>fi.click());
dz.addEventListener('dragover',e=>{e.preventDefault();dz.classList.add('drag-over');});
dz.addEventListener('dragleave',()=>dz.classList.remove('drag-over'));
dz.addEventListener('drop',e=>{e.preventDefault();dz.classList.remove('drag-over');addFiles([...e.dataTransfer.files]);});
fi.addEventListener('change',()=>addFiles([...fi.files]));
function addFiles(nf){nf.forEach(f=>{if(!files.find(x=>x.name===f.name&&x.size===f.size))files.push(f);});renderFiles();}
function renderFiles(){
  const list=document.getElementById('fileList'),items=document.getElementById('fileItems'),cnt=document.getElementById('fileCount');
  if(!files.length){list.style.display='none';return;}
  list.style.display='block';cnt.textContent=`${files.length} arquivo(s)`;items.innerHTML='';
  files.forEach((f,i)=>{const li=document.createElement('li');li.innerHTML=`<span>📄</span><span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${f.name}</span><span style="color:#94a3b8;font-size:.7rem">${(f.size/1024).toFixed(0)}KB</span><button class="f-remove" onclick="removeFile(${i})">✕</button>`;items.appendChild(li);});}
function removeFile(i){files.splice(i,1);renderFiles();}
function clearFiles(){files=[];renderFiles();document.getElementById('fileInput').value='';}
function clearLog(){document.getElementById('terminal').innerHTML='<div class="t-line t-muted">Log limpo.</div>';}
function log(msg,type=''){const t=document.getElementById('terminal');const div=document.createElement('div');div.className='t-line'+(type?' t-'+type:'');div.textContent=msg;t.appendChild(div);t.scrollTop=t.scrollHeight;}
function toast(msg,dur=3000){const el=document.getElementById('toast');el.textContent=msg;el.classList.add('show');setTimeout(()=>el.classList.remove('show'),dur);}
let pi;
function startProg(){const b=document.getElementById('progressFill');let w=0;pi=setInterval(()=>{if(w<90){w+=3;b.style.width=w+'%';}},300);}
function stopProg(){clearInterval(pi);const b=document.getElementById('progressFill');b.style.width='100%';setTimeout(()=>b.style.width='0',800);}
async function processar(){
  if(!files.length){toast('Adicione pelo menos 1 PDF!');return;}
  const btn=document.getElementById('btnProcess'),txt=document.getElementById('btnText');
  btn.disabled=true;txt.textContent='Processando...';startProg();log('');log('Enviando '+files.length+' arquivo(s)...');
  const form=new FormData();files.forEach(f=>form.append('files',f,f.name));
  try{
    const res=await fetch('/api/processar',{method:'POST',body:form});
    const data=await res.json();
    if(!res.ok){log('ERRO: '+(data.detail||res.statusText),'err');toast('Erro no servidor');return;}
    (data.logs||[]).forEach(l=>log(l,l.includes('ERRO')?'err':''));
    const r=data.resumo||{};
    ['total','ida','volta','indefinido','erro'].forEach(k=>{const el=document.getElementById('s-'+k);if(el)el.textContent=r[k]||0;});
    if(data.download){const dl=document.getElementById('downloadBtn');dl.href=data.download;dl.style.display='block';}
    log('');log('Concluido! '+(r.total||0)+' comprovante(s).');toast('Processamento concluido!');
  }catch(e){log('Falha de conexao: '+e.message,'err');toast('Falha de conexao');}
  finally{btn.disabled=false;txt.textContent='PROCESSAR COMPROVANTES';stopProg();}
}
if('serviceWorker' in navigator)navigator.serviceWorker.register('/static/sw.js').catch(()=>{});