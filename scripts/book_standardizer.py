#!/usr/bin/env python3
"""Language-neutral Input -> Book Model -> Standard EPUB."""
from __future__ import annotations
import argparse, hashlib, html, re, shutil, tempfile, zipfile
from pathlib import Path
from urllib.parse import unquote
from lxml import etree
from book_model import Book, Chapter, ContentBlock, Metadata, Part, Volume, normalize_source_path

CHAPTER = re.compile(r'^(?:第\s*([0-9０-９一二三四五六七八九十百千]+)\s*(?:章|話|回)|chapter[-_ ]?(\d+)|prologue|epilogue|序章|終章|序|終)$', re.I)
FILE_CHAPTER = re.compile(r'(?:chapter|chap)[-_ ]?0*(\d+)', re.I)
VOLUME = re.compile(r'^(?:第\s*([0-9０-９]+)\s*(?:巻|冊|部)|vol(?:ume)?\.?\s*([0-9０-９]+)|book\s*([0-9０-９]+))$', re.I)

def clean(s): return re.sub(r'[ \t\r\n]+',' ',s).strip()
def num(s):
    if not s: return None
    s=s.translate(str.maketrans('０１２３４５６７８９','0123456789'))
    if s.isdigit(): return int(s)
    u={'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10,'百':100,'千':1000}; total=cur=0
    for c in s:
        if c.isdigit(): cur=cur*10+int(c)
        elif c in u:
            n=u[c]
            if n>=10: total+=(cur or 1)*n; cur=0
            else: cur+=n
        else: return None
    return total+cur or None

def chapter_title(s):
    s=clean(s); m=CHAPTER.match(s)
    return (s,next((num(x) for x in m.groups() if x),None)) if m else None

def file_chapter(s):
    m=FILE_CHAPTER.search(Path(s).stem); return int(m.group(1)) if m else None

def volume_title(s):
    s=clean(s)
    if s in {'上巻','前編'}: return s,1
    if s in {'中巻'}: return s,2
    if s in {'下巻'}: return s,3
    if s in {'後編'}: return s,2
    m=VOLUME.match(s)
    if not m: return None
    n=next((num(x) for x in m.groups() if x),None)
    return (s,n) if n else None

def opf(root):
    t=etree.parse(str(root/'META-INF/container.xml')); rel=t.xpath("string((//*[local-name()='rootfile']/@full-path)[1])")
    if not rel: raise ValueError('EPUB package document not found')
    return root/unquote(rel)

def epub_metadata(root,fallback):
    t=etree.parse(str(opf(root)))
    def get(n): return clean(t.xpath(f"string((//*[local-name()='metadata']/*[local-name()='{n}'])[1])"))
    return Metadata(get('title') or fallback,get('creator'),get('language') or None,get('publisher') or None,get('identifier') or None,get('description') or None)

def spine(root):
    p=opf(root); t=etree.parse(str(p)); manifest={x.get('id'):x.get('href') for x in t.xpath("//*[local-name()='manifest']/*[local-name()='item']")}
    return [(p.parent/unquote(manifest[r.get('idref')].split('#')[0])).resolve() for r in t.xpath("//*[local-name()='spine']/*[local-name()='itemref']") if r.get('idref') in manifest]

def blocks(body,source):
    out=[]
    for e in body.iter():
        if not isinstance(e.tag,str): continue
        tag=etree.QName(e).localname.lower()
        if tag in {'script','style','noscript'}: continue
        text=clean(''.join(e.itertext()))
        if tag in {'h1','h2','h3','h4','h5','h6'} and text: out.append(ContentBlock('heading',text,{'level':int(tag[1])},source))
        elif tag in {'p','li','blockquote','dt','dd','pre','figcaption'} and text: out.append(ContentBlock('paragraph',text,{},source))
        elif tag=='img': out.append(ContentBlock('image',None,{'src':e.get('src',''),'alt':e.get('alt','')},source))
    return out

def parse_epub(path):
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)/'epub'
        with zipfile.ZipFile(path) as z: z.extractall(root)
        book=Book(epub_metadata(root,path.stem),[],[normalize_source_path(path)])
        volume=Volume(1,'Volume 1'); book.volumes.append(volume); current=None
        for source in spine(root):
            if source.suffix.lower() not in {'.xhtml','.html','.htm'} or not source.is_file(): continue
            t=etree.parse(str(source),etree.XMLParser(resolve_entities=False,no_network=True)); bodies=t.xpath("//*[local-name()='body']")
            if not bodies: continue
            sid=normalize_source_path(source.relative_to(root)); bs=blocks(bodies[0],sid)
            heads=[b for b in bs if b.kind=='heading']; logical=chapter_title(heads[0].content or '') if heads else None
            fc=file_chapter(source.name)
            if logical:
                if current: volume.chapters.append(current)
                current=Chapter(logical[1],logical[0])
            elif current is None: current=Chapter(fc,f'Chapter {fc}' if fc else source.stem)
            current.parts.append(Part(sid,bs))
        if current: volume.chapters.append(current)
        book.validate(); return book

