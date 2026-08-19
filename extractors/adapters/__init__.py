# -*- coding: utf-8 -*-
"""
Adapters de Casos de Uso Especializados do Motor de Extração
"""

from extractors.adapters.general_spatial_adapter import GeneralSpatialAdapter
from extractors.adapters.flyer_product_adapter import FlyerProductAdapter, FlyerProductResolver

__all__ = ["GeneralSpatialAdapter", "FlyerProductAdapter", "FlyerProductResolver"]
