# -*- coding: utf-8 -*-

# ------------------------------------------------------------------------------
#
#   Copyright 2018-2019 Fetch.AI Limited
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
#
# ------------------------------------------------------------------------------

"""This module contains helper methods for base agent implementations."""
import logging
from typing import Dict, List, Set, Union

from oef.query import Query, Constraint, GtEq, Or
from oef.schema import AttributeSchema, DataModel, Description

from tac.aea.crypto.base import Crypto
from tac.aea.dialogue.base import DialogueLabel
from tac.aea.mail.messages import OEFMessage, FIPAMessage
from tac.aea.mail.protocol import Envelope
from tac.platform.protocol import Response

logger = logging.getLogger(__name__)


TAC_SUPPLY_DATAMODEL_NAME = "tac_supply"
TAC_DEMAND_DATAMODEL_NAME = "tac_demand"
QUANTITY_SHIFT = 1  # Any non-negative integer is fine.


def is_oef_message(msg: Envelope) -> bool:
    """
    Check whether a message is from the oef.

    :param msg: the message
    :return: boolean indicating whether or not the message is from the oef
    """
    return msg.protocol_id == "oef" and msg.message.get("type") in set(OEFMessage.Type)


def is_controller_message(msg: Envelope, crypto: Crypto) -> bool:
    """
    Check whether a message is from the controller.

    :param msg: the message
    :param crypto: the crypto of the agent
    :return: boolean indicating whether or not the message is from the controller
    """
    if not msg.protocol_id == "bytes":
        return False

    try:
        byte_content = msg.message.get("content")
        sender_pbk = msg.sender
        Response.from_pb(byte_content, sender_pbk, crypto)
    except Exception as e:
        logger.debug("Not a Controller message: {}".format(str(e)))
        # try:
        #     byte_content = msg.get("content")
        #     sender_pbk = msg.sender
        #     Response.from_pb(byte_content, sender_pbk, crypto)
        # except:
        #     pass
        return False

    return True


def is_fipa_message(msg: Envelope) -> bool:
    """Chcek whether a message is a FIPA message."""
    return msg.protocol_id == "fipa" and msg.message.get("performative") in set(FIPAMessage.Performative)


def generate_transaction_id(agent_pbk: str, opponent_pbk: str, dialogue_label: DialogueLabel, agent_is_seller: bool) -> str:
    """
    Make a transaction id.

    :param agent_pbk: the pbk of the agent.
    :param opponent_pbk: the public key of the opponent.
    :param dialogue_label: the dialogue label
    :param agent_is_seller: boolean indicating if the agent is a seller
    :return: a transaction id
    """
    # the format is {buyer_pbk}_{seller_pbk}_{dialogue_id}_{dialogue_starter_pbk}
    assert opponent_pbk == dialogue_label.dialogue_opponent_pbk
    buyer_pbk, seller_pbk = (opponent_pbk, agent_pbk) if agent_is_seller else (agent_pbk, opponent_pbk)
    transaction_id = "{}_{}_{}_{}".format(buyer_pbk, seller_pbk, dialogue_label.dialogue_id, dialogue_label.dialogue_starter_pbk)
    return transaction_id


def dialogue_label_from_transaction_id(agent_pbk: str, transaction_id: str) -> DialogueLabel:
    """
    Recover dialogue label from transaction id.

    :param agent_pbk: the pbk of the agent.
    :param transaction_id: the transaction id
    :return: a dialogue label
    """
    buyer_pbk, seller_pbk, dialogue_id, dialogue_starter_pbk = transaction_id.split('_')
    if agent_pbk == buyer_pbk:
        dialogue_opponent_pbk = seller_pbk
    else:
        dialogue_opponent_pbk = buyer_pbk
    dialogue_label = DialogueLabel(int(dialogue_id), dialogue_opponent_pbk, dialogue_starter_pbk)
    return dialogue_label


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
