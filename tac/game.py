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

"""This module contains all the classes to represent the TAC game.

Classes:

- GameConfiguration: a class to hold the initial configuration of a game. Immutable.
- Game: the class that manages an instance of a game (e.g. validate and settling transactions).
- GameState: a data structure to hold the current state of a player, plus some he
- GameTransaction: a class that keep information about a transaction in the game.

"""

import copy
import datetime
import pprint
from typing import List, Dict, Any, Optional, Set

from tac.protocol import Transaction

from tac.helpers.misc import compute_endowments, compute_instances_per_good, compute_random_preferences, from_iso_format

Endowment = List[int]  # an element e_i is the endowment for good i.
Utilities = List[int]  # an element u_i is the utility value for good i.


class GameConfiguration:

    def __init__(self, initial_money_amounts: List[int],
                 endowments: List[Endowment],
                 utilities: List[List[int]],
                 fee: int,
                 agent_labels: Optional[List[str]] = None):
        """
        Initialize a game configuration.
        :param initial_money_amounts: the initial amount of money for every agent.
        :param endowments: the endowments of the agents. A matrix where the first index is the agent id
                            and the second index is the good id. A generic element at row i and column j is
                            an integer that denotes the amount of good j for agent i.
        :param utilities: the preferences of the agents. A matrix of integers where a generic element e_ij
                            is the utility of good j for agent i.
        :param fee: the fee for a transaction.
        :param agent_labels: a list of participant labels (as strings). If None, generate a default list of labels.
        """

        self._initial_money_amounts = initial_money_amounts
        self._endowments = endowments
        self._utilities = utilities
        self._fee = fee

        self._agent_labels = agent_labels if agent_labels is not None else self._generate_ids(self.nb_agents)

        self._from_agent_pbk_to_agent_id = dict(map(reversed, enumerate(self.agent_labels)))

        self._check_consistency()

    @property
    def initial_money_amounts(self) -> List[int]:
        return self._initial_money_amounts

    @property
    def endowments(self) -> List[Endowment]:
        return self._endowments

    @property
    def utilities(self) -> List[Utilities]:
        return self._utilities

    @property
    def fee(self) -> int:
        return self._fee

    @property
    def nb_agents(self) -> int:
        return len(self.endowments)

    @property
    def nb_goods(self) -> int:
        return len(self.endowments[0])

    @property
    def agent_labels(self) -> List[str]:
        return self._agent_labels

    def _generate_ids(self, nb_agents: int) -> List[str]:
        """
        Generate ids for the participants.
        :param nb_agents: the number of participants.
        :return: a list of labels.
        """
        return ["agent_{:02}".format(i) for i in range(nb_agents)]

    def agent_id_from_label(self, label: str) -> int:
        """
        From the label of an agent to his id.
        :param label: the label of the agent.
        :return: the integer identifier.
        """
        return self._from_agent_pbk_to_agent_id[label]

    def create_game_states(self) -> List['GameState']:
        return [
            GameState(self.initial_money_amounts[i], self.endowments[i], self.utilities[i])
            for i in range(self.nb_agents)
        ]

    def _check_consistency(self):
        """
        Check the consistency of the game configuration.
        :return: None
        :raises: AssertionError: if some constraint is not satisfied.
        """

        assert all(money >= 0 for money in self.initial_money_amounts) > 0, "All the money must be a non-negative value."
        assert all(e >= 0 for row in self.endowments for e in row), "Endowments must be non-negative."
        assert all(e >= 0 for row in self.utilities for e in row), "Utilities must be non-negative."
        assert self.fee >= 0, "Fee must be non-negative."

        # checks that the data structure have information about the right number of agents
        assert self.nb_agents > 1
        assert self.nb_agents == len(self.initial_money_amounts)
        assert self.nb_agents == len(self.endowments)
        assert self.nb_agents == len(self.utilities)
        assert self.nb_agents == len(self.agent_labels)

        # checks that all the rows have the same dimensions.
        assert self.nb_goods > 0
        assert all(self.nb_goods == len(row) for row in self.endowments)
        assert all(self.nb_goods == len(row) for row in self.utilities)

        assert len(set(self.agent_labels)) == self.nb_agents, "Labels must be unique."

        # check that all the rows of the utility matrix have the same elements and no duplicates
        utilities_values = list(map(set, self.utilities))  # List[Set[int]]
        first_value = utilities_values[0]  # type: Set[int]
        assert len(first_value) == self.nb_goods
        assert all(first_value == value for value in utilities_values)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "initial_money_amounts": self.initial_money_amounts,
            "endowments": self.endowments,
            "utilities": self.utilities,
            "fee": self.fee,
            "agent_labels": self.agent_labels
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'GameConfiguration':
        """Instantiate an object from the dictionary."""

        obj = cls(
            d["initial_money_amounts"],
            d["endowments"],
            d["utilities"],
            d["fee"],
            d["agent_labels"]
        )
        return obj

    def __eq__(self, other):
        return isinstance(other, GameConfiguration) and \
            self.initial_money_amounts == other.initial_money_amounts and \
            self.endowments == other.endowments and \
            self.utilities == other.utilities and \
            self.fee == other.fee


