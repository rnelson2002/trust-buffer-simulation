from __future__ import annotations

import copy

from simulation.agent_choose_behaviour import AgentChooseBehaviour
from simulation.agent_buffers import AgentBuffers, ReputationItem, CryptoItem, TrustItem, StereotypeItem
from simulation.capability import Capability
from simulation.events import AgentStereotypeRequest, AgentCryptoRequest, AgentTaskInteraction
from simulation.constants import EPSILON

class Agent:
    def __init__(self, name: str, capabilities: List[Capability], behaviour, choose: AgentChooseBehaviour, trust_dissem_period: float,
                crypto_bux_max: int, trust_bux_max: int, reputation_bux_max: int, stereotype_bux_max: int):
        self.name = name
        self.capabilities = capabilities
        self.capability_behaviour = {capability: behaviour() for capability in self.capabilities}



        self.choose = choose()

        self.trust_dissem_period = trust_dissem_period

        self.buffers = AgentBuffers(self, crypto_bux_max, trust_bux_max, reputation_bux_max, stereotype_bux_max)

        self.sim = None
        self.cCMS = None
        self.iCMS = None

    def set_sim(self, sim):
        self.sim = sim
        self.cCMS = sim.correct_sketch
        self.iCMS = sim.incorrect_sketch

        # Give each behaviour their own random seed to prevent capabilities
        # all being good or bad simultaneously
        for (capability, behaviour) in sorted(self.capability_behaviour.items(), key=lambda x: x[0].name):
            behaviour.individual_seed = sim.rng.getrandbits(32)

    def next_trust_dissemination_period(self, rng: random.Random) -> float:
        return rng.expovariate(1.0 / self.trust_dissem_period)

    def request_stereotype(self, agent: Agent):
        self.sim.add_event(AgentStereotypeRequest(self.sim.current_time + EPSILON, self, agent))

    def request_crypto(self, agent: Agent):
        self.sim.add_event(AgentCryptoRequest(self.sim.current_time + EPSILON, self, agent))

    def receive_trust_information(self, agent: Agent):
        # Don't record information from ourself
        if agent is self:
            return

        crypto_item = self.buffers.find_crypto(agent)

        # Can't decrypt or verify
        if crypto_item is None:
            self.request_crypto(agent)
            return

        self.sim.es.use_crypto(crypto_item)

        # Need to request sterotype information here, if missing any
        if any(self.buffers.find_stereotype(agent, capability) is None for capability in self.capabilities):
            self.request_stereotype(agent)

        trust_items = copy.deepcopy(agent.buffers.trust)
        trust_items.freeze()

        # Record reputation information
        reputation_item = self.buffers.find_reputation(agent)
        if reputation_item is None:
            # Try to add this new item
            new_reputation_item = ReputationItem(agent, trust_items)

            self.buffers.add_reputation(self.sim.es, new_reputation_item)
        else:
            # Update the item
            reputation_item.trust_items = trust_items

            # Record that we have used it
            self.sim.es.use_reputation(reputation_item)


    def receive_crypto_information(self, agent: Agent):
        # Don't record information about ourself
        if agent is self:
            return

        crypto_item = self.buffers.find_crypto(agent)

        # Don't add items we already have
        if crypto_item is not None:
            return

        new_crypto_item = CryptoItem(agent)

        self.buffers.add_crypto(self.sim.es, new_crypto_item)

    def receive_stereotype_information(self, agent: Agent, capability: Capability):
        # Ignore stereotypes about ourself
        if agent is self:
            return

        # Don't want to record capabilities we do not have
        if capability not in self.capabilities:
            return

        stereotype_item = self.buffers.find_stereotype(agent, capability)

        # Don't add items we already have
        if stereotype_item is not None:
            return

        new_stereotype_item = StereotypeItem(agent, capability)

        self.buffers.add_stereotype(self.sim.es, new_stereotype_item)

    def update_trust_history(self, agent: Agent, capability: Capability, outcome: InteractionObservation):
        trust_item = self.buffers.find_trust(agent, capability)

        # Need to add item if not in buffer
        if trust_item is None:
            new_trust_item = TrustItem(agent, capability)

            self.buffers.add_trust(self.sim.es, new_trust_item)

            trust_item = self.buffers.find_trust(agent, capability)
            assert trust_item is new_trust_item or trust_item is None

        if trust_item is not None:
            trust_item.record(outcome)

            # Record that we have used it
            self.sim.es.use_trust(trust_item)

        self.log(f"Value of buffers after update {self.buffers.utility(self, capability, targets=[agent])} {capability}")

    def choose_agent_for_task(self, capability: Capability):
        item = self.choose.choose_agent_for_task(self, capability)
        if item is None:
            return None

        self.sim.es.use_crypto(item)

        self.sim.es.use_trust(self.buffers.find_trust(item.agent, capability))

        for reputation_item in self.buffers.reputation:
            if any(trust_item.agent is item and trust_item.capability is capability for trust_item in reputation_item.trust_items):
                self.sim.es.use_reputation(reputation_item)

        self.sim.es.use_stereotype(self.buffers.find_stereotype(item.agent, capability))

        return item.agent

    def perform_interaction(self, selected_agent: Agent, capability: Capability):
        # Record the values in the buffers at the time the interaction was initiated
        buffers = self.buffers.frozen()

        self.sim.add_event(AgentTaskInteraction(self.sim.current_time + EPSILON, self, capability, selected_agent, buffers))


    def log(self, message: str):
        self.sim.log(f"{self!s}|{message}")

    def __repr__(self):
        return f"Agent({self.name})"

    def __str__(self):
        return self.name

    # Can't allow this to be copied
    def __deepcopy__(self, memo):
        return self

    # Can't allow this to be copied
    def __copy__(self):
        return self
