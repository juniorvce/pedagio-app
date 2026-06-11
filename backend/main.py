import sys,subprocess,re,os,shutil,uuid,warnings
from pathlib import Path
from datetime import datetime
def _pip(*pkgs):
    M={'pillow':'PIL','pypdf':'pypdf','pdf2image':'pdf2image','openpyxl':'openpyxl','fastapi':'fastapi','uvicorn':'uvicorn','python-multipart':'multipart'}
    for pkg in pkgs:
        try: __import__(M.get(pkg,pkg))
        except ImportError:
            for f in [['--break-system-packages'],['--user'],[]]:
                if subprocess.run([sys.executable,'-m','pip','install','-q',pkg]+f,capture_output=True).returncode==0: break
def _apt(p):
    if subprocess.run(['dpkg','-s',p],capture_output=True).returncode!=0:
        subprocess.run(['sudo','apt-get','install','-y','-q',p])
_apt('poppler-utils')
_pip('fastapi','uvicorn','python-multipart','pypdf','pdf2image','pillow','openpyxl')
from fastapi import FastAPI,UploadFile,File,HTTPException
from fastapi.responses import FileResponse,JSONResponse,HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import pypdf
from pdf2image import convert_from_path
import openpyxl
from openpyxl.drawing.image import Image as XLImage
from openpyxl.drawing.spreadsheet_drawing import AbsoluteAnchor
from openpyxl.drawing.xdr import XDRPoint2D,XDRPositiveSize2D
warnings.filterwarnings('ignore')
HERE=Path(__file__).parent
OUTPUTS=HERE/'outputs';MODELO=HERE/'modelo'/'modelo_planilha.xlsx'
FRONTEND=HERE.parent/'frontend'
OUTPUTS.mkdir(exist_ok=True)
PX=9525;DPI=300;CN=4;IW=1783440;IH=3254040
SX=[379800,2260800,4141080,6022080]
YB=12792240;YS=3254040;RH=161925;LP=80
app=FastAPI(title='PedagioApp',version='1.0')
app.add_middleware(CORSMiddleware,allow_origins=['*'],allow_methods=['*'],allow_headers=['*'])
if FRONTEND.exists():
    app.mount('/static',StaticFiles(directory=str(FRONTEND/'static')),name='static')
@app.get('/',response_class=HTMLResponse)
async def root(): return HTMLResponse((FRONTEND/'index.html').read_text(encoding='utf-8'))
@app.get('/api/health')
async def health(): return {'status':'ok'}
def is_pdf(p):
    if p.suffix.lower()=='.pdf': return True
    try:
        with open(p,'rb') as f: return f.read(5)==b'%PDF-'
    except: return False
def extrai(pdf):
    try:
        r=pypdf.PdfReader(str(pdf));t='\n'.join(p.extract_text() or '' for p in r.pages)
    except Exception as e: return {'erro':str(e)}
    d={k:None for k in ['id','valor','tipo','local','veiculo','data','hora','direcao','nome_img']}
    m=re.search(r'#(\d+)',t);d['id']=m.group(1) if m else None
    m=re.search(r'Total pago\s+R\$\s*([\d,\.]+)',t);d['valor']='R$ '+m.group(1) if m else None
    m=re.search(r'(Ped.gio|Estacionamento)',t,re.I);d['tipo']=m.group(1) if m else None
    m=re.search(r'(?:Ped.gio|Estacionamento)\s*\n([A-Z0-9 ]+)',t)
    d['local']=m.group(1).strip() if m else None
    m=re.search(r'Ve.culo\s+([A-Z0-9]+)',t);d['veiculo']=m.group(1) if m else None
    m=re.search(r'Data da passagem\s+(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}:\d{2})',t)
    if m: d['data'],d['hora']=m.group(1),m.group(2)
    else:
        m2=re.search(r'Data\s+(\d{2}/\d{2}/\d{4})',t)
        m3=re.search(r'Hor.rio\s+(\d{2}:\d{2})',t)
        if m2: d['data']=m2.group(1)
        if m3: d['hora']=m3.group(1)
    if d['hora']:
        try:
            h,mn=map(int,d['hora'].split(':'));v=h*60+mn
            d['direcao']='IDA' if 480<=v<=720 else('VOLTA' if 900<=v<=1140 else 'INDEFINIDO')
        except: d['direcao']='INDEFINIDO'
    else: d['direcao']='INDEFINIDO'
    if d['data']:
        try: fmt=datetime.strptime(d['data'],'%d/%m/%Y').strftime('%d-%m-%y')
        except: fmt=d['data'].replace('/','-')
        d['nome_img']=fmt+' - '+d['direcao']
    else: d['nome_img']='00-00-00 - '+(d['direcao'] or 'INDEFINIDO')
    return d
