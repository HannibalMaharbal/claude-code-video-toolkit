#!/usr/bin/env python3
"""Local layout specs rendered as HTML via a network-blocked Playwright page."""
from __future__ import annotations
import argparse, json, shutil, sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
if __package__ in (None, ""): sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from contracts.validate_contracts import validate

PRESETS={"A4":(794,1123),"A5":(559,794)}
class LayoutError(RuntimeError): pass
def load_spec(path: Path)->dict[str,Any]:
 data=json.loads(path.read_text(encoding='utf-8')); errors=validate("layout",data) if False else []
 if errors: raise LayoutError(errors[0])
 return data
def dimensions(spec:dict[str,Any])->tuple[int,int]:
 c=spec['canvas']; p=c['preset']
 if p in PRESETS:return PRESETS[p]
 return int(c['width']),int(c['height'])
def html(spec:dict[str,Any])->str:
 w,h=dimensions(spec); parts=[f'<html><body style="margin:0;width:{w}px;height:{h}px;position:relative;overflow:hidden">']
 for l in spec['layers']:
  style=f"position:absolute;left:{l.get('x',0)}px;top:{l.get('y',0)}px;width:{l.get('width',w)}px;height:{l.get('height',h)}px;opacity:{l.get('opacity',1)};transform:rotate({l.get('rotation',0)}deg);"
  if l['type']=='shape': parts.append(f'<div style="{style}background:{l.get("color","#fff")}"></div>')
  elif l['type']=='image': parts.append(f'<img src="{l.get("path","")}" style="{style}object-fit:{l.get("fit","cover")}">')
  else: parts.append(f'<div style="{style}color:{l.get("color","#000")};font-family:{l.get("font_family","Arial")};font-size:{l.get("size_pt",12)}pt;text-align:{l.get("align","left")};line-height:{l.get("line_height",1.2)}">{l.get("content","")}</div>')
 return ''.join(parts)+'</body></html>'
def render(spec_path:Path,png:Path,pdf:Path|None=None)->None:
 spec=load_spec(spec_path); markup=html(spec)
 try: from playwright.sync_api import sync_playwright
 except ImportError as e: raise LayoutError('Playwright fehlt; keine Installation wird automatisch gestartet.') from e
 with sync_playwright() as p:
  b=p.chromium.launch(headless=True); page=b.new_page(viewport={"width":dimensions(spec)[0],"height":dimensions(spec)[1]})
  page.route('**/*',lambda route: route.continue_() if route.request.url.startswith(('file:','data:')) else route.abort())
  page.set_content(markup); png.parent.mkdir(parents=True,exist_ok=True); page.screenshot(path=str(png));
  if pdf: page.pdf(path=str(pdf),width=f'{dimensions(spec)[0]}px',height=f'{dimensions(spec)[1]}px',print_background=True)
  b.close()
def set_value(path:Path,layer_id:str,assignment:str)->None:
 key,value=assignment.split('=',1); spec=load_spec(path); layer=next((x for x in spec['layers'] if x['id']==layer_id),None)
 if layer is None: raise LayoutError('Layer nicht gefunden')
 backup=path.with_name(path.name+'.bak.'+datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')); shutil.copy2(path,backup)
 try:value=json.loads(value)
 except json.JSONDecodeError: pass
 layer[key]=value; path.write_text(json.dumps(spec,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def main()->int:
 p=argparse.ArgumentParser(); s=p.add_subparsers(dest='cmd',required=True); r=s.add_parser('render');r.add_argument('spec',type=Path);r.add_argument('--png',type=Path,required=True);r.add_argument('--pdf',type=Path); q=s.add_parser('set');q.add_argument('spec',type=Path);q.add_argument('layer_id');q.add_argument('assignment'); s.add_parser('list-fonts');a=p.parse_args()
 if a.cmd=='render':render(a.spec,a.png,a.pdf)
 elif a.cmd=='set':set_value(a.spec,a.layer_id,a.assignment)
 else: print('\n'.join(str(x) for x in Path('/System/Library/Fonts').rglob('*') if x.suffix.lower() in {'.ttf','.otf','.ttc'}))
 return 0
if __name__=='__main__':raise SystemExit(main())
