from importlib.resources import files


def demo_board():
    return files("ceda").joinpath("resources/demo.kicad_pcb")


def demo_config():
    return files("ceda").joinpath("resources/demo.json")


def app_icon():
    return files("ceda").joinpath("resources/icons/ceda-icon.png")
