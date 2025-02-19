#!/usr/bin/env python3
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

"""
This module implements a TAC simulation.

It spawn a controller agent that handles the competition and
several baseline agents that will participate to the competition.

It requires an OEF node running and a Visdom server, if the visualization is desired.

You can also run it as a script. To check the available arguments:

    python3 -m tac.platform.simulation -h

"""

import argparse
import datetime
import logging
import math
import multiprocessing
import pprint
import random
import time
from typing import Optional, List

import dateutil

from tac.agents.v1.base.strategy import RegisterAs, SearchFor
from tac.agents.v1.examples.baseline import main as baseline_main
from tac.platform.controller import TACParameters
from tac.platform.controller import main as controller_main

logger = logging.getLogger(__name__)


class SimulationParams:
    """Class to hold simulation parameters."""

    def __init__(self,
                 oef_addr: str = "localhost",
                 oef_port: int = 10000,
                 nb_baseline_agents: int = 5,
                 register_as: RegisterAs = RegisterAs.BOTH,
                 search_for: SearchFor = SearchFor.BOTH,
                 services_interval: int = 5,
                 pending_transaction_timeout: int = 120,
                 verbose: bool = False,
                 dashboard: bool = False,
                 visdom_addr: str = "localhost",
                 visdom_port: int = 8097,
                 data_output_dir: Optional[str] = "data",
                 experiment_id: int = None,
                 seed: int = 42,
                 tac_parameters: Optional[TACParameters] = None):
        """
        Initialize a SimulationParams class.

        :param oef_addr: the IP address of the OEF.
        :param oef_port: the port of the OEF.
        :param nb_baseline_agents: the number of baseline agents to spawn.
        :param register_as: the registration policy the agents will follow.
        :param search_for: the search policy the agents will follow.
        :param services_interval: The amount of time (in seconds) the baseline agents wait until it updates services again.
        :param pending_transaction_timeout: The amount of time (in seconds) the baseline agents wait until the transaction confirmation.
        :param verbose: control the verbosity of the simulation.
        :param dashboard: enable the Visdom visualization.
        :param visdom_addr: the IP address of the Visdom server
        :param visdom_port: the port of the Visdom server.
        :param data_output_dir: the path to the output directory.
        :param experiment_id: the name of the experiment.
        :param seed: the random seed.
        :param tac_parameters: the parameters for the TAC.
        """
        self.tac_parameters = tac_parameters if tac_parameters is not None else TACParameters()
        self.oef_addr = oef_addr
        self.oef_port = oef_port
        self.nb_baseline_agents = nb_baseline_agents
        self.register_as = register_as
        self.search_for = search_for
        self.services_interval = services_interval
        self.pending_transaction_timeout = pending_transaction_timeout
        self.verbose = verbose
        self.dashboard = dashboard
        self.visdom_addr = visdom_addr
        self.visdom_port = visdom_port
        self.data_output_dir = data_output_dir
        self.experiment_id = experiment_id
        self.seed = seed


def _make_id(agent_id: int, is_world_modeling: bool, nb_agents: int) -> str:
    """
    Make the name for baseline agents from an integer identifier.

    E.g.:

    >>> _make_id(2, False, 10)
    'tac_agent_2'
    >>> _make_id(2, False, 100)
    'tac_agent_02'
    >>> _make_id(2, False, 101)
    'tac_agent_002'

    :param agent_id: the agent id.
    :param is_world_modeling: the boolean indicated whether the baseline agent models the world around her or not.
    :param nb_agents: the overall number of agents.
    :return: the formatted name.
    :return: the string associated to the integer id.
    """
    max_number_of_digits = math.ceil(math.log10(nb_agents))
    if is_world_modeling:
        string_format = "tac_agent_{:0" + str(max_number_of_digits) + "}_wm"
    else:
        string_format = "tac_agent_{:0" + str(max_number_of_digits) + "}"
    result = string_format.format(agent_id)
    return result


