import os, re, io, zipfile, uuid
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
import pypdf
from pdf2image import convert_from_bytes
import openpyxl
from openpyxl.drawing.image import Image as XLImage
from openpyxl.drawing.spreadsheet_drawing import TwoCellAnchor, AnchorMarker

app = FastAPI(title="Pedagio App")
HERE = Path(__file__).parent
OUT = HERE / "outputs"; OUT.mkdir(exist_ok=True)

SLOTS = [(1,213120,3,457560),(4,159480,6,533520),(7,52560,8,513000),(8,802440,10,1089720)]
FILEIRAS = [(79,71100,99,86400),(100,38160,120,53460),(122,6480,142,21780)]

def is_pdf(name, raw): return name.lower().endswith(".pdf") or raw[:5]==b"%PDF-"

def extrair(raw):
    d={"data":None,"hora":None,"direcao":"INDEFINIDO"}
    try:
        r=pypdf.PdfReader(io.BytesIO(raw)); t="\n".join((p.extract_text() or "") for p in r.pages)
    except Exception: t=""
    m=re.search(r"Data da passagem\s+(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}:\d{2})",t)
    if m: d["data"],d["hora"]=m.group(1),m.group(2)
    else:
        m2=re.search(r"(\d{2}/\d{2}/\d{4})",t); m3=re.search(r"(\d{2}:\d{2})",t)
        if m2: d["data"]=m2.group(1)
        if m3: d["hora"]=m3.group(1)
    if d["hora"]:
        try:
            h,mn=map(int,d["hora"].split(":")); v=h*60+mn
            if 480<=v<=720: d["direcao"]="IDA"
            elif 900<=v<=1140: d["direcao"]="VOLTA"
        except Exception: pass
    return d

def fmt_nome(d):
    if d["data"]:
        try: f=datetime.strptime(d["data"],"%d/%m/%Y").strftime("%d-%m-%y")
        except Exception: f=d["data"].replace("/","-")
    else: f="00-00-00"
    return f"{f} - {d['direcao']}.png"

def chave(it):
    d=it["d"]
    try: dt=datetime.strptime(d["data"],"%d/%m/%Y")
    except Exception: dt=datetime.min
    return (dt,{"IDA":0,"VOLTA":1,"INDEFINIDO":2}.get(d["direcao"],9))

def inserir(ws,p,slot,fil):
    fc,fco,tc,tco=slot; fr,fro,tr,tro=fil
    img=XLImage(p)
    img.anchor=TwoCellAnchor(editAs="oneCell",
        _from=AnchorMarker(col=fc,colOff=fco,row=fr,rowOff=fro),
        to=AnchorMarker(col=tc,colOff=tco,row=tr,rowOff=tro))
    ws.add_image(img)

@app.get("/",response_class=HTMLResponse)
def home(): return HTML
@app.get("/api/health")
def health(): return {"status":"ok"}

