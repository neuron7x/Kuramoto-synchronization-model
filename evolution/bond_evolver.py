from __future__ import annotations

import argparse
import json
import random
from typing import Dict, Tuple

import networkx as nx
from deap import algorithms, base, creator, tools

from core.energy import BondType, system_free_energy


class MetricsSnapshot:
    def __init__(
        self,
        latencies: Dict[Tuple[str, str], float],
        coherency: Dict[Tuple[str, str], float],
        resource_usage: float,
        entropy: float,
    ) -> None:
        self.latencies = latencies
        self.coherency = coherency
        self.resource_usage = resource_usage
        self.entropy = entropy


def mutate_bond_type(graph: nx.DiGraph) -> Tuple[nx.DiGraph]:
    if graph.number_of_edges() == 0:
        return (graph,)

    edge = random.choice(list(graph.edges()))
    current_type = graph.edges[edge].get("type")
    allowed = list(BondType.__args__)
    candidates = [bond for bond in allowed if bond != current_type]
    if candidates:
        graph.edges[edge]["type"] = random.choice(candidates)
    return (graph,)


def crossover_graphs(g1: nx.DiGraph, g2: nx.DiGraph) -> Tuple[nx.DiGraph, nx.DiGraph]:
    child1 = g1.copy()
    child2 = g2.copy()

    common_edges = set(g1.edges()).intersection(g2.edges())
    if not common_edges:
        return child1, child2

    sample_size = len(common_edges) // 2
    swap_edges = random.sample(list(common_edges), sample_size) if sample_size else []

    for (src, dst) in swap_edges:
        edge_type_1 = g1.edges[(src, dst)].get("type")
        edge_type_2 = g2.edges[(src, dst)].get("type")
        child1.edges[(src, dst)]["type"] = edge_type_2
        child2.edges[(src, dst)]["type"] = edge_type_1

    return child1, child2


def evaluate_graph(graph: nx.DiGraph, snap: MetricsSnapshot) -> float:
    bonds = {(u, v): data.get("type") for u, v, data in graph.edges(data=True)}
    return system_free_energy(
        bonds=bonds,
        latencies=snap.latencies,
        coherency=snap.coherency,
        resource_usage=snap.resource_usage,
        entropy=snap.entropy,
    )


def evolve_bonds(
    base_graph: nx.DiGraph,
    snap: MetricsSnapshot,
    generations: int,
    pop_size: int = 16,
    cx_prob: float = 0.4,
    mut_prob: float = 0.6,
) -> nx.DiGraph:
    if not hasattr(creator, "FitnessMin"):
        creator.create("FitnessMin", base.Fitness, weights=(-1.0,))
    if not hasattr(creator, "Individual"):
        creator.create("Individual", nx.DiGraph, fitness=creator.FitnessMin)

    toolbox = base.Toolbox()

    def init_individual() -> creator.Individual:  # type: ignore[name-defined]
        graph = base_graph.copy()
        mutate_bond_type(graph)
        individual = creator.Individual()
        individual.add_nodes_from(graph.nodes(data=True))
        individual.add_edges_from(graph.edges(data=True))
        for u, v, data in graph.edges(data=True):
            for key, value in data.items():
                individual.edges[(u, v)][key] = value
        return individual

    toolbox.register("individual", init_individual)
    toolbox.register("population", tools.initRepeat, list, toolbox.individual)

    def eval_ind(individual: nx.DiGraph) -> Tuple[float]:
        free_energy = evaluate_graph(individual, snap)
        return (free_energy,)

    def mutate_wrapper(individual: nx.DiGraph) -> Tuple[nx.DiGraph]:
        return mutate_bond_type(individual)

    def mate_wrapper(ind1: nx.DiGraph, ind2: nx.DiGraph) -> Tuple[nx.DiGraph, nx.DiGraph]:
        return crossover_graphs(ind1, ind2)

    toolbox.register("evaluate", eval_ind)
    toolbox.register("mate", mate_wrapper)
    toolbox.register("mutate", mutate_wrapper)
    toolbox.register("select", tools.selTournament, tournsize=3)

    population = toolbox.population(n=pop_size)

    for _ in range(generations):
        offspring = algorithms.varAnd(population, toolbox, cxpb=cx_prob, mutpb=mut_prob)
        fits = list(map(toolbox.evaluate, offspring))
        for fit, individual in zip(fits, offspring):
            individual.fitness.values = fit
        population = toolbox.select(offspring, k=pop_size)

    best = tools.selBest(population, k=1)[0]
    return best


def save_graph(graph: nx.DiGraph, path: str) -> None:
    data = {
        "nodes": list(graph.nodes()),
        "edges": [
            {"src": src, "dst": dst, "type": edge_data.get("type")}
            for src, dst, edge_data in graph.edges(data=True)
        ],
    }
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)


def _build_default_graph() -> nx.DiGraph:
    graph = nx.DiGraph()
    graph.add_edge("ingest", "matcher", type="covalent")
    graph.add_edge("matcher", "risk", type="ionic")
    graph.add_edge("risk", "broker", type="metallic")
    graph.add_edge("broker", "audit", type="hydrogen")
    return graph


def _default_snapshot() -> MetricsSnapshot:
    return MetricsSnapshot(
        latencies={
            ("ingest", "matcher"): 0.45,
            ("matcher", "risk"): 0.8,
            ("risk", "broker"): 0.15,
            ("broker", "audit"): 1.2,
        },
        coherency={
            ("ingest", "matcher"): 0.92,
            ("matcher", "risk"): 0.71,
            ("risk", "broker"): 0.88,
            ("broker", "audit"): 0.63,
        },
        resource_usage=0.58,
        entropy=0.33,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generations", type=int, default=50)
    parser.add_argument("--output", type=str, default="optimized_graph.json")
    args = parser.parse_args()

    graph = _build_default_graph()
    snapshot = _default_snapshot()

    best = evolve_bonds(graph, snapshot, generations=args.generations)
    save_graph(best, args.output)
    print(f"[bond_evolver] saved {args.output}")


if __name__ == "__main__":
    main()