def spawn_controller_agent(params: SimulationParams):
    """Spawn a controller agent."""
    result = multiprocessing.Process(target=controller_main, kwargs=dict(
        name="tac_controller",
        nb_agents=params.tac_parameters.min_nb_agents,
        nb_goods=params.tac_parameters.nb_goods,
        money_endowment=params.tac_parameters.money_endowment,
        base_good_endowment=params.tac_parameters.base_good_endowment,
        lower_bound_factor=params.tac_parameters.lower_bound_factor,
        upper_bound_factor=params.tac_parameters.upper_bound_factor,
        tx_fee=params.tac_parameters.tx_fee,
        oef_addr=params.oef_addr,
        oef_port=params.oef_port,
        start_time=params.tac_parameters.start_time,
        registration_timeout=params.tac_parameters.registration_timeout,
        inactivity_timeout=params.tac_parameters.inactivity_timeout,
        competition_timeout=params.tac_parameters.competition_timeout,
        whitelist_file=params.tac_parameters.whitelist,
        verbose=True,
        dashboard=params.dashboard,
        visdom_addr=params.visdom_addr,
        visdom_port=params.visdom_port,
        data_output_dir=params.data_output_dir,
        experiment_id=params.experiment_id,
        seed=params.seed,
        version=1,
    ))
    result.start()
    return result


def run_baseline_agent(**kwargs) -> None:
    """Run a baseline agent."""
    # give the time to the controller to connect to the OEF
    time.sleep(5.0)
    baseline_main(**kwargs)


def spawn_baseline_agents(params: SimulationParams) -> List[multiprocessing.Process]:
    """Spawn baseline agents."""
    fraction_world_modeling = 0.1
    nb_baseline_agents_world_modeling = round(params.nb_baseline_agents * fraction_world_modeling)

    threads = [multiprocessing.Process(target=run_baseline_agent, kwargs=dict(
        name=_make_id(i, i < nb_baseline_agents_world_modeling, params.nb_baseline_agents),
        oef_addr=params.oef_addr,
        oef_port=params.oef_port,
        register_as=params.register_as,
        search_for=params.search_for,
        is_world_modeling=i < nb_baseline_agents_world_modeling,
        services_interval=params.services_interval,
        pending_transaction_timeout=params.pending_transaction_timeout,
        dashboard=params.dashboard,
        visdom_addr=params.visdom_addr,
        visdom_port=params.visdom_port)) for i in range(params.nb_baseline_agents)]

    for t in threads:
        t.start()

    return threads


