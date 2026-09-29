"""CPU trajectory replay from CSV: markers are centres, not rendered robot geometry."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import imageio.v2 as imageio
import numpy as np
from PIL import Image, ImageDraw, ImageFont

def render(root, episode):
    folder=root/episode
    target=folder/"trajectory-replay.mp4"
    if target.exists(): raise ValueError("refusing to replace existing media")
    with (folder/"trajectory.csv").open() as f: rows=list(csv.DictReader(f))
    font=ImageFont.load_default(size=20)
    small=ImageFont.load_default(size=16)
    saved=False
    with imageio.get_writer(str(target),fps=50,codec="libx264",quality=7) as writer:
        for row in rows:
            frame=Image.new("RGB",(960,640),"#f8f7f2")
            d=ImageDraw.Draw(frame)
            d.text((36,22),episode,font=font,fill="#27372d")
            d.text((36,53),"Measured coordinates / trajectory replay / 50 Hz",font=small,fill="#5c665f")
            d.text((36,84),f"t = {float(row['time']):.3f} s    phase = {row['phase']}",font=font,fill="#27372d")
            # Shared metric axes: 0..0.32m x, 0..0.24m z; centre markers are not to scale.
            def point(x,z): return (75+float(x)*2100,495-float(z)*1400)
            for z in (0,.05,.10,.15,.20):
                a,b=point(0,z),point(.32,z)
                d.line((a,b),fill="#d7dbd2",width=1)
                d.text((16,a[1]-9),str(round(z*1000)),font=small,fill="#5c665f")
            for x in (0,.08,.16,.24,.32):
                a,b=point(x,0),point(x,.24)
                d.line((a,b),fill="#d7dbd2",width=1)
                d.text((a[0]-10,508),str(round(x*1000)),font=small,fill="#5c665f")
            d.text((22,132),"z / mm",font=small,fill="#5c665f")
            d.text((681,532),"x / mm",font=small,fill="#5c665f")
            # Mark the acceptance-bin centre, not a success indicator.
            bx,bz=point(.24,.026)
            d.line(((bx,150),(bx,495)),fill="#a5bacc",width=2)
            d.text((bx-28,146),"bin x",font=small,fill="#466783")
            cx,cz=point(row["cube_x"],row["cube_z"])
            hx,hz=point(row["hand_x"],row["hand_z"])
            tx,tz=point(row["target_x"],row["target_z"])
            d.ellipse((hx-9,hz-9,hx+9,hz+9),outline="#427558",width=4)
            d.rectangle((cx-7,cz-7,cx+7,cz+7),fill="#ac543c")
            d.line(((tx-8,tz),(tx+8,tz)),fill="#697981",width=2)
            d.line(((tx,tz-8),(tx,tz+8)),fill="#697981",width=2)
            d.text((780,155),"Physical contact",font=small,fill="#5c665f")
            contact=row["contacts"].replace("|"," + ") or "none"
            d.multiline_text((780,182),contact.replace(" + ","\n"),font=small,fill="#27372d")
            d.text((780,256),"Bad samples",font=small,fill="#5c665f")
            d.text((780,282),row["bad_streak"],font=font,fill="#27372d")
            d.text((780,335),"ALARM" if row["alarm"]=="1" else "No alarm",font=font,fill="#ac543c" if row["alarm"]=="1" else "#427558")
            d.text((780,390),"Forced open",font=small,fill="#5c665f")
            d.text((780,416),"ON" if row["fault_open"]=="1" else "off",font=font,fill="#27372d")
            d.text((36,563),"Green circle: hand centre    Red square: cube centre    Cross: command target",font=small,fill="#27372d")
            d.text((36,593),"XZ projection only; markers are not robot geometry. No interpolation or new physics.",font=small,fill="#5c665f")
            writer.append_data(np.asarray(frame))
            if not saved and float(row["time"])>=5.22:
                frame.save(folder/"trajectory-poster.png");saved=True
    return {"episode":episode,"frames":len(rows),"fps":50,"video_seconds":len(rows)/50,
            "first_sample_s":float(rows[0]["time"]),"last_sample_s":float(rows[-1]["time"]),
            "kind":"CSV centre-coordinate XZ projection; not a MuJoCo scene recording",
            "csvSha256":hashlib.sha256((folder/"trajectory.csv").read_bytes()).hexdigest(),
            "mediaSha256":hashlib.sha256(target.read_bytes()).hexdigest()}

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("root",type=Path);a=p.parse_args()
    result=[render(a.root,f"forced-open-{mode}-run-1") for mode in ("once","debounced")]
    (a.root/"media.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf8")
    print(json.dumps(result))

