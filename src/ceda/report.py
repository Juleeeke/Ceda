from __future__ import annotations

import csv
import html
import json
from pathlib import Path

import numpy as np
from shapely.geometry import Polygon


def color(value, minimum, maximum):
    ratio = min(1,max(0,(value-minimum)/max(maximum-minimum,1e-12)))
    stops = [(232,237,243),(161,183,212),(90,136,185),(239,182,132),(212,107,85)]
    scaled = ratio*(len(stops)-1)
    i = min(int(scaled),len(stops)-2)
    f = scaled-i
    rgb = [round(stops[i][j]*(1-f)+stops[i+1][j]*f) for j in range(3)]
    return "#"+"".join(f"{c:02x}" for c in rgb)


def board_svg(board,report=None,layer=None,field="current_density",width=1000):
    bounds = board.outline.bounds if board.outline is not None else np.array([p.bounds for p in board.copper.values()]).reshape(-1,4)
    if not isinstance(bounds,tuple):
        bounds = (bounds[:,0].min(),bounds[:,1].min(),bounds[:,2].max(),bounds[:,3].max())
    x0,y0,x1,y1 = bounds
    margin = max(x1-x0,y1-y0)*0.05
    height = round(width*(y1-y0+2*margin)/(x1-x0+2*margin))
    body = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="{x0-margin} {y0-margin} {x1-x0+2*margin} {y1-y0+2*margin}">',
            f'<rect x="{x0-margin}" y="{y0-margin}" width="{x1-x0+2*margin}" height="{y1-y0+2*margin}" fill="#ffffff"/>']
    def path(shape,fill,stroke="none"):
        polygons = [shape] if isinstance(shape,Polygon) else list(shape.geoms)
        for polygon in polygons:
            commands = []
            for ring in [polygon.exterior,*polygon.interiors]:
                commands.append("M "+" L ".join(f"{x:.6g},{y:.6g}" for x,y in ring.coords)+" Z")
            body.append(f'<path d="{" ".join(commands)}" fill="{fill}" fill-rule="evenodd" stroke="{stroke}" stroke-width="0.08"/>')
    if board.outline is not None:
        path(board.outline,"#fafbfc","#bbc3cf")
    for (net,name),geometry in board.copper.items():
        if layer is None or name == layer:
            path(geometry,"#b6c7d4")
    if report:
        mesh = report["mesh"]
        values = mesh["current_density_a_mm2"] if field == "current_density" else np.mean(np.array(mesh["voltage_v"])[mesh["triangles"]],axis=1)
        indices = [i for i,key in enumerate(mesh["triangle_keys"]) if layer is None or key[1] == layer]
        if indices:
            minimum,maximum = min(values[i] for i in indices),max(values[i] for i in indices)
            for i in indices:
                coords = [mesh["points_mm"][n] for n in mesh["triangles"][i]]
                body.append('<polygon points="'+' '.join(f'{x:.6g},{y:.6g}' for x,y in coords)+f'" fill="{color(values[i],minimum,maximum)}"/>')
    for pad in board.pads:
        if layer is None or layer in pad.layers:
            path(pad.geometry,"none","#778394")
            body.append(f'<text x="{pad.x+0.2}" y="{pad.y-0.3}" font-family="sans-serif" font-size="0.65" fill="#535f70">{html.escape(pad.id)}</text>')
    body.append("</svg>")
    return "\n".join(body)


