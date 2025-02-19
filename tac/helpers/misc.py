# -*- coding: utf-8 -*-

# ------------------------------------------------------------------------------
#
#   Copyright 2018-2019 Fetch.AI Limited
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
#
# ------------------------------------------------------------------------------

"""A module containing miscellaneous methods and classes."""

import logging
import random
from typing import List, Set, Dict, Tuple, Union

import math
import numpy as np
from oef.query import Query, Constraint, GtEq, Or
from oef.schema import AttributeSchema, DataModel, Description


logger = logging.getLogger("tac")
TAC_SUPPLY_DATAMODEL_NAME = "tac_supply"
TAC_DEMAND_DATAMODEL_NAME = "tac_demand"
QUANTITY_SHIFT = 1  # Any non-negative integer is fine.


class TacError(Exception):
    """General purpose exception to detect exception associated with the logic of the TAC application."""


def generate_transaction_id(agent_pbk: str, origin: str, dialogue_id: int, agent_is_seller: bool) -> str:
    """
    Generate a transaction id.

    :param agent_pbk: the pbk of the agent.
    :param origin: the public key of the message sender.
    :param dialogue_id: the dialogue id
    :param agent_is_seller: boolean indicating if the agent is a seller
    :return: a transaction id
    """
    # the format is {buyer_pbk}_{seller_pbk}_{dialogue_id}
    buyer_pbk, seller_pbk = (origin, agent_pbk) if agent_is_seller else (agent_pbk, origin)
    transaction_id = "{}_{}_{}".format(buyer_pbk, seller_pbk, dialogue_id)
    return transaction_id


def determine_scaling_factor(money_endowment: int) -> float:
    """
    Compute the scaling factor based on the money amount.

    :param money_endowment: the endowment of money for the agent
    :return: the scaling factor
    """
    scaling_factor = 10.0 ** (len(str(money_endowment)) - 1)
    return scaling_factor


def generate_good_endowments(nb_goods: int, nb_agents: int, base_amount: int, uniform_lower_bound_factor: int, uniform_upper_bound_factor: int) -> List[List[int]]:
    """
    Compute good endowments per agent. That is, a matrix of shape (nb_agents, nb_goods).

    :param nb_goods: the number of goods.
    :param nb_agents: the number of agents.
    :param base_amount: the base amount of instances per good
    :param uniform_lower_bound_factor: the lower bound of the uniform distribution for the sampling of the good instance number.
    :param uniform_upper_bound_factor: the upper bound of the uniform distribution for the sampling of the good instance number.
    :return: the endowments matrix.
    """
    # sample good instances
    instances_per_good = _sample_good_instances(nb_agents, nb_goods, base_amount,
                                                uniform_lower_bound_factor, uniform_upper_bound_factor)
    # each agent receives at least two good
    endowments = [[base_amount] * nb_goods for _ in range(nb_agents)]
    # randomly assign additional goods to create differences
    for good_id in range(nb_goods):
        for _ in range(instances_per_good[good_id] - (base_amount * nb_agents)):
            agent_id = random.randint(0, nb_agents - 1)
            endowments[agent_id][good_id] += 1
    return endowments


def generate_utility_params(nb_agents: int, nb_goods: int, scaling_factor: float) -> List[List[float]]:
    """
    Compute the preference matrix. That is, a generic element e_ij is the utility of good j for agent i.

    :param nb_agents: the number of agents.
    :param nb_goods: the number of goods.
    :param scaling_factor: a scaling factor for all the utility params generated.
    :return: the preference matrix.
    """
    utility_params = _sample_utility_function_params(nb_goods, nb_agents, scaling_factor)
    return utility_params


def _sample_utility_function_params(nb_goods: int, nb_agents: int, scaling_factor: float) -> List[List[float]]:
    """
    Sample utility function params for each agent.

    :param nb_goods: the number of goods
    :param nb_agents: the number of agents
    :param scaling_factor: a scaling factor for all the utility params generated.
    :return: a matrix with utility function params for each agent
    """
    decimals = 4 if nb_goods < 100 else 8
    utility_function_params = []
    for i in range(nb_agents):
        random_integers = [random.randint(1, 101) for _ in range(nb_goods)]
        total = sum(random_integers)
        normalized_fractions = [round(i / float(total), decimals) for i in random_integers]
        if not sum(normalized_fractions) == 1.0:
            normalized_fractions[-1] = round(1.0 - sum(normalized_fractions[0:-1]), decimals)
        utility_function_params.append(normalized_fractions)

    # scale the utility params
    for i in range(len(utility_function_params)):
        for j in range(len(utility_function_params[i])):
            utility_function_params[i][j] *= scaling_factor

    return utility_function_params


