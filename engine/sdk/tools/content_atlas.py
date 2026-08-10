"""Build a deterministic, compact RGBA atlas from an Aseprite sheet."""
from __future__ import annotations
import argparse, json, math, struct, zlib
from pathlib import Path

def read_png(path: Path):
    data = path.read_bytes(); assert data[:8] == b'\x89PNG\r\n\x1a\n'
    pos = 8; raw = bytearray(); w = h = depth = kind = None
    while pos < len(data):
        n = struct.unpack('>I', data[pos:pos+4])[0]; tag = data[pos+4:pos+8]; chunk = data[pos+8:pos+8+n]; pos += n + 12
        if tag == b'IHDR': w,h,depth,kind,_,_,_ = struct.unpack('>IIBBBBB', chunk)
        elif tag == b'IDAT': raw.extend(chunk)
        elif tag == b'IEND': break
    if depth != 8 or kind not in (2,6): raise ValueError('only 8-bit RGB/RGBA PNG is supported')
    bpp = 4 if kind == 6 else 3; stride = w*bpp; decoded = zlib.decompress(raw); rows=[]; prev=bytearray(stride); at=0
    for _ in range(h):
        f=decoded[at]; at += 1; cur=bytearray(decoded[at:at+stride]); at += stride
        for i in range(stride):
            left=cur[i-bpp] if i>=bpp else 0; up=prev[i]; ul=prev[i-bpp] if i>=bpp else 0
            if f==1: cur[i]=(cur[i]+left)&255
            elif f==2: cur[i]=(cur[i]+up)&255
            elif f==3: cur[i]=(cur[i]+((left+up)//2))&255
            elif f==4:
                p=left+up-ul; pa=abs(p-left); pb=abs(p-up); pc=abs(p-ul); cur[i]=(cur[i]+(left if pa<=pb and pa<=pc else up if pb<=pc else ul))&255
            elif f!=0: raise ValueError('unsupported PNG filter')
        rows.append(cur); prev=cur
    rgba=bytearray(w*h*4)
    for y,row in enumerate(rows):
        for x in range(w):
            s=x*bpp; d=(y*w+x)*4; rgba[d:d+3]=row[s:s+3]; rgba[d+3]=row[s+3] if bpp==4 else 255
    return w,h,rgba

def write_png(path,w,h,pix):
    def chunk(t,v): return struct.pack('>I',len(v))+t+v+struct.pack('>I',zlib.crc32(t+v)&0xffffffff)
    raw=b''.join(b'\0'+bytes(pix[y*w*4:(y+1)*w*4]) for y in range(h))
    path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(raw,9))+chunk(b'IEND',b''))