class Game:
    """
    >>> money_amounts = [20, 20, 20]
    >>> endowment = [
    ... [1, 1, 0],
    ... [1, 0, 0],
    ... [0, 1, 2]]
    >>> utilities = [
    ... [20, 40, 60],
    ... [20, 60, 40],
    ... [40, 20, 60]]
    >>> game_configuration = GameConfiguration(
    ...     money_amounts,
    ...     endowment,
    ...     utilities,
    ...     1
    ... )
    >>> game = Game(game_configuration)

    Get the scores:
    >>> game.get_scores()
    [80, 40, 100]
    """

    def __init__(self, configuration: GameConfiguration):
        """
        Initialize a game.
        :param configuration: the game configuration.
        """
        self.configuration = configuration
        self.transactions = []  # type: List[GameTransaction]

        # instantiate the game state for every agent.
        self.game_states = [
            GameState(
                configuration.initial_money_amounts[i],
                configuration.endowments[i],
                configuration.utilities[i]
            )
            for i in range(configuration.nb_agents)]  # type: List[GameState]

    @staticmethod
    def generate_game(initial_money_amounts: List[int],
                      scores: Set[int],
                      fee: int,
                      agent_ids: List[str] = None, g: int = 3) -> 'Game':
        """
        Generate a game, sampling the endowments and the preferences.
        :param initial_money_amounts: the initial amount of money for every agent.
        :param scores: the scores values to generate the agents' preferences.
        :param fee: the fee to pay per transaction.
        :param agent_ids: the labels for the agents.
        :param g:
        :return: a game.
        """
        nb_agents = len(initial_money_amounts)
        nb_goods = len(scores)
        instances_per_good = compute_instances_per_good(nb_goods, nb_agents, g)
        endowments = compute_endowments(nb_agents, instances_per_good)
        preferences = compute_random_preferences(nb_agents, scores)
        configuration = GameConfiguration(initial_money_amounts, endowments, preferences, fee, agent_ids)
        return Game(configuration)

    def get_scores(self) -> List[int]:
        """Get the current scores for every agent."""
        return [gs.get_score() for gs in self.game_states]

    def agent_id_from_label(self, agent_label: str) -> int:
        """
        Get agent id from label.
        :param agent_label: the label for the agent.
        :return: the agent id associated with the label.
        """
        return self.configuration.agent_id_from_label(agent_label)

    def get_game_data_from_agent_label(self, agent_label: str) -> 'GameState':
        """
        Get game data from agent public key.
        :param agent_label: the agent's label.
        :return: the game state of the agent.
        """
        return self.game_states[self.configuration.agent_id_from_label(agent_label)]

    def is_transaction_valid(self, tx: 'GameTransaction') -> bool:
        """
        Check w hether the transaction is valid given the state of the game.
        :param tx: the game transaction.
        :return: True if the transaction is valid, False otherwise.
        :raises: AssertionError: if the data in the transaction are not allowed (e.g. negative amount).
        """

        # check if the buyer has enough balance to pay the transaction.
        if self.game_states[tx.buyer_id].balance < tx.amount + self.configuration.fee:
            return False

        # check if we have enough instances of goods, for every good involved in the transaction.
        seller_holdings = self.game_states[tx.seller_id].current_holdings
        for good_id, bought_quantity in tx.quantities_by_good_id.items():
            if seller_holdings[good_id] < bought_quantity:
                return False

        return True

    def settle_transaction(self, tx: 'GameTransaction') -> None:
        """
        Settle a transaction.

        >>> game = Game(GameConfiguration(
        ... initial_money_amounts = [20, 20],
        ... endowments = [[0, 0], [1, 1]],
        ... utilities = [[10, 20], [10, 20]],
        ... fee = 0))
        >>> game_state_1 = game.game_states[0] # game state of player 1
        >>> game_state_2 = game.game_states[1] # game state of player 2
        >>> game_state_1.balance, game_state_1.current_holdings
        (20, [0, 0])
        >>> game_state_2.balance, game_state_2.current_holdings
        (20, [1, 1])
        >>> game.settle_transaction(GameTransaction(0, 1, 20, {0: 1, 1: 1}))
        >>> game_state_1.balance, game_state_1.current_holdings
        (0, [1, 1])
        >>> game_state_2.balance, game_state_2.current_holdings
        (40, [0, 0])

        :param tx: the game transaction.
        :return: None
        :raises: AssertionError if the transaction is not valid.
        """
        assert self.is_transaction_valid(tx)
        self.transactions.append(tx)
        buyer_state = self.game_states[tx.buyer_id]
        seller_state = self.game_states[tx.seller_id]

        # update holdings
        for good_id, quantity in tx.quantities_by_good_id.items():
            buyer_state.current_holdings[good_id] += quantity
            seller_state.current_holdings[good_id] -= quantity

        # update balances
        buyer_state.balance -= tx.amount
        seller_state.balance += tx.amount

    def get_holdings_summary(self) -> str:
        """
        Get holdings summary.

        >>> money_amounts = [20, 20, 20]
        >>> endowment = [
        ... [1, 1, 0],
        ... [1, 0, 0],
        ... [0, 1, 2]]
        >>> utilities = [
        ... [20, 40, 60],
        ... [20, 60, 40],
        ... [40, 20, 60]]
        >>> game_configuration = GameConfiguration(
        ... money_amounts,
        ... endowment,
        ... utilities,
        ... 1)
        >>> game = Game(game_configuration)
        >>> print(game.get_holdings_summary(), end="")
        00 [1, 1, 0]
        01 [1, 0, 0]
        02 [0, 1, 2]

        :return: a string representing the holdings for every agent.
        """
        result = ""
        for i, game_state in enumerate(self.game_states):
            result = result + "{:02d}".format(i) + " " + str(game_state.current_holdings) + "\n"
        return result

    def to_dict(self) -> Dict[str, Any]:
        return {
            "configuration": self.configuration.to_dict(),
            "transactions": [t.to_dict() for t in self.transactions]
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'Game':
        configuration = GameConfiguration.from_dict(d["configuration"])

        game = Game(configuration)
        for tx_dict in d["transactions"]:
            tx = GameTransaction.from_dict(tx_dict)
            game.settle_transaction(tx)

        return game

    def __eq__(self, other):
        return isinstance(other, Game) and \
                self.configuration == other.configuration and \
                self.transactions == other.transactions


class GameState:
    """Represent the state of an agent during the game."""

    def __init__(self, money: int, endowment: Endowment, utilities: Utilities):
        """
        Instantiate a game state object.

        :param money: the money of the game state.
        :param endowment: the endowment for every good.
        :param utilities: the utility values for every good.
        """
        assert len(endowment) == len(utilities)
        self.balance = money
        self._utilities = utilities
        self.current_holdings = copy.copy(endowment)

        self.nb_goods = len(utilities)

    @property
    def utilities(self) -> Utilities:
        return self._utilities

    def get_score(self) -> int:
        """
        Compute the score of the current state.
        The score is computed as:
        sum of all the holdings with positive quantity, weighted with the associated good score,
        plus the money left.
        :return: the score.
        """
        holdings_score = self.score_good_quantities(self.current_holdings)
        money_score = self.balance
        score = holdings_score + money_score
        return score

    def score_good_quantity(self, good_id: int, quantity: int) -> int:
        """
        Score a quantity for a specified good id.
        :param good_id: the good id associated with the quantity.
        :param quantity: the quantity to be scored.
        :return: the score of the quantity.
        """
        assert 0 <= good_id < self.nb_goods
        assert 0 <= quantity
        return self.utilities[good_id] * (1 if quantity >= 1 else 0)

    def score_good_quantities(self, quantities: List[int]) -> int:
        """
        Score a vector of quantities.
        E.g.
        >>> game_state = GameState(20, [0, 0, 0], [1, 2, 3])
        >>> game_state.score_good_quantities([0, 1, 2])
        5

        :param quantities: the quantities to be scored.
        :return: the score.
        :raises: AssertionError: if the quantities have invalid values (g. invalid good id)
        """
        return sum(self.score_good_quantity(good_id, quantities) for good_id, quantities in enumerate(quantities))

    def get_excess_goods_quantities(self) -> List[int]:
        """
        Return the vector of good quantities in excess. A quantity for a good is in excess if it is more than 1.
        E.g. if an agent holds the good quantities [0, 2, 1], this function returns [0, 1, 0].
        >>> game_state = GameState(20, [1, 2, 3], [20, 40, 60])
        >>> game_state.get_excess_goods_quantities()
        [0, 1, 2]

        :return: the vector of good quantities in excess.
        """
        return [q - 1 if q > 1 else 0 for q in self.current_holdings]

    def _apply_delta_quantitites(self, delta_quantities_by_good_id: Dict[int, int]) -> List[int]:
        """
        Return the new holdings, after applied the variation of quantities provided in input.
        :param delta_quantities_by_good_id:
        :return: the new vector of holdings.
        """
        new_holdings = copy.copy(self.current_holdings)
        for good_id, delta_quantity in delta_quantities_by_good_id.items():
            new_holdings[good_id] += delta_quantity
        return new_holdings

    def get_score_after_transaction(self, delta_money: int, delta_quantities_by_good_id: Dict[int, int]) -> int:
        """
        Simulate a transaction and get the resulting score.

        >>> game_state = GameState(20, [0, 1, 2], [20, 40, 60])
        >>> game_state.get_score()  # gives: money + weighted_holdings = 20 * (0*20 + 1*40 + 1*60)
        120
        >>> game_state.get_score_after_transaction(-10, {0: 1})  # add an holding for the first good and pay 10.
        130

        :param delta_money: the delta amount of money.
                            A negative value means that we pay money in the transaction.
                            A positive value means that we gain money from the transaction.
        :param delta_quantities_by_good_id: a map from good ids to delta quantities.
                               A negative value ``q`` with key ``i`` means that we sold ``q`` instances of good ``i``.
                               A positive value ``q`` with key``i`` means that we bought ``q`` instances of good ``i``.
        :return: the score that we would get if the transaction is confirmed.
        :raises: AssertionError: if we cannot update the state with the proposed changes.
        """
        self._check_update(delta_money, delta_quantities_by_good_id)
        # create a new (temporary) holdings
        new_holdings = self._apply_delta_quantitites(delta_quantities_by_good_id)
        new_holdings_score = self.score_good_quantities(new_holdings)
        new_money = self.balance + delta_money
        return new_holdings_score + new_money

    def update(self, tx: Transaction) -> None:
        """
        Update the game state from a transaction request.
        :param tx: the transaction request message.
        :return: None
        """
        switch = -1 if tx.buyer else 1
        self.balance += switch * tx.amount
        for good_id, quantity in tx.quantities_by_good_id.items():
            self.current_holdings[good_id] += -switch * quantity

    def _check_update(self, delta_money: int, delta_quantities_by_good_id: Dict[int, int]) -> None:
        """
        Check if the update is consistent. E.g. check that the game state has enough money and enough holdings.

        :param delta_money: the difference of money between the new and the old balance.
        :param delta_quantities_by_good_id: a map from good ids to delta quantities.
        :return: None
        :raises: AssertionError: if the update does not satisfy some constraints.
        """

        # check if we have enough money.
        assert delta_money >= 0 or self.balance >= abs(delta_money), "Not enough money."

        # check if we have enough good instances.
        for good_id, delta_quantity in delta_quantities_by_good_id.items():
            # if the delta is negative, check that we have enough good instances for the transaction.
            assert delta_quantity >= 0 or self.current_holdings[good_id] >= abs(delta_quantity), "Not enough good instances."

    def __str__(self):
        return "GameState{}".format(pprint.pformat({
            "money": self.balance,
            "scores": self.utilities,
            "current_holdings": self.current_holdings
        }))

    def __eq__(self, other) -> bool:
        return isinstance(other, GameState) and \
               self.balance == other.balance and \
               self.utilities == other.utilities and \
               self.current_holdings == other.current_holdings


class GameTransaction:
    """Represent a transaction between agents"""

    def __init__(self, buyer_id: int, seller_id: int, amount: int, quantities_by_good_id: Dict[int, int],
                 timestamp: Optional[datetime.datetime] = None):
        """
        Instantiate a game transaction object.

        :param buyer_id: the participant id of the buyer in the game.
        :param seller_id: the participant id of the seller in the game.
        :param amount: the amount transferred.
        :param quantities_by_good_id: a map from good id to the quantity transacted.
        :param timestamp: the timestamp of the transaction.
        """
        self.buyer_id = buyer_id
        self.seller_id = seller_id
        self.amount = amount
        self.quantities_by_good_id = quantities_by_good_id
        self.timestamp = datetime.datetime.now() if timestamp is None else timestamp

        self._check_consistency()

    def _check_consistency(self):
        """
        Check the consistency of the transaction parameters.
        :return: None
        :raises AssertionError if some constraint is not satisfied.
        """

        assert self.buyer_id != self.seller_id
        assert self.amount > 0
        assert all(good_id >= 0 for good_id in self.quantities_by_good_id.keys())
        assert all(quantity >= 0 for quantity in self.quantities_by_good_id.values())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "buyer_id": self.buyer_id,
            "seller_id": self.seller_id,
            "amount": self.amount,
            "quantities_by_good_id": self.quantities_by_good_id,
            "timestamp": str(self.timestamp)
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'GameTransaction':
        # make the keys as integers
        quantities_by_good_id = {int(k): v for k, v in d["quantities_by_good_id"].items()}

        return cls(
            buyer_id=d["buyer_id"],
            seller_id=d["seller_id"],
            amount=d["amount"],
            quantities_by_good_id=quantities_by_good_id,
            timestamp=from_iso_format(d["timestamp"])
        )

    def __eq__(self, other) -> bool:
        return isinstance(other, GameTransaction) and \
               self.buyer_id == other.buyer_id and \
               self.seller_id == other.seller_id and \
               self.amount == other.amount and \
               self.quantities_by_good_id == other.quantities_by_good_id and \
               self.timestamp == other.timestamp