@app.post("/api/processar")
async def processar(modelo: UploadFile = File(...), pdfs: list[UploadFile] = File(...)):
  import traceback
  try:
      job=str(uuid.uuid4())[:8]; jd=OUT/job; imgdir=jd/"imgs"; imgdir.mkdir(parents=True)
      modelo_bytes=await modelo.read()
      regs=[]; stats={"IDA":0,"VOLTA":0,"INDEFINIDO":0}; logs=[]
      for i,pf in enumerate(pdfs):
          raw=await pf.read()
          if not is_pdf(pf.filename,raw): logs.append(f"Ignorado: {pf.filename}"); continue
          d=extrair(raw); stats[d["direcao"]]+=1; nome=fmt_nome(d)
          try:
              pages=convert_from_bytes(raw,dpi=200,fmt="png")
              p=imgdir/f"{i:03d}_{nome}"; pages[0].save(p,"PNG",optimize=True)
              regs.append({"d":d,"nome":nome,"path":str(p)}); logs.append(f"OK {pf.filename} -> {nome} [{d['direcao']}]")
          except Exception as e: logs.append(f"ERRO {pf.filename}: {e}")
      if not regs: raise HTTPException(400,"Nenhum PDF valido.")
      regs.sort(key=chave)
      wb=openpyxl.load_workbook(io.BytesIO(modelo_bytes)); ws=wb.active; total=len(regs)
      if total>8: ws.insert_rows(121,amount=22); logs.append(f"{total} (>8): +22 linhas.")
      else: logs.append(f"{total} (<=8): planilha INTACTA.")
      for idx,reg in enumerate(regs):
          if idx>=12: logs.append(f"Limite 12. {reg['nome']} ignorado."); continue
          inserir(ws,reg["path"],SLOTS[idx%4],FILEIRAS[idx//4])
          logs.append(f"[{idx+1:02d}] {reg['nome']} -> slot {idx%4+1}, fileira {idx//4+1}")
      xlsx=jd/"Planilha_Preenchida.xlsx"; wb.save(str(xlsx))
      zp=jd/"Resultado.zip"
      with zipfile.ZipFile(zp,"w",zipfile.ZIP_DEFLATED) as zf:
          zf.write(str(xlsx),"Planilha_Preenchida.xlsx")
          for reg in regs: zf.write(reg["path"],f"Imagens/{reg['nome']}")
      return JSONResponse({"job":job,"resumo":{"total":total,**{k.lower():v for k,v in stats.items()}},
          "logs":logs,"xlsx":f"/api/baixar/{job}/xlsx","zip":f"/api/baixar/{job}/zip"})

  except HTTPException:
    raise
  except Exception as e:
    return JSONResponse(status_code=500, content={"erro": str(e), "trace": traceback.format_exc()[-1200:]})

@app.get("/api/baixar/{job}/{tipo}")
def baixar(job:str,tipo:str):
    jd=OUT/job
    if tipo=="xlsx":
        f=jd/"Planilha_Preenchida.xlsx"; mt="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"; fn="Planilha_Preenchida.xlsx"
    else:
        f=jd/"Resultado.zip"; mt="application/zip"; fn="Resultado.zip"
    if not f.exists(): raise HTTPException(404,"nao encontrado")
    return FileResponse(str(f),media_type=mt,filename=fn)

HTML = """<!DOCTYPE html><html lang="pt-BR"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pedagio App</title><style>
*{box-sizing:border-box;margin:0;padding:0;font-family:'Segoe UI',system-ui,sans-serif}
body{background:#0f172a;color:#e2e8f0;padding:16px;display:flex;justify-content:center}
.wrap{max-width:720px;width:100%}h1{color:#3b82f6;text-align:center;margin:14px 0 4px}
.sub{text-align:center;color:#94a3b8;margin-bottom:22px;font-size:.9rem}
.card{background:#1e293b;border:1px solid #334155;border-radius:14px;padding:20px;margin-bottom:16px}
label{display:block;color:#94a3b8;font-weight:600;font-size:.85rem;margin-bottom:8px}
input[type=file]{width:100%;padding:11px;background:#0f172a;border:1px dashed #334155;border-radius:8px;color:#e2e8f0;margin-bottom:14px;cursor:pointer}
.stats{display:flex;gap:10px;margin-bottom:16px}
.sb{flex:1;background:#0f172a;border:1px solid #334155;border-radius:10px;padding:12px;text-align:center}
.sb span{display:block;font-size:1.6rem;font-weight:800}.sb small{color:#94a3b8;font-size:.72rem}
button{width:100%;background:#3b82f6;color:#fff;border:none;padding:14px;font-size:1.05rem;font-weight:700;border-radius:10px;cursor:pointer}
button:hover{background:#2563eb}button:disabled{background:#334155;cursor:not-allowed}
.dl{display:none;gap:10px;margin-top:12px}
.dl a{flex:1;text-align:center;background:#22c55e;color:#fff;text-decoration:none;padding:11px;border-radius:8px;font-weight:700;font-size:.9rem}
.dl a:hover{background:#16a34a}
#log{background:#020617;color:#4ade80;padding:14px;border-radius:10px;font-family:monospace;font-size:.78rem;height:200px;overflow-y:auto;margin-top:16px;white-space:pre-wrap}
</style></head><body><div class="wrap">
<h1>🚗 Pedágio App</h1><p class="sub">Comprovantes PDF → planilha no padrão do gabarito</p>
<div class="card">
<label>📂 Planilha Modelo (.xlsx)</label><input type="file" id="modelo" accept=".xlsx">
<label>📄 Comprovantes PDF (vários)</label><input type="file" id="pdfs" multiple>
<div class="stats">
<div class="sb"><span id="s-total" style="color:#3b82f6">0</span><small>Total</small></div>
<div class="sb"><span id="s-ida" style="color:#22c55e">0</span><small>IDA</small></div>
<div class="sb"><span id="s-volta" style="color:#f59e0b">0</span><small>VOLTA</small></div></div>
<button id="btn" onclick="proc()">🚀 PROCESSAR</button>
<div class="dl" id="dl"><a id="dl-xlsx" href="#">⬇️ Planilha</a><a id="dl-zip" href="#">⬇️ ZIP completo</a></div>
</div><div id="log">Aguardando arquivos...</div></div>
<script>
function log(m){const l=document.getElementById('log');l.textContent+="\n"+m;l.scrollTop=l.scrollHeight;}
async function proc(){
  const mo=document.getElementById('modelo').files[0];const pf=document.getElementById('pdfs').files;
  if(!mo){alert('Carregue a planilha modelo!');return;}
  if(!pf.length){alert('Carregue os PDFs!');return;}
  const btn=document.getElementById('btn');btn.disabled=true;btn.textContent='Processando...';
  document.getElementById('log').textContent='Enviando...';
  const fd=new FormData();fd.append('modelo',mo);for(const f of pf)fd.append('pdfs',f);
  try{
    const r=await fetch('/api/processar',{method:'POST',body:fd});const j=await r.json();
    if(!r.ok){log('ERRO '+r.status+': '+(j.erro||j.detail||r.statusText));if(j.trace)log(j.trace);btn.disabled=false;btn.textContent='\ud83d\ude80 PROCESSAR';return;}
    (j.logs||[]).forEach(log);
    document.getElementById('s-total').textContent=j.resumo.total||0;
    document.getElementById('s-ida').textContent=j.resumo.ida||0;
    document.getElementById('s-volta').textContent=j.resumo.volta||0;
    document.getElementById('dl-xlsx').href=j.xlsx;document.getElementById('dl-zip').href=j.zip;
    document.getElementById('dl').style.display='flex';log('\nConcluido!');
  }catch(e){log('Falha: '+e.message);}finally{btn.disabled=false;btn.textContent='🚀 PROCESSAR';}
}
</script></body></html>"""

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