def write_report(board,report,output):
    output = Path(output).resolve()
    output.mkdir(parents=True,exist_ok=True)
    (output/"result.json").write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding="utf-8")
    (output/"config.json").write_text(json.dumps(report["config"],ensure_ascii=False,indent=2),encoding="utf-8")
    # Snapshot matches the hash recorded in the result; never modify originals.
    snapshot = output/"input.kicad_pcb"
    if snapshot.resolve() != board.path.resolve():
        import hashlib
        raw = board.path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != board.sha256:
            from .errors import CedaError
            raise CedaError("原始 PCB 在分析期间已变更；不能保存错误的输入快照。")
        snapshot.write_bytes(raw)
    mesh = report["mesh"]
    with (output/"field.csv").open("w",encoding="utf-8",newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["net","layer","x_mm","y_mm","voltage_v","current_density_a_mm2","loss_w"])
        for i,tri in enumerate(mesh["triangles"]):
            center = np.array([mesh["points_mm"][n] for n in tri]).mean(axis=0)
            voltage = float(np.mean([mesh["voltage_v"][n] for n in tri]))
            writer.writerow([*mesh["triangle_keys"][i],*center,voltage,mesh["current_density_a_mm2"][i],mesh["triangle_loss_w"][i]])
    visuals = []
    for layer in board.layers:
        svg = board_svg(board,report,layer.name)
        (output/f"{layer.name}-current.svg").write_text(svg,encoding="utf-8")
        visuals.append(f"<h3>{html.escape(layer.name)} · 电流密度</h3>{svg}")
    escaped = lambda value: html.escape(str(value))
    rows = "".join(f"<tr><td>{escaped(l['label'])}</td><td>{escaped(l['positive'])} → {escaped(l['negative'])}</td><td>{l['voltage_v']:.6f} V</td><td>{escaped(l['minimum_voltage_v'])}</td><td>{escaped(l['verdict'])}</td></tr>" for l in report["loads"])
    thermal = report.get("thermal")
    heat = f"<p>实验性板温估算最高 {thermal['maximum_board_c']:.2f} °C；{escaped(thermal['coupling_status'])}。不包含结温验证。</p>" if thermal else "<p>热分析未运行。</p>"
    markup = f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>Ceda PCB 分析报告</title>
<style>body{{background:#fff;color:#303844;font:14px system-ui,sans-serif;max-width:1100px;margin:40px auto;padding:20px}}h1,h2{{color:#252d37;font-weight:600}}h1{{font-size:26px}}h2{{font-size:18px;margin-top:32px}}h3{{font-size:14px;color:#6f7c8d;font-weight:500}}table{{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}}td,th{{padding:12px;text-align:left;border-bottom:1px solid #e9edf2}}th{{color:#8a95a4;font-weight:400}}svg{{max-width:100%;height:auto}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;color:#7d8896;font-size:12px;background:#fafbfc;padding:16px;border:1px solid #edf0f4;border-radius:5px}}.badge{{padding:9px 12px;background:#f8f9fb;border:1px solid #e9edf2;border-radius:5px;color:#677486}}p,li{{line-height:1.8}}</style>
<h1>Ceda · PCB 后布局分析</h1><p>{escaped(report['config']['name'])}</p><p class="badge">{escaped(report['verdict'])} · 仅对已配置 DC 工况判定 · 无实测校准</p>
<h2>负载端供电</h2><table><tr><th>负载</th><th>端口</th><th>本地 VDD–GND</th><th>最低电压/V</th><th>判定</th></tr>{rows}</table>
<h2>数值质量</h2><pre>{escaped(json.dumps(report['diagnostics'],ensure_ascii=False,indent=2))}</pre><h3>网格细化</h3><pre>{escaped(json.dumps(report['mesh_refinement'],ensure_ascii=False,indent=2))}</pre>
<h2>热分析</h2>{heat}<h2>布局结果</h2>{''.join(visuals)}<p>颜色按每层范围归一化；尖角峰值不等于通用载流上限。</p>
<h2>未验证范围</h2><ul>{''.join('<li>'+escaped(item)+'</li>' for item in report['unverified'])}</ul>
<h2>模型假设</h2><ul>{''.join('<li>'+escaped(item)+'</li>' for item in report['assumptions'])}</ul>
<h2>复现信息</h2><pre>PCB SHA-256: {escaped(board.sha256)}\nConfig SHA-256: {escaped(report['config_sha256'])}\nCeda: {escaped(report['ceda_version'])}\n{escaped(report['solver_versions'])}\n{escaped(report['platform'])}</pre></html>"""
    (output/"report.html").write_text(markup,encoding="utf-8")
    return output/"report.html"