def cvt(pdf,nome,idir):
    imgs=[]
    for i,pg in enumerate(convert_from_path(str(pdf),dpi=DPI,fmt='png')):
        n=f'{nome}.png' if i==0 else f'{nome}_{i+1:02d}.png'
        dst=idir/n;c=2
        while dst.exists(): n2=n.replace('.png',f'_{c}.png');dst=idir/n2;c+=1;n=n2
        pg.save(dst,'PNG',optimize=True);imgs.append(dst)
    return imgs
def sk(item):
    d=item[1]
    try: dt=datetime.strptime(d['data'],'%d/%m/%Y')
    except: dt=datetime.min
    return (dt,{'IDA':0,'VOLTA':1,'INDEFINIDO':2}.get(d.get('direcao','INDEFINIDO'),9))
def acha(ws):
    for row in ws.iter_rows():
        for c in row:
            if c.value and isinstance(c.value,str) and 'ANEXE ABAIXO' in c.value.upper(): return c.row+2
    return 80
def insere(ws,ii,lb):
    y0=YB+(lb-LP)*RH
    for idx,(ip,d) in enumerate(ii):
        cs=idx%CN;rs=idx//CN
        xl=XLImage(str(ip));xl.width=IW//PX;xl.height=IH//PX
        xl.anchor=AbsoluteAnchor(pos=XDRPoint2D(SX[cs],y0+rs*YS),ext=XDRPositiveSize2D(IW,IH))
        ws.add_image(xl)
@app.post('/api/processar')
async def processar(files:list[UploadFile]=File(...)):
    jid=str(uuid.uuid4())[:8];jd=OUTPUTS/jid;idir=jd/'imgs'
    idir.mkdir(parents=True)
    if not MODELO.exists(): raise HTTPException(500,'modelo nao encontrado')
    logs=[];imgs=[];res={'total':0,'ida':0,'volta':0,'indefinido':0,'erro':0};pdfs=[]
    for f in files:
        dst=jd/f.filename;dst.write_bytes(await f.read())
        if is_pdf(dst): pdfs.append(dst)
        else: logs.append(f'Ignorado: {f.filename}')
    for pdf in sorted(pdfs,key=lambda x:x.name):
        logs.append(f'>> {pdf.name}')
        d=extrai(pdf)
        if 'erro' in d: logs.append(f'  ERRO: {d["erro"]}');res['erro']+=1;continue
        logs.append(f'  {d["data"]} {d["hora"]} | {d["direcao"]} | {d["local"]} | {d["valor"]}')
        try:
            for p in cvt(pdf,d['nome_img'],idir): imgs.append((p,d));logs.append(f'  PNG: {p.name}')
        except Exception as e: logs.append(f'  ERRO: {e}');res['erro']+=1;continue
        res['total']+=1
        k=d['direcao'].lower() if d['direcao'] else 'indefinido'
        if k in res: res[k]+=1
    imgs.sort(key=sk)
    logs.append(f'Inserindo {len(imgs)} imagem(ns)...')
    wb=openpyxl.load_workbook(str(MODELO));ws=wb.active
    insere(ws,imgs,acha(ws))
    out=jd/'planilha_preenchida.xlsx';wb.save(str(out))
    logs.append('Pronto!')
    return JSONResponse({'job_id':jid,'resumo':res,'logs':logs,'download':f'/api/download/{jid}'})
@app.get('/api/download/{jid}')
async def download(jid:str):
    f=OUTPUTS/jid/'planilha_preenchida.xlsx'
    if not f.exists(): raise HTTPException(404,'nao encontrado')
    return FileResponse(str(f),media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',filename='planilha_preenchida.xlsx')
if __name__=='__main__':
    import uvicorn,socket
    try: ip=socket.gethostbyname(socket.gethostname())
    except: ip='SEU-IP'
    print(f'\nPedagio App!\n  Local: http://localhost:8000\n  Rede : http://{ip}:8000\n')
    uvicorn.run('main:app',host='0.0.0.0',port=8000,reload=False)
