from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .errors import CedaError


def main(argv=None):
    parser = argparse.ArgumentParser(prog="ceda",description="Ceda local PCB analysis workbench")
    sub = parser.add_subparsers(dest="command")
    gui = sub.add_parser("gui",help="Open desktop workbench")
    gui.add_argument("--demo",action="store_true")
    gui.add_argument("--screenshot")
    inspect = sub.add_parser("inspect",help="Inspect actual KiCad PCB geometry")
    inspect.add_argument("board")
    inspect.add_argument("--netlist")
    for name in ("analyze","worker"):
        analyze = sub.add_parser(name,help="Analyze a board and write a reproducible report")
        analyze.add_argument("board")
        analyze.add_argument("--config",required=True)
        analyze.add_argument("--output",required=True)
        analyze.add_argument("--netlist")
    demo = sub.add_parser("demo",help="Run the supplied synthetic copper-neck example")
    demo.add_argument("--output",default="outputs/demo")
    spice = sub.add_parser("transient",help="Run optional single-port layout-R / RC startup analysis")
    spice.add_argument("result")
    spice.add_argument("--output",required=True)
    spice.add_argument("--capacitance-uf",type=float,default=10.0)
    spice.add_argument("--esr-ohm",type=float,default=0.05)
    spice.add_argument("--ramp-ms",type=float,default=1.0)
    args = parser.parse_args(argv)
    try:
        if args.command in (None,"gui"):
            from .gui.app import launch
            return launch(getattr(args,"demo",False),getattr(args,"screenshot",None))
        from .kicad import load_board
        if args.command == "inspect":
            board = load_board(args.board)
            data = board.summary()
            if args.netlist:
                from .netlist import compare_netlist
                data["netlist_comparison"] = compare_netlist(board,args.netlist)
            print(json.dumps(data,ensure_ascii=False,indent=2))
            return 2 if any(i.severity == "error" for i in board.issues) else 0
        if args.command == "transient":
            from .spice import run_transient
            result = run_transient(json.loads(Path(args.result).read_text()),args.output,args.capacitance_uf*1e-6,args.esr_ohm,args.ramp_ms*1e-3)
            print(json.dumps(result,ensure_ascii=False,indent=2))
            return 0
        from .config import AnalysisConfig
        from .analysis import analyze
        from .report import write_report
        if args.command == "demo":
            from .resources import demo_board,demo_config
            board = load_board(demo_board())
            config = AnalysisConfig.read(demo_config())
        else:
            board = load_board(args.board)
            config = AnalysisConfig.read(args.config)
        comparison = None
        if getattr(args,"netlist",None):
            from .netlist import compare_netlist
            comparison = compare_netlist(board,args.netlist)
            if comparison["status"] == "fail":
                raise CedaError("原理图导出网表与 PCB 引脚网络不一致。")
        def progress(message):
            print(json.dumps({"event":"progress","message":message},ensure_ascii=False),flush=True)
        result = analyze(board,config,progress)
        if comparison:
            result["netlist_comparison"] = comparison
            result["unverified"] = [item for item in result["unverified"] if "原理图" not in item]
        report_path = write_report(board,result,args.output)
        print(json.dumps({"event":"complete","report":str(report_path),"verdict":result["verdict"],"loads":result["loads"]},ensure_ascii=False),flush=True)
        # Completion and engineering verdict are separate; CI can inspect result.json.
        return 0
    except (CedaError,OSError,ValueError) as exc:
        print(json.dumps({"event":"error","message":str(exc)},ensure_ascii=False),file=sys.stderr,flush=True)
        return 2
