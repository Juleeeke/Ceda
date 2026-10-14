"""Compare KiCad exported XML design intent against PCB pad assignments."""
import xml.etree.ElementTree as ET
from pathlib import Path

from .errors import CedaError


def compare_netlist(board,path):
    try:
        root = ET.fromstring(Path(path).read_text(encoding="utf-8"))
    except (OSError,ET.ParseError) as exc:
        raise CedaError(f"无法读取 KiCad XML 网表：{exc}") from exc
    if root.tag != "export" or root.find("nets") is None:
        raise CedaError("需要 KiCad 导出的 XML 网表（export/nets）。")
    expected = {}
    for net in root.findall("./nets/net"):
        for node in net.findall("node"):
            expected[f"{node.get('ref')}.{node.get('pin')}"] = net.get("name","")
    actual = {pad.id:pad.net for pad in board.pads}
    differences = []
    for identifier,net in expected.items():
        if identifier not in actual:
            differences.append({"pad":identifier,"status":"missing_on_pcb","expected":net})
        elif actual[identifier] != net:
            differences.append({"pad":identifier,"status":"net_mismatch","expected":net,"actual":actual[identifier]})
    for identifier,net in actual.items():
        if identifier not in expected and net:
            differences.append({"pad":identifier,"status":"missing_in_netlist","actual":net})
    return {"status":"pass" if not differences else "fail","scope":"pad net assignments; not full ERC/DRC",
            "path":str(Path(path).resolve()),"differences":differences}
