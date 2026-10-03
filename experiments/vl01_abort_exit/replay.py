"""Render recorded E12 states, without stepping or modifying the experiment."""
import argparse,gzip,hashlib,json
from pathlib import Path
import imageio.v2 as imageio
import mujoco
import numpy as np
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parents[2]
def main():
 p=argparse.ArgumentParser();p.add_argument('--evidence',type=Path,required=True);a=p.parse_args()
 conditions=('repeated-gap--hold','repeated-gap--open','repeated-gap--open-retreat');states=[];summaries=[]
 for name in conditions:
  with gzip.open(a.evidence/name/'states.jsonl.gz','rt',encoding='utf8') as f:states.append([json.loads(line) for line in f])
  summaries.append(json.loads((a.evidence/name/'summary.json').read_text('utf8')))
 model=mujoco.MjModel.from_xml_path(str(ROOT/'experiments/vl01_pick_place/scene.xml'))
 data=mujoco.MjData(model);renderer=mujoco.Renderer(model,height=320,width=480)
 try:font=ImageFont.truetype('arial.ttf',20)
 except OSError:font=ImageFont.load_default()
 target=a.evidence/'abort-exit-replay.mp4'
 if target.exists():raise FileExistsError(target)
 ticks=[]
 try:
  with imageio.get_writer(str(target),fps=25,codec='libx264',quality=7) as writer:
   for i in range(0,len(states[0]),2):
    tick=states[0][i]['tick'];ticks.append(tick);canvas=Image.new('RGB',(1440,384),'#faf9f6');draw=ImageDraw.Draw(canvas)
    for side,name in enumerate(conditions):
     state=states[side][i];assert state['tick']==tick
     data.qpos[:]=state['qpos'];data.qvel[:]=state['qvel'];data.ctrl[:]=state['ctrl'];data.time=tick*.002
     mujoco.mj_forward(model,data);renderer.update_scene(data,camera='overview')
     canvas.paste(Image.fromarray(renderer.render()),(side*480,64))
     aborted=summaries[side]['abort_tick'] is not None and tick>summaries[side]['abort_tick']
     draw.text((side*480+10,8),f"{name.removeprefix('repeated-gap--')} | t={tick*.002:.3f}s",font=font,fill='#263b34')
     draw.text((side*480+10,34),'EXIT ACTIVE' if aborted else 'SAME CONTROL PREFIX',font=font,fill='#263b34')
    if i==400:canvas.save(a.evidence/'abort-exit-poster.png')
    writer.append_data(np.asarray(canvas))
 finally:renderer.close()
 metadata=dict(kind='recorded-state-replay',fps=25,frames=len(ticks),ticks=ticks,conditions=conditions,
  sources={f'{name}/states.jsonl.gz':hashlib.sha256((a.evidence/name/'states.jsonl.gz').read_bytes()).hexdigest() for name in conditions},
  videoSha256=hashlib.sha256(target.read_bytes()).hexdigest(),note='mj_forward on stored qpos/qvel; no mj_step; not an additional rollout')
 (a.evidence/'replay.json').write_text(json.dumps(metadata,indent=2)+'\n',encoding='utf8')
 print(f'Rendered {len(ticks)} three-view frames: {target}')
if __name__=='__main__':main()