def main():
    p=argparse.ArgumentParser(); p.add_argument('--png',required=True); p.add_argument('--json',required=True); p.add_argument('--output-png',required=True); p.add_argument('--output-json',required=True); p.add_argument('--used',action='append',default=[]); p.add_argument('--source-root'); p.add_argument('--all',action='store_true'); p.add_argument('--preserve-size',action='store_true'); a=p.parse_args()
    doc=json.loads(Path(a.json).read_text(encoding='utf-8')); w,h,src=read_png(Path(a.png)); slices=[]
    used=set(a.used)
    if a.source_root:
        import re
        for source in Path(a.source_root).rglob('*.h'):
            text=source.read_text(encoding='utf-8',errors='ignore')
            text=re.sub(r'//.*|/\*.*?\*/|"(?:\\.|[^"\\])*"', ' ', text, flags=re.S)
            used.update(m.group(1) for m in re.finditer(r'\bt_([A-Za-z_][A-Za-z0-9_]*)\b', text))
    wanted=(used if not a.all else {s.get('name') for s in doc.get('meta',{}).get('slices',[])})|{'invalid'}
    for s in doc.get('meta',{}).get('slices',[]):
        if s.get('name') not in wanted: continue
        keys=s.get('keys',[])
        if len(keys)!=1 or keys[0].get('frame')!=0: raise ValueError('animated or malformed slice')
        b=keys[0].get('bounds',{}); x,y,sw,sh=(b.get(k) for k in ('x','y','w','h'))
        if min(x,y,sw,sh)<0 or x+sw>w or y+sh>h or not sw or not sh: raise ValueError('slice outside atlas')
        slices.append((s['name'],x,y,sw,sh))
    if 'invalid' not in {s[0] for s in slices}: raise ValueError('atlas must contain invalid slice')
    slices.sort(key=lambda s:s[0]); border=1; cols=max(1,int(math.ceil(math.sqrt(len(slices))))); cellw=max(s[3] for s in slices)+2*border; cellh=max(s[4] for s in slices)+2*border; ow=1
    if a.preserve_size:
        out=bytearray(src); out_s=[{'name':n,'color':'#0000ffff','keys':[{'frame':0,'bounds':{'x':x,'y':y,'w':sw,'h':sh}}]} for n,x,y,sw,sh in slices]
        write_png(Path(a.output_png),w,h,out); Path(a.output_json).parent.mkdir(parents=True,exist_ok=True); Path(a.output_json).write_text(json.dumps({'frames':{'atlas (main).aseprite':{'frame':{'x':0,'y':0,'w':w,'h':h},'rotated':False,'trimmed':False}},'meta':{'image':Path(a.output_png).name,'format':'RGBA8888','size':{'w':w,'h':h},'slices':out_s}},sort_keys=True,separators=(',',':')),encoding='utf-8'); return
    while ow<cols*cellw: ow*=2
    oh=1
    while oh<math.ceil(len(slices)/cols)*cellh: oh*=2
    out=bytearray(ow*oh*4); out_s=[]
    for i,(name,x,y,sw,sh) in enumerate(slices):
        dx=(i%cols)*cellw+border; dy=(i//cols)*cellh+border
        for yy in range(sh):
            for xx in range(sw): out[((dy+yy)*ow+dx+xx)*4:((dy+yy)*ow+dx+xx+1)*4]=src[((y+yy)*w+x+xx)*4:((y+yy)*w+x+xx+1)*4]
        for xx in range(sw):
            out[((dy-1)*ow+dx+xx)*4:((dy-1)*ow+dx+xx+1)*4]=out[(dy*ow+dx+xx)*4:(dy*ow+dx+xx+1)*4]; out[((dy+sh)*ow+dx+xx)*4:((dy+sh)*ow+dx+xx+1)*4]=out[((dy+sh-1)*ow+dx+xx)*4:((dy+sh-1)*ow+dx+xx+1)*4]
        for yy in range(sh):
            out[((dy+yy)*ow+dx-1)*4:((dy+yy)*ow+dx)*4]=out[((dy+yy)*ow+dx)*4:((dy+yy)*ow+dx+1)*4]; out[((dy+yy)*ow+dx+sw)*4:((dy+yy)*ow+dx+sw+1)*4]=out[((dy+yy)*ow+dx+sw-1)*4:((dy+yy)*ow+dx+sw)*4]
        out_s.append({'name':name,'color':'#0000ffff','keys':[{'frame':0,'bounds':{'x':dx,'y':dy,'w':sw,'h':sh}}]})
    write_png(Path(a.output_png),ow,oh,out); result={'frames':{'atlas (main).aseprite':{'frame':{'x':0,'y':0,'w':ow,'h':oh},'rotated':False,'trimmed':False}},'meta':{'image':Path(a.output_png).name,'format':'RGBA8888','size':{'w':ow,'h':oh},'slices':out_s}}
    Path(a.output_json).parent.mkdir(parents=True,exist_ok=True); Path(a.output_json).write_text(json.dumps(result,sort_keys=True,separators=(',',':')),encoding='utf-8')
if __name__=='__main__': main()