def parse_txt(path):
    book=Book(Metadata(title=path.stem),[Volume(1,'Volume 1')],[normalize_source_path(path)]); current=None; bs=[]
    def flush():
        nonlocal current,bs
        if current: current.parts.append(Part(normalize_source_path(path),bs)); book.volumes[-1].chapters.append(current)
        current=None; bs=[]
    for raw in path.read_text(encoding='utf-8-sig').replace('\r\n','\n').replace('\r','\n').split('\n'):
        s=clean(raw)
        if not s: continue
        v=volume_title(s); c=chapter_title(s)
        if v:
            flush(); book.volumes.append(Volume(v[1],f'{path.stem} {v[0]}'))
        elif c:
            flush(); current=Chapter(c[1],c[0])
        else:
            if current is None: current=Chapter(None,'Chapter 1')
            bs.append(ContentBlock('paragraph',s,{},normalize_source_path(path)))
    flush()
    if len(book.volumes)>1 and not book.volumes[0].chapters: book.volumes.pop(0)
    book.validate(); return book

def render(ch):
    out=[f'<h1>{html.escape(ch.title)}</h1>']
    for part in ch.parts:
        for b in part.blocks:
            if b.kind=='heading':
                n=max(1,min(6,int(b.attributes.get('level',2)))); out.append(f'<h{n}>{html.escape(b.content or "")}</h{n}>')
            elif b.kind=='image':
                out.append(f'<p><img src="{html.escape(b.attributes.get("src",""),quote=True)}" alt="{html.escape(b.attributes.get("alt",""),quote=True)}"/></p>')
            elif b.content: out.append(f'<p>{html.escape(b.content)}</p>')
    return '<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml" xml:lang="und"><head><meta charset="utf-8"/><link rel="stylesheet" href="style.css"/></head><body>'+''.join(out)+'</body></html>'

def write_epub(book,output,combined=False):
    targets=[(Volume(1,book.metadata.title,[c for v in book.volumes for c in v.chapters]),output)] if combined else [(v,output.parent/f'{output.stem}_vol{v.number:02d}.epub') for v in book.volumes]
    result=[]
    for volume,target in targets:
        work=Path(tempfile.mkdtemp(prefix='book-'))
        try:
            (work/'META-INF').mkdir(); (work/'OEBPS').mkdir(); (work/'mimetype').write_bytes(b'application/epub+zip')
            (work/'META-INF/container.xml').write_text('<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>',encoding='utf-8')
            (work/'OEBPS/style.css').write_text('body{line-height:1.8;margin:1em}p{margin:0 0 1em;text-indent:1em}img{max-width:100%;height:auto}',encoding='utf-8')
            man=['<item id="css" href="style.css" media-type="text/css"/>']; spine_items=[]; nav=[]
            for i,ch in enumerate(volume.chapters,1):
                fn=f'chapter-{i:04d}.xhtml'; (work/'OEBPS'/fn).write_text(render(ch),encoding='utf-8'); man.append(f'<item id="c{i}" href="{fn}" media-type="application/xhtml+xml"/>'); spine_items.append(f'<itemref idref="c{i}"/>'); nav.append(f'<navPoint id="n{i}" playOrder="{i}"><navLabel><text>{html.escape(ch.title)}</text></navLabel><content src="{fn}"/></navPoint>')
            uid='urn:uuid:'+hashlib.sha256((book.metadata.title+volume.title).encode()).hexdigest()[:24]
            (work/'OEBPS/content.opf').write_text('<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">'+uid+'</dc:identifier><dc:title>'+html.escape(volume.title)+'</dc:title><dc:language>'+html.escape(book.metadata.language or 'und')+'</dc:language></metadata><manifest>'+''.join(man)+'</manifest><spine toc="ncx">'+''.join(spine_items)+'</spine></package>',encoding='utf-8')
            (work/'OEBPS/toc.ncx').write_text('<?xml version="1.0"?><ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1"><docTitle><text>'+html.escape(volume.title)+'</text></docTitle><navMap>'+''.join(nav)+'</navMap></ncx>',encoding='utf-8')
            target.parent.mkdir(parents=True,exist_ok=True)
            with zipfile.ZipFile(target,'w') as z:
                z.write(work/'mimetype','mimetype',compress_type=zipfile.ZIP_STORED)
                for f in sorted(work.rglob('*')):
                    if f.is_file() and f.name!='mimetype': z.write(f,f.relative_to(work).as_posix(),compress_type=zipfile.ZIP_DEFLATED)
            result.append(target)
        finally: shutil.rmtree(work)
    return result

def main():
    p=argparse.ArgumentParser(); p.add_argument('input',type=Path); p.add_argument('output',type=Path); p.add_argument('--combined',action='store_true'); a=p.parse_args()
    book=parse_txt(a.input) if a.input.suffix.lower()=='.txt' else parse_epub(a.input)
    for x in write_epub(book,a.output,a.combined): print(x)

if __name__=='__main__': main()
