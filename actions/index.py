from typing import Dict
from actions.base import BaseAction
from actions.fetch_market import FetchMarketAction
from actions.create_pool import CreatePoolAction
from actions.adjust_risk import AdjustRiskAction
from actions.compound import CompoundAction
from actions.add_liquidity import AddLiquidityAction

def get_available_actions() -> Dict[str, BaseAction]:
    """Returns a dictionary of all available actions"""
    actions = {}
    for action_class in [CreatePoolAction, AdjustRiskAction, CompoundAction, FetchMarketAction, AddLiquidityAction]:
        action = action_class()
        actions[action.intent_name] = action
    return actions 