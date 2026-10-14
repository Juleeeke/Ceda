from dataclasses import replace

import pytest

from ceda.config import AnalysisConfig
from ceda.kicad import load_board
from ceda.resources import demo_board,demo_config


@pytest.fixture
def board():
    return load_board(demo_board())


@pytest.fixture
def config():
    config = AnalysisConfig.read(demo_config())
    config.settings.ambient_c = 20
    config.settings.mesh_refinement = False
    config.settings.mesh_size_mm = 0.8
    return config