def _sample_good_instances(nb_agents: int, nb_goods: int, base_amount: int,
                           uniform_lower_bound_factor: int, uniform_upper_bound_factor: int) -> List[int]:
    """
    Sample the number of instances for a good.

    :param nb_agents: the number of agents
    :param nb_goods: the number of goods
    :param base_amount: the base amount of instances per good
    :param uniform_lower_bound_factor: the lower bound factor of a uniform distribution
    :param uniform_upper_bound_factor: the upper bound factor of a uniform distribution
    :return: the number of instances I sampled.
    """
    a = base_amount * nb_agents + nb_agents * uniform_lower_bound_factor
    b = base_amount * nb_agents + nb_agents * uniform_upper_bound_factor
    # Return random integer in range [a, b]
    nb_instances = [round(np.random.uniform(a, b)) for _ in range(nb_goods)]
    return nb_instances


def generate_money_endowments(nb_agents: int, money_endowment: int) -> List[int]:
    """
    Compute the initial money amounts for each agent.

    :param nb_agents: number of agents.
    :param money_endowment: money endowment per agent.
    :return: the list of initial money amounts.
    """
    return [money_endowment] * nb_agents


def generate_equilibrium_prices_and_holdings(endowments: List[List[int]], utility_function_params: List[List[float]], money_endowment: float, scaling_factor: float, quantity_shift: int = QUANTITY_SHIFT) -> Tuple[List[float], List[List[float]], List[float]]:
    """
    Compute the competitive equilibrium prices and allocation.

    :param endowments: endowments of the agents
    :param utility_function_params: utility function params of the agents (already scaled)
    :param money_endowment: money endowment per agent.
    :param scaling_factor: a scaling factor for all the utility params generated.
    :param quantity_shift: a factor to shift the quantities in the utility function (to ensure the natural logarithm can be used on the entire range of quantities)
    :return: the lists of equilibrium prices, equilibrium good holdings and equilibrium money holdings
    """
    endowments_a = np.array(endowments, dtype=np.int)
    scaled_utility_function_params_a = np.array(utility_function_params, dtype=np.float)  # note, they are already scaled
    endowments_by_good = np.sum(endowments_a, axis=0)
    scaled_params_by_good = np.sum(scaled_utility_function_params_a, axis=0)
    eq_prices = np.divide(scaled_params_by_good, quantity_shift * len(endowments) + endowments_by_good)
    eq_good_holdings = np.divide(scaled_utility_function_params_a, eq_prices) - quantity_shift
    eq_money_holdings = np.transpose(np.dot(eq_prices, np.transpose(endowments_a + quantity_shift))) + money_endowment - scaling_factor
    return eq_prices.tolist(), eq_good_holdings.tolist(), eq_money_holdings.tolist()


def logarithmic_utility(utility_function_params: List[float], good_bundle: List[int], quantity_shift: int = QUANTITY_SHIFT) -> float:
    """
    Compute agent's utility given her utility function params and a good bundle.

    :param utility_function_params: utility function params of the agent
    :param good_bundle: a bundle of goods with the quantity for each good
    :param quantity_shift: a factor to shift the quantities in the utility function (to ensure the natural logarithm can be used on the entire range of quantities)
    :return: utility value
    """
    goodwise_utility = [param * math.log(quantity + quantity_shift) if quantity + quantity_shift > 0 else -10000
                        for param, quantity in zip(utility_function_params, good_bundle)]
    return sum(goodwise_utility)


def marginal_utility(utility_function_params: List[float], current_holdings: List[int], delta_holdings: List[int]) -> float:
    """
    Compute agent's utility given her utility function params and a good bundle.

    :param utility_function_params: utility function params of the agent
    :param current_holdings: a list of goods with the quantity for each good
    :param delta_holdings: a list of goods with the quantity for each good (can be positive or negative)
    :return: utility difference between new and current utility
    """
    current_utility = logarithmic_utility(utility_function_params, current_holdings)
    new_holdings = [sum(x) for x in zip(current_holdings, delta_holdings)]
    new_utility = logarithmic_utility(utility_function_params, new_holdings)
    return new_utility - current_utility


def build_datamodel(good_pbks: List[str], is_supply: bool) -> DataModel:
    """
    Build a data model for supply and demand (i.e. for offered or requested goods).

    :param good_pbks: the list of good public keys
    :param is_supply: Boolean indicating whether it is a supply or demand data model

    :return: the data model.
    """
    goods_quantities_attributes = [AttributeSchema(good_pbk, int, False)
                                   for good_pbk in good_pbks]
    price_attribute = AttributeSchema("price", float, False)
    description = TAC_SUPPLY_DATAMODEL_NAME if is_supply else TAC_DEMAND_DATAMODEL_NAME
    data_model = DataModel(description, goods_quantities_attributes + [price_attribute])
    return data_model