def parse_arguments():
    """Arguments parsing."""
    parser = argparse.ArgumentParser("tac_agent_spawner")
    parser.add_argument("--nb-agents", type=int, default=10, help="(minimum) number of TAC agent to wait for the competition.")
    parser.add_argument("--nb-goods", type=int, default=10, help="Number of TAC agent to run.")
    parser.add_argument("--money-endowment", type=int, default=200, help="Initial amount of money.")
    parser.add_argument("--base-good-endowment", default=2, type=int, help="The base amount of per good instances every agent receives.")
    parser.add_argument("--lower-bound-factor", default=0, type=int, help="The lower bound factor of a uniform distribution.")
    parser.add_argument("--upper-bound-factor", default=0, type=int, help="The upper bound factor of a uniform distribution.")
    parser.add_argument("--tx-fee", default=0.1, type=float, help="The transaction fee.")
    parser.add_argument("--oef-addr", default="127.0.0.1", help="TCP/IP address of the OEF Agent")
    parser.add_argument("--oef-port", default=10000, help="TCP/IP port of the OEF Agent")
    parser.add_argument("--nb-baseline-agents", type=int, default=10, help="Number of baseline agent to run. Defaults to the number of agents of the competition.")
    parser.add_argument("--start-time", default=str(datetime.datetime.now() + datetime.timedelta(0, 10)), type=str, help="The start time for the competition (in UTC format).")
    parser.add_argument("--registration-timeout", default=10, type=int, help="The amount of time (in seconds) to wait for agents to register before attempting to start the competition.")
    parser.add_argument("--inactivity-timeout", default=60, type=int, help="The amount of time (in seconds) to wait during inactivity until the termination of the competition.")
    parser.add_argument("--competition-timeout", default=240, type=int, help="The amount of time (in seconds) to wait from the start of the competition until the termination of the competition.")
    parser.add_argument("--services-interval", default=5, type=int, help="The amount of time (in seconds) the baseline agents wait until it updates services again.")
    parser.add_argument("--pending-transaction-timeout", default=120, type=int, help="The amount of time (in seconds) the baseline agents wait until the transaction confirmation.")
    parser.add_argument("--register-as", choices=['seller', 'buyer', 'both'], default='both', help="The string indicates whether the baseline agent registers as seller, buyer or both on the oef.")
    parser.add_argument("--search-for", choices=['sellers', 'buyers', 'both'], default='both', help="The string indicates whether the baseline agent searches for sellers, buyers or both on the oef.")
    parser.add_argument("--dashboard", action="store_true", help="Enable the agent dashboard.")
    parser.add_argument("--data-output-dir", default="data", help="The output directory for the simulation data.")
    parser.add_argument("--experiment-id", default=None, help="The experiment ID.")
    parser.add_argument("--visdom-addr", default="localhost", help="TCP/IP address of the Visdom server")
    parser.add_argument("--visdom-port", default=8097, help="TCP/IP port of the Visdom server")
    parser.add_argument("--seed", default=42, help="The random seed of the simulation.")
    parser.add_argument("--whitelist-file", nargs="?", default=None, type=str, help="The file that contains the list of agent names to be whitelisted.")

    arguments = parser.parse_args()
    logger.debug("Arguments: {}".format(pprint.pformat(arguments.__dict__)))

    return arguments


def build_simulation_parameters(arguments: argparse.Namespace) -> SimulationParams:
    """From argparse output, build an instance of SimulationParams."""
    tac_parameters = TACParameters(
        min_nb_agents=arguments.nb_agents,
        money_endowment=arguments.money_endowment,
        nb_goods=arguments.nb_goods,
        tx_fee=arguments.tx_fee,
        base_good_endowment=arguments.base_good_endowment,
        lower_bound_factor=arguments.lower_bound_factor,
        upper_bound_factor=arguments.upper_bound_factor,
        start_time=dateutil.parser.parse(arguments.start_time),
        registration_timeout=arguments.registration_timeout,
        competition_timeout=arguments.competition_timeout,
        inactivity_timeout=arguments.inactivity_timeout,
        whitelist=arguments.whitelist_file
    )

    simulation_params = SimulationParams(
        oef_addr=arguments.oef_addr,
        oef_port=arguments.oef_port,
        nb_baseline_agents=arguments.nb_baseline_agents,
        dashboard=arguments.dashboard,
        visdom_addr=arguments.visdom_addr,
        visdom_port=arguments.visdom_port,
        data_output_dir=arguments.data_output_dir,
        experiment_id=arguments.experiment_id,
        seed=arguments.seed,
        tac_parameters=tac_parameters
    )

    return simulation_params


def run(params: SimulationParams):
    """Run the simulation."""
    random.seed(params.seed)

    controller_thread = None  # type: Optional[multiprocessing.Process]
    baseline_threads = []  # type: List[multiprocessing.Process]

    try:

        controller_thread = spawn_controller_agent(params)
        baseline_threads = spawn_baseline_agents(params)
        controller_thread.join()

    except KeyboardInterrupt:
        logger.debug("Simulation interrupted...")
    except Exception:
        logger.exception("Unexpected exception.")
        exit(-1)
    finally:
        if controller_thread is not None:
            controller_thread.join(timeout=5)
            controller_thread.terminate()

        for t in baseline_threads:
            t.join(timeout=5)
            t.terminate()


if __name__ == '__main__':
    arguments = parse_arguments()
    simulation_parameters = build_simulation_parameters(arguments)
    run(simulation_parameters)