def get_goods_quantities_description(good_pbks: List[str], good_quantities: List[int], is_supply: bool) -> Description:
    """
    Get the TAC description for supply or demand.

    That is, a description with the following structure:
    >>> description = {
    ...     "tac_good_0": 1,
    ...     "tac_good_1": 0,
    ...     #...
    ...
    ... }
    >>>

     where the keys indicate the good_pbk and the values the quantity.

     >>> desc = get_goods_quantities_description(['tac_good_0', 'tac_good_1', 'tac_good_2', 'tac_good_3'], [0, 0, 1, 2], True)
     >>> desc.data_model.name == TAC_SUPPLY_DATAMODEL_NAME
     True
     >>> desc.values == {
     ...    "tac_good_0": 0,
     ...    "tac_good_1": 0,
     ...    "tac_good_2": 1,
     ...    "tac_good_3": 2}
     ...
     True

    :param good_pbks: the public keys of the goods.
    :param good_quantities: the quantities per good.
    :param is_supply: True if the description is indicating supply, False if it's indicating demand.

    :return: the description to advertise on the Service Directory.
    """
    data_model = build_datamodel(good_pbks, is_supply=is_supply)
    desc = Description({good_pbk: quantity for good_pbk, quantity in zip(good_pbks, good_quantities)},
                       data_model=data_model)
    return desc


def build_query(good_pbks: Set[str], is_searching_for_sellers: bool) -> Query:
    """
    Build buyer or seller search query.

    Specifically, build the search query
        - to look for sellers if the agent is a buyer, or
        - to look for buyers if the agent is a seller.

    In particular, if the agent is a buyer and the demanded good public keys are {'tac_good_0', 'tac_good_2', 'tac_good_3'}, the resulting constraint expression is:

        tac_good_0 >= 1 OR tac_good_2 >= 1 OR tac_good_3 >= 1

    That is, the OEF will return all the sellers that have at least one of the good in the query
    (assuming that the sellers are registered with the data model specified).

    :param good_pbks: the good public keys to put in the query
    :param is_searching_for_sellers: Boolean indicating whether the query is for sellers (supply) or buyers (demand).

    :return: the query
    """
    data_model = None if good_pbks is None else build_datamodel(list(good_pbks), is_supply=is_searching_for_sellers)
    constraints = [Constraint(good_pbk, GtEq(1)) for good_pbk in good_pbks]

    if len(good_pbks) > 1:
        constraints = [Or(constraints)]

    query = Query(constraints, model=data_model)
    return query


def build_dict(good_pbks: Set[str], is_supply: bool) -> Dict[str, Union[str, List]]:
    """
    Build supply or demand services dictionary.

    :param good_pbks: the good public keys to put in the query
    :param is_supply: Boolean indicating whether the services are for supply or demand.

    :return: the dictionary
    """
    description = TAC_SUPPLY_DATAMODEL_NAME if is_supply else TAC_DEMAND_DATAMODEL_NAME
    result = {'description': description, 'services': list(good_pbks)}
    return result


def generate_good_pbk_to_name(nb_goods: int) -> Dict[str, str]:
    """
    Generate public keys for things.

    :param nb_goods: the number of things.
    :return: a dictionary mapping goods' public keys to names.
    """
    max_number_of_digits = math.ceil(math.log10(nb_goods))
    string_format = 'tac_good_{:0' + str(max_number_of_digits) + '}'
    return {string_format.format(i) + '_pbk': string_format.format(i) for i in range(nb_goods)}


def generate_html_table_from_dict(dictionary: Dict[str, List[str]], title="") -> str:
    """
    Generate a html table from a dictionary.

    :param dictionary: the dictionary
    :param title: the title
    :return: a html string
    """
    style_tag = "<style>table, th, td{border: 1px solid black;padding:10px;}</style>"
    html_head = "<head>{}</head>".format(style_tag)
    title_tag = "<h2>{}</h2>".format(title) if title else ""

    table_head = "<tr><th>{}</th></tr>".format("</th><th>".join(dictionary.keys()))
    table_body = ""
    for row in zip(*dictionary.values()):
        table_row = "<tr><td>" + "</td><td>".join(row) + "</td></tr>"
        table_body += table_row

    table = "<table>{}{}</table>".format(table_head, table_body)

    html_table = "<html>" + html_head + title_tag + table + "</html>"

    return html_table


def escape_html(string: str, quote=True) -> str:
    """
    Replace special characters "&", "<" and ">" to HTML-safe sequences.

    :param string: the string
    :param quote: If the optional flag quote is true (the default), the quotation mark characters, both double quote (") and single quote (') characters are also translated.

    :return: the escaped string
    """
    string = string.replace("&", "&amp;")  # Must be done first!
    string = string.replace("<", "&lt;")
    string = string.replace(">", "&gt;")
    if quote:
        string = string.replace('"', "&quot;")
        string = string.replace('\'', "&#x27;")
    return string
